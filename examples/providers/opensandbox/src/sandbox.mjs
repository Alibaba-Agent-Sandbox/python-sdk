// sandbox.* and ports.url methods (OpenSandbox lifecycle API).

import { CODES, RpcError, badParams, failure } from "./errors.mjs";
import {
  CODE_INTERPRETER_ENTRYPOINT,
  DEFAULT_ENTRYPOINT,
  withCreateOptions,
} from "./config.mjs";
import {
  EXECD_PORT,
  cpuLimit,
  gpuLimit,
  isCodeInterpreterImage,
  mapState,
  memoryLimit,
  parseHttpDate,
  resolveImage,
  statusToStates,
  ttlSeconds,
  validateMetadata,
} from "./convert.mjs";
import { sleep } from "./http.mjs";

const need = (params, key) => {
  const value = params[key];
  if (typeof value !== "string" || value === "") throw badParams(`Missing parameter '${key}'.`);
  return value;
};

export const sandboxId = (params) => need(params, "sandbox_id");

export function toRecord(sb, fallbackImage = "") {
  const record = {
    sandbox_id: sb.id,
    template: sb.image?.uri ?? (sb.snapshotId ? `snapshot:${sb.snapshotId}` : fallbackImage),
    status: mapState(sb.status?.state),
    metadata: sb.metadata ?? {},
  };
  if (sb.createdAt) record.created_at = sb.createdAt;
  if (sb.expiresAt) record.expires_at = sb.expiresAt;
  if (sb.status?.state) record.state = sb.status.state;
  if (sb.status?.message) record.status_message = sb.status.message;
  return record;
}

export function buildCreateBody(params, baseCfg, log = () => {}) {
  const cfg = withCreateOptions(baseCfg, params.options);
  if (params.disk !== undefined && params.disk !== null && params.disk !== 0) {
    throw badParams("OpenSandbox cannot size the disk: 'disk' is ignored by its Docker runtime, so it is refused.", {
      suggestion: "Omit disk, or use a volume through a custom deployment.",
    });
  }
  const image = resolveImage(params.template, cfg);
  const limits = { cpu: cpuLimit(params.cpu), memory: memoryLimit(params.memory) };
  const gpu = gpuLimit(params.gpu);
  if (gpu !== undefined) limits.gpu = gpu;
  const entrypoint = cfg.entrypoint ?? (isCodeInterpreterImage(image) ? CODE_INTERPRETER_ENTRYPOINT : DEFAULT_ENTRYPOINT);
  const body = {
    image: { uri: image },
    entrypoint,
    resourceLimits: limits,
  };
  if (cfg.registryUsername) body.image.auth = { username: cfg.registryUsername, password: cfg.registryPassword ?? "" };
  const { timeout, clamped } = ttlSeconds(params.timeout);
  if (timeout !== undefined) body.timeout = timeout;
  if (clamped) log(`timeout ${params.timeout}s is below OpenSandbox's 60 s minimum; using 60 s`);
  if (params.envs && Object.keys(params.envs).length > 0) body.env = Object.fromEntries(Object.entries(params.envs).map(([k, v]) => [k, String(v)]));
  const metadata = validateMetadata(params.metadata);
  if (Object.keys(metadata).length > 0) body.metadata = metadata;
  if (cfg.networkPolicy) body.networkPolicy = cfg.networkPolicy;
  if (cfg.platform) body.platform = cfg.platform;
  // `secure` is sent by the host only when the user set it; otherwise the configured default applies.
  if (typeof params.secure === "boolean" ? params.secure : cfg.secureAccess) body.secureAccess = true;
  return { body, image };
}

async function waitRunning(ctx, id, signal) {
  const deadline = Date.now() + ctx.cfg.readyTimeout * 1000;
  for (;;) {
    const { json } = await ctx.osb.lifecycle("GET", `/sandboxes/${encodeURIComponent(id)}`, { signal });
    const state = json?.status?.state;
    if (state === "Running") return json;
    if (state === "Failed" || state === "Terminated") {
      throw failure(`Sandbox ${id} entered state ${state}${json?.status?.message ? `: ${json.status.message}` : ""}.`);
    }
    if (Date.now() > deadline) throw new RpcError(CODES.TIMEOUT, `Sandbox ${id} was not running after ${ctx.cfg.readyTimeout}s (state ${state}).`);
    await sleep(500);
  }
}

async function waitExecd(ctx, id, signal) {
  const deadline = Date.now() + ctx.cfg.readyTimeout * 1000;
  let last;
  for (;;) {
    try {
      await ctx.osb.execd(id, "GET", "/ping", { signal, timeoutMs: 5000, idempotent: false, operation: "execd ping" });
      return;
    } catch (err) {
      if (!(err instanceof RpcError) || err.data?.cancelled) throw err;
      last = err;
      ctx.osb.forget(id);
    }
    if (Date.now() > deadline) {
      throw new RpcError(CODES.TIMEOUT, `execd of sandbox ${id} did not become ready within ${ctx.cfg.readyTimeout}s: ${last?.message ?? ""}`);
    }
    await sleep(250);
  }
}

async function killQuietly(ctx, id) {
  try {
    await ctx.osb.lifecycle("DELETE", `/sandboxes/${encodeURIComponent(id)}`, { idempotent: false });
  } catch {
    /* best effort */
  }
}

export const methods = {
  async "sandbox.create"(params, ctx) {
    const { body, image } = buildCreateBody(params, ctx.cfg, ctx.log);
    const requestMs = Math.max(ctx.cfg.httpTimeoutMs, ctx.cfg.readyTimeout * 1000, (Number(params.request_timeout) || 0) * 1000);
    const { json } = await ctx.osb.lifecycle("POST", "/sandboxes", {
      body,
      signal: ctx.signal,
      timeoutMs: requestMs,
      idempotent: false,
      operation: "create sandbox",
    });
    const id = json?.id;
    if (!id) throw failure("OpenSandbox returned no sandbox id.");
    try {
      await waitRunning(ctx, id, ctx.signal);
      await waitExecd(ctx, id, ctx.signal);
    } catch (err) {
      await killQuietly(ctx, id);
      throw err;
    }
    const { json: full } = await ctx.osb.lifecycle("GET", `/sandboxes/${encodeURIComponent(id)}`, { signal: ctx.signal });
    return toRecord(full ?? json, image);
  },

  async "sandbox.get"(params, ctx) {
    const { json } = await ctx.osb.lifecycle("GET", `/sandboxes/${encodeURIComponent(sandboxId(params))}`, { signal: ctx.signal, operation: "get sandbox" });
    return toRecord(json);
  },

  async "sandbox.connect"(params, ctx) {
    return methods["sandbox.get"](params, ctx);
  },

  async "sandbox.list"(params, ctx) {
    const page = params.cursor ? Number.parseInt(String(params.cursor), 10) : 1;
    if (!Number.isInteger(page) || page < 1) throw badParams(`Invalid cursor '${params.cursor}'.`);
    const limit = Math.min(Math.max(Number(params.limit) || 20, 1), 200);
    const query = [["page", String(page)], ["pageSize", String(limit)]];
    for (const state of statusToStates(params.status)) query.push(["state", state]);
    const filter = Object.entries(params.metadata ?? {});
    if (filter.length > 0) query.push(["metadata", filter.map(([k, v]) => `${k}=${v}`).join("&")]);
    const { json } = await ctx.osb.lifecycle("GET", "/sandboxes", { query, signal: ctx.signal, operation: "list sandboxes" });
    const result = { sandboxes: (json?.items ?? []).map((item) => toRecord(item)) };
    if (json?.pagination?.hasNextPage) result.next = String(page + 1);
    return result;
  },

  async "sandbox.kill"(params, ctx) {
    const path = `/sandboxes/${encodeURIComponent(sandboxId(params))}`;
    const attempt = () => ctx.osb.lifecycle("DELETE", path, { signal: ctx.signal, idempotent: false, operation: "kill sandbox" });
    try {
      try {
        await attempt();
      } catch (err) {
        if (err.httpStatus !== 409) throw err;
        await sleep(1000);
        await attempt();
      }
    } catch (err) {
      if (err.code !== CODES.NOT_FOUND) throw err;
    }
    ctx.osb.forget(params.sandbox_id);
    return {};
  },

  async "sandbox.set_timeout"(params, ctx) {
    const id = sandboxId(params);
    const seconds = Math.ceil(Number(params.timeout));
    if (!Number.isFinite(seconds) || seconds <= 0) throw badParams(`Invalid timeout '${params.timeout}'.`);
    // The API sets an absolute time; derive "now" from the server's clock to avoid client skew.
    const { headers } = await ctx.osb.lifecycle("GET", `/sandboxes/${encodeURIComponent(id)}`, { signal: ctx.signal, operation: "read server time" });
    const now = parseHttpDate(headers.get("date")) ?? Date.now();
    const expiresAt = new Date(now + seconds * 1000).toISOString();
    await ctx.osb.lifecycle("POST", `/sandboxes/${encodeURIComponent(id)}/renew-expiration`, {
      body: { expiresAt },
      signal: ctx.signal,
      idempotent: false,
      operation: "set timeout",
    });
    return { expires_at: expiresAt };
  },

  async "sandbox.pause"(params, ctx) {
    return transition(ctx, sandboxId(params), "pause", "Paused");
  },

  async "sandbox.resume"(params, ctx) {
    return transition(ctx, sandboxId(params), "resume", "Running");
  },

  async "ports.url"(params, ctx) {
    const port = Number(params.port);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw badParams(`Invalid port '${params.port}'.`);
    const ep = await ctx.osb.endpoint(sandboxId(params), port, { force: true, signal: ctx.signal });
    const result = { url: ep.url };
    if (Object.keys(ep.headers).length > 0) result.headers = ep.headers;
    return result;
  },
};

async function transition(ctx, id, verb, target) {
  const enc = encodeURIComponent(id);
  await ctx.osb.lifecycle("POST", `/sandboxes/${enc}/${verb}`, { signal: ctx.signal, idempotent: false, operation: `${verb} sandbox` });
  const deadline = Date.now() + 30_000;
  for (;;) {
    const { json } = await ctx.osb.lifecycle("GET", `/sandboxes/${enc}`, { signal: ctx.signal });
    if (json?.status?.state === target) break;
    if (json?.status?.state === "Failed") throw failure(`Sandbox ${id} failed while trying to ${verb}.`);
    if (Date.now() > deadline) throw new RpcError(CODES.TIMEOUT, `Sandbox ${id} did not reach ${target} within 30s.`);
    await sleep(300);
  }
  if (verb === "resume") await waitExecd(ctx, id, ctx.signal);
  return {};
}

export { EXECD_PORT };
