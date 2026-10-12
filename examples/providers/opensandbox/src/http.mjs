// HTTP access to the OpenSandbox lifecycle server and to per-sandbox `execd` daemons.

import { CODES, RpcError, mapHttpError, redact } from "./errors.mjs";
import { EXECD_PORT, endpointUrl } from "./convert.mjs";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Abort controller that fires on `signal` or after `ms`; `timedOut()` tells which. */
function deadline(signal, ms) {
  const controller = new AbortController();
  let timedOut = false;
  const timer = ms > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, ms) : undefined;
  const onAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  return {
    signal: controller.signal,
    timedOut: () => timedOut,
    done() {
      if (timer) clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    },
  };
}

function networkError(err, url, secrets) {
  const reason = err?.cause?.code ?? err?.cause?.message ?? err?.message ?? String(err);
  const target = redact(new URL(url).origin, secrets);
  return new RpcError(CODES.FAIL, `Cannot reach OpenSandbox at ${target}: ${reason}`, {
    retryable: true,
    suggestion: "Check EBX_OPENSANDBOX_BASE_URL and that the server (or the sandbox, if paused) is running.",
  });
}

export class OsbClient {
  constructor(cfg, { fetchImpl = globalThis.fetch, log = () => {} } = {}) {
    this.cfg = cfg;
    this.fetch = fetchImpl;
    this.log = log;
    this.endpoints = new Map();
  }

  #lifecycleHeaders(extra = {}) {
    const headers = { Accept: "application/json", ...extra };
    if (this.cfg.apiKey) headers["OPEN-SANDBOX-API-KEY"] = this.cfg.apiKey;
    return headers;
  }

  /** Low level: one fetch with timeout, retry (idempotent calls only) and error mapping. */
  async #request(url, init, { signal, timeoutMs, idempotent = false, operation, what, feature, streaming = false }) {
    const attempts = idempotent ? this.cfg.maxRetries + 1 : 1;
    let lastError;
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      if (attempt > 0) await sleep(Math.min(200 * 2 ** (attempt - 1), 2000));
      const limit = deadline(signal, timeoutMs ?? this.cfg.httpTimeoutMs);
      try {
        const response = await this.fetch(url, { ...init, signal: limit.signal });
        if (!response.ok) {
          const text = await response.text();
          const err = mapHttpError(response.status, text, { operation, what, feature });
          err.message = redact(err.message, this.cfg.secrets);
          if (err.data.retryable && attempt + 1 < attempts) {
            lastError = err;
            limit.done();
            continue;
          }
          throw err;
        }
        if (streaming) {
          return { response, release: limit.done, timedOut: limit.timedOut };
        }
        const out = { response, buffer: Buffer.from(await response.arrayBuffer()) };
        limit.done();
        return out;
      } catch (err) {
        limit.done();
        if (err instanceof RpcError) throw err;
        if (limit.timedOut()) {
          throw new RpcError(CODES.TIMEOUT, `OpenSandbox did not answer ${operation ?? "the request"} in time.`, { retryable: idempotent });
        }
        if (signal?.aborted) throw new RpcError(CODES.FAIL, "Request cancelled.", { cancelled: true });
        lastError = networkError(err, url, this.cfg.secrets);
        if (attempt + 1 >= attempts) throw lastError;
      }
    }
    throw lastError;
  }

  /** Lifecycle API. Returns `{status, json, headers}`. */
  async lifecycle(method, path, { query, body, signal, timeoutMs, idempotent = method === "GET", operation } = {}) {
    const url = new URL(`${this.cfg.apiBase}${path}`);
    for (const [key, value] of query ?? []) url.searchParams.append(key, value);
    const init = { method, headers: this.#lifecycleHeaders() };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers["Content-Type"] = "application/json";
    }
    const { response, buffer } = await this.#request(url.toString(), init, {
      signal,
      timeoutMs,
      idempotent,
      operation: operation ?? `${method} ${path}`,
      what: "sandbox",
    });
    const text = buffer.toString("utf8");
    let json;
    try {
      json = text ? JSON.parse(text) : undefined;
    } catch {
      json = undefined;
    }
    return { status: response.status, json, headers: response.headers };
  }

  /** `{url, headers}` for a sandbox port (cached for the execd port). */
  async endpoint(sandboxId, port, { force = false, signal } = {}) {
    const cacheable = port === EXECD_PORT;
    if (cacheable && !force && this.endpoints.has(sandboxId)) return this.endpoints.get(sandboxId);
    const query = this.cfg.useServerProxy ? [["use_server_proxy", "true"]] : [];
    const { json } = await this.lifecycle("GET", `/sandboxes/${encodeURIComponent(sandboxId)}/endpoints/${port}`, {
      query,
      signal,
      operation: `resolve endpoint for port ${port}`,
    });
    if (!json || typeof json.endpoint !== "string") {
      throw new RpcError(CODES.FAIL, `OpenSandbox returned no endpoint for port ${port}.`);
    }
    const resolved = { url: endpointUrl(json.endpoint, this.cfg.scheme).replace(/\/+$/, ""), headers: { ...(json.headers ?? {}) } };
    if (cacheable) this.endpoints.set(sandboxId, resolved);
    return resolved;
  }

  forget(sandboxId) {
    this.endpoints.delete(sandboxId);
  }

  /**
   * Data-plane request against the sandbox's execd. `Endpoint.headers` are replayed verbatim.
   * Returns `{response, buffer}`; with `streaming: true` returns `{response, release, timedOut}` (drain the body, then call `release`).
   */
  async execd(sandboxId, method, path, opts = {}) {
    const { query, body, rawBody, contentType, signal, timeoutMs, idempotent = method === "GET", operation, what, headers: extra } = opts;
    let refreshed = false;
    for (;;) {
      const ep = await this.endpoint(sandboxId, EXECD_PORT, { force: refreshed, signal });
      const url = new URL(`${ep.url}${path}`);
      for (const [key, value] of query ?? []) url.searchParams.append(key, value);
      const init = { method, headers: { ...ep.headers, ...(extra ?? {}) } };
      if (body !== undefined) {
        init.body = JSON.stringify(body);
        init.headers["Content-Type"] = "application/json";
      } else if (rawBody !== undefined) {
        init.body = rawBody;
        init.headers["Content-Type"] = contentType;
      }
      try {
        return await this.#request(url.toString(), init, {
          signal,
          timeoutMs,
          idempotent,
          operation: operation ?? `${method} ${path}`,
          what,
          streaming: opts.streaming,
        });
      } catch (err) {
        const connectionFailure = err instanceof RpcError && err.data?.retryable && err.httpStatus === undefined;
        if (connectionFailure && !refreshed) {
          this.forget(sandboxId);
          refreshed = true;
          continue;
        }
        throw err;
      }
    }
  }

  async execdJson(sandboxId, method, path, opts = {}) {
    const { buffer } = await this.execd(sandboxId, method, path, opts);
    const text = buffer.toString("utf8");
    return text ? JSON.parse(text) : undefined;
  }
}

export { sleep };
