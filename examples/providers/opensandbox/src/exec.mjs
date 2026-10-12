// exec.* and process.* methods (execd `/command`).

import { randomBytes, randomUUID } from "node:crypto";
import { CODES, RpcError, badParams, failure, notFound, unsupported } from "./errors.mjs";
import { exitFromErrorEvent, restoreLineEnding, shellJoin } from "./convert.mjs";
import { buildUpload } from "./multipart.mjs";
import { readEvents } from "./sse.mjs";
import { sleep } from "./http.mjs";
import { sandboxId } from "./sandbox.mjs";

const STDIN_WRAPPER = 'f="$1"; shift; "$@" < "$f"; rc=$?; rm -f "$f"; exit $rc';
const WATCHDOG_MS = 15_000;

/** One shell script, no `ps`: slim images do not ship procps. Output: pid, ppid, state, user, cmd (tab separated). */
const LIST_PROCESSES = [
  "# __ebx_ps__",
  "for d in /proc/[0-9]*; do",
  '  pid=${d#/proc/}; [ -r "$d/stat" ] || continue',
  '  line=$(cat "$d/stat" 2>/dev/null) || continue',
  "  rest=${line##*) }; set -- $rest; state=$1; ppid=$2",
  `  cmd=$(tr '\\0' ' ' < "$d/cmdline" 2>/dev/null)`,
  '  [ -n "$cmd" ] || cmd=$(cat "$d/comm" 2>/dev/null)',
  '  user=$(stat -c %U "$d" 2>/dev/null)',
  "  printf '%s\\t%s\\t%s\\t%s\\t%s\\n' \"$pid\" \"$ppid\" \"$state\" \"$user\" \"$cmd\"",
  "done",
].join("\n");

const isExecdId = (value) => typeof value === "string" && !/^\d+$/.test(value) && /^[0-9a-zA-Z_-]{8,}$/.test(value);
const isPid = (value) => (Number.isInteger(value) && value > 0) || (typeof value === "string" && /^\d+$/.test(value));

async function resolveUser(ctx, id, user, signal) {
  const text = String(user ?? "").trim();
  if (!text) return {};
  if (/^\d+$/.test(text)) return { uid: Number(text) };
  const key = `${id}:${text}`;
  if (ctx.state.users.has(key)) return ctx.state.users.get(key);
  const lookup = async (flag) => {
    const res = await runCollect(ctx, id, quick(["id", flag, text], 15), signal);
    if (res.exit_code !== 0 || !/^\d+$/.test(res.stdout.trim())) throw badParams(`Unknown user '${text}' in sandbox ${id}.`);
    return Number(res.stdout.trim());
  };
  const resolved = { uid: await lookup("-u"), gid: await lookup("-g") };
  ctx.state.users.set(key, resolved);
  return resolved;
}

/** Everything about a command except the argv/command field (which depends on the execd generation). */
async function prepare(ctx, id, params, signal) {
  let argv = [String(params.cmd ?? ""), ...(params.args ?? []).map(String)];
  if (!argv[0]) throw badParams("Missing parameter 'cmd'.");
  if (typeof params.stdin === "string" && params.stdin.length > 0) {
    const file = `/tmp/.ebx-stdin-${randomUUID()}`;
    await upload(ctx, id, file, Buffer.from(params.stdin, "utf8"), signal);
    argv = ["sh", "-c", STDIN_WRAPPER, "sh", file, ...argv];
  }
  const extras = {};
  if (params.cwd) extras.cwd = String(params.cwd);
  if (params.env && Object.keys(params.env).length > 0) {
    extras.envs = Object.fromEntries(Object.entries(params.env).map(([k, v]) => [k, String(v)]));
  }
  const timeoutSec = Number(params.timeout);
  const hasTimeout = Number.isFinite(timeoutSec) && timeoutSec > 0;
  if (hasTimeout) extras.timeout = Math.round(timeoutSec * 1000);
  Object.assign(extras, await resolveUser(ctx, id, params.user, signal));
  return { argv, extras, hasTimeout, timeoutSec: hasTimeout ? timeoutSec : 0 };
}

const quick = (argv, timeoutSec) => ({
  argv,
  extras: { timeout: timeoutSec * 1000 },
  hasTimeout: true,
  timeoutSec,
});

function commandBody(prepared, legacy, background) {
  const body = { ...prepared.extras };
  if (legacy) body.command = shellJoin(prepared.argv);
  else body.argv = prepared.argv;
  if (background) body.background = true;
  return body;
}

/** POST /command, falling back to the string form on execd builds that predate `argv`. */
async function openStream(ctx, id, prepared, { signal, background = false }) {
  for (let pass = 0; pass < 2; pass += 1) {
    try {
      return await ctx.osb.execd(id, "POST", "/command", {
        body: commandBody(prepared, ctx.state.legacyExecd, background),
        signal,
        timeoutMs: prepared.hasTimeout ? prepared.timeoutSec * 1000 + WATCHDOG_MS : 0,
        idempotent: false,
        streaming: true,
        operation: "run command",
      });
    } catch (err) {
      const legacyRejection = !ctx.state.legacyExecd && err.httpStatus === 400 && /'Command'|argv/i.test(err.rawMessage ?? "");
      if (!legacyRejection) throw err;
      ctx.state.legacyExecd = true;
      ctx.log("execd predates 'argv': falling back to string commands and per-line output events");
    }
  }
  throw failure("execd rejected the command in both argv and string form.");
}

function streamFailure(stream, signal) {
  if (signal?.aborted) return new RpcError(CODES.FAIL, "Request cancelled.", { cancelled: true });
  if (stream.timedOut()) return new RpcError(CODES.TIMEOUT, "The command stream did not finish in time.", { sdk_code: "E3001" });
  return failure("The connection to execd closed before the command finished.", { retryable: false });
}

const fixLine = (ctx, text) => (ctx.state.legacyExecd ? restoreLineEnding(text) : text);

/** Run to completion; returns the EPP `exec.run` result. */
async function runCollect(ctx, id, spec, signal) {
  const prepared = spec;
  const stream = await openStream(ctx, id, prepared, { signal });
  const stdout = [];
  const stderr = [];
  let exit;
  let commandId;
  try {
    for await (const ev of readEvents(stream.response)) {
      if (ev.type === "init") commandId = ev.text;
      else if (ev.type === "stdout") stdout.push(fixLine(ctx, String(ev.text ?? "")));
      else if (ev.type === "stderr") stderr.push(fixLine(ctx, String(ev.text ?? "")));
      else if (ev.type === "error") {
        const parsed = exitFromErrorEvent(ev.error);
        if (parsed.killed && prepared.hasTimeout) {
          throw new RpcError(CODES.TIMEOUT, `Command timed out after ${prepared.timeoutSec}s.`, { sdk_code: "E3001", command_id: commandId });
        }
        if (parsed.startFailure) stderr.push(`${parsed.message}\n`);
        else if (parsed.killed) stderr.push("Killed\n");
        exit = parsed.killed ? 137 : parsed.exitCode;
      } else if (ev.type === "execution_complete" && exit === undefined) exit = 0;
    }
  } catch (err) {
    if (err instanceof RpcError) throw err;
    throw streamFailure(stream, signal);
  } finally {
    stream.release();
  }
  if (exit === undefined) throw failure("execd ended the event stream without an exit status.");
  return { exit_code: exit, stdout: stdout.join(""), stderr: stderr.join(""), command_id: commandId };
}

async function upload(ctx, id, path, content, signal) {
  const { body, contentType } = buildUpload({ path, content });
  await ctx.osb.execd(id, "POST", "/files/upload", {
    rawBody: body,
    contentType,
    signal,
    idempotent: false,
    timeoutMs: Math.max(ctx.cfg.httpTimeoutMs, 60_000),
    operation: "upload file",
    what: "file",
  });
}

/** Foreground-less run: execd keeps the command alive; we poll its merged log. */
async function pumpDetached(ctx, id, processId, signal, notify) {
  let cursor = 0;
  const enc = encodeURIComponent(processId);
  const drain = async () => {
    const { response, buffer } = await ctx.osb.execd(id, "GET", `/command/${enc}/logs`, {
      query: [["cursor", String(cursor)]],
      signal,
      operation: "read command log",
    });
    const next = Number(response.headers.get("execd-commands-tail-cursor"));
    if (Number.isFinite(next)) cursor = next;
    if (buffer.length > 0) notify("exec.output", { process_id: processId, stream: "stdout", data: buffer.toString("utf8") });
  };
  for (;;) {
    await drain();
    const status = await ctx.osb.execdJson(id, "GET", `/command/status/${enc}`, { signal, operation: "command status" });
    if (!status.running) {
      await drain();
      return typeof status.exit_code === "number" ? status.exit_code : status.error ? 1 : 0;
    }
    await sleep(250);
  }
}

export const methods = {
  async "exec.run"(params, ctx) {
    const id = sandboxId(params);
    const prepared = await prepare(ctx, id, params, ctx.signal);
    const { exit_code, stdout, stderr } = await runCollect(ctx, id, prepared, ctx.signal);
    return { exit_code, stdout, stderr };
  },

  async "exec.start"(params, ctx) {
    const id = sandboxId(params);
    const signal = ctx.signal;
    const prepared = await prepare(ctx, id, params, signal);
    const detached = params.detached === true;
    const stream = await openStream(ctx, id, prepared, { signal, background: detached });
    const iterator = readEvents(stream.response)[Symbol.asyncIterator]();
    let first;
    try {
      first = await iterator.next();
    } catch (err) {
      stream.release();
      throw err instanceof RpcError ? err : streamFailure(stream, signal);
    }
    const processId = first.value?.type === "init" && first.value.text ? String(first.value.text) : randomBytes(16).toString("hex");
    const head = first.value?.type === "init" ? [] : first.done ? [] : [first.value];
    const done = first.done;

    ctx.afterResponse(() => {
      const task = (async () => {
        const out = (stream_, data) => ctx.notify("exec.output", { process_id: processId, stream: stream_, data });
        let exit;
        try {
          const handle = (ev) => {
            if (ev.type === "stdout" || ev.type === "stderr") out(ev.type, fixLine(ctx, String(ev.text ?? "")));
            else if (ev.type === "error") {
              const parsed = exitFromErrorEvent(ev.error);
              if (parsed.killed && prepared.hasTimeout) {
                out("stderr", `Command timed out after ${prepared.timeoutSec}s\n`);
                exit = 124;
              } else {
                if (parsed.startFailure) out("stderr", `${parsed.message}\n`);
                exit = parsed.killed ? 137 : parsed.exitCode;
              }
            } else if (ev.type === "execution_complete" && exit === undefined) exit = 0;
          };
          for (const ev of head) handle(ev);
          if (!done) for (let n = await iterator.next(); !n.done; n = await iterator.next()) handle(n.value);
          if (detached) exit = await pumpDetached(ctx, id, processId, signal, ctx.notify);
        } catch (err) {
          const failed = err instanceof RpcError ? err : streamFailure(stream, signal);
          out("stderr", `${failed.message}\n`);
          exit = exit ?? 1;
        } finally {
          stream.release();
        }
        ctx.notify("exec.exit", { process_id: processId, exit_code: exit ?? 1 });
      })();
      ctx.track(task);
    });
    return { process_id: processId };
  },

  async "process.list"(params, ctx) {
    const id = sandboxId(params);
    const res = await runCollect(ctx, id, quick(["sh", "-c", LIST_PROCESSES], 20), ctx.signal);
    if (res.exit_code !== 0 && !res.stdout) throw failure(`Could not list processes: ${res.stderr.trim() || `exit ${res.exit_code}`}`);
    const processes = [];
    for (const line of res.stdout.split("\n")) {
      const [pid, ppid, state, user, ...cmd] = line.split("\t");
      const command = cmd.join("\t").trim();
      if (!/^\d+$/.test(pid ?? "") || command.includes("__ebx_ps__")) continue;
      processes.push({
        pid: Number(pid),
        ppid: Number(ppid),
        user,
        command,
        status: state === "Z" ? "zombie" : state === "T" ? "stopped" : "running",
      });
    }
    return { processes };
  },

  async "process.kill"(params, ctx) {
    return signalProcess(params, ctx, 9);
  },

  async "process.signal"(params, ctx) {
    const sig = params.signal ?? 15;
    return signalProcess(params, ctx, sig);
  },

  async "process.stdin"() {
    throw unsupported(
      "process.stdin",
      "OpenSandbox's execd /command has no stdin channel; use `exec.run` with stdin or a PTY session.",
    );
  },
};

function signalName(sig) {
  if (Number.isInteger(sig)) return String(sig);
  const name = String(sig).trim().toUpperCase().replace(/^SIG/, "");
  if (!/^[A-Z0-9]{1,10}$/.test(name)) throw badParams(`Invalid signal '${sig}'.`);
  return name;
}

async function signalProcess(params, ctx, sig) {
  const id = sandboxId(params);
  const target = params.pid ?? params.process_id;
  const name = signalName(sig);
  if (isPid(target)) {
    const res = await runCollect(ctx, id, quick(["sh", "-c", 'kill -"$1" "$2"', "sh", name, String(target)], 15), ctx.signal);
    if (res.exit_code !== 0) {
      const text = res.stderr.trim() || `exit ${res.exit_code}`;
      if (/no such process|not found/i.test(text)) throw notFound(`No process with pid ${target}.`);
      throw failure(`kill failed: ${text}`);
    }
    return {};
  }
  if (isExecdId(target)) {
    if (name !== "9" && name !== "KILL") {
      throw unsupported("process.signal", "execd can only SIGKILL a command it started (by command id); use a numeric pid for other signals.");
    }
    await ctx.osb.execd(id, "DELETE", "/command", { query: [["id", String(target)]], signal: ctx.signal, idempotent: false, operation: "interrupt command", what: "command" });
    return {};
  }
  throw badParams(`Invalid process id '${target}': expected a numeric pid or an execd command id.`);
}
