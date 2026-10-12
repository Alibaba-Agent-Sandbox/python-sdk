#!/usr/bin/env node
// OpenSandbox provider for Easy Sandbox: an EPP/1 plugin in dependency-free Node ESM (Node >= 20).
// Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout, free-form logs on stderr.

import { pathToFileURL } from "node:url";
import { serve } from "./src/epp.mjs";
import { parseConfig } from "./src/config.mjs";
import { OsbClient } from "./src/http.mjs";
import { CODES, RpcError, badParams, redact, unsupported } from "./src/errors.mjs";
import { methods as sandboxMethods } from "./src/sandbox.mjs";
import { methods as execMethods } from "./src/exec.mjs";
import { methods as fileMethods } from "./src/files.mjs";

export const PROTOCOL = "epp/1";
export const PLUGIN = { name: "opensandbox", version: "0.1.0" };

/** What this plugin implements; keep in sync with `[features] supported` in ebx-provider.toml. */
export const FEATURES = [
  "sandbox.lifecycle",
  "sandbox.timeout",
  "sandbox.pause",
  "exec.run",
  "exec.stream",
  "process.manage",
  "files.rw",
  "ports.url",
  "sessions",
];

/** EPP methods of features OpenSandbox cannot provide: answered with -32003 (E8004 in the host). */
const UNSUPPORTED = {
  "pty.open": "pty",
  "pty.write": "pty",
  "pty.resize": "pty",
  "pty.close": "pty",
  "code.run": "code.interpret",
  "code.context.create": "code.interpret",
  "code.context.list": "code.interpret",
  "code.context.remove": "code.interpret",
  "code.context.restart": "code.interpret",
  "templates.list": "templates.read",
  "templates.get": "templates.read",
  "templates.delete": "templates.build",
  "templates.build": "templates.build",
  "templates.build_status": "templates.build",
};

const STATELESS = { ...sandboxMethods, ...execMethods, ...fileMethods };

export function createPlugin({ log = () => {}, fetchImpl } = {}) {
  const session = { cfg: undefined, osb: undefined, tasks: new Set() };
  const state = { legacyExecd: false, users: new Map() };

  const dispatch = async (method, params, call) => {
    if (method === "initialize") {
      if (params.protocol !== PROTOCOL) throw badParams(`Unsupported protocol '${params.protocol}', this plugin speaks ${PROTOCOL}.`);
      session.cfg = parseConfig(params.config ?? {}, params.core ?? {});
      session.osb = new OsbClient(session.cfg, { fetchImpl, log });
      return { protocol: PROTOCOL, plugin: PLUGIN, features: FEATURES };
    }
    if (method === "shutdown") {
      call.shutdown();
      return {};
    }
    if (UNSUPPORTED[method]) throw unsupported(UNSUPPORTED[method]);
    const handler = STATELESS[method];
    if (!handler) throw new RpcError(CODES.METHOD_NOT_FOUND, `Unknown method ${method}`);
    if (!session.cfg) throw new RpcError(CODES.FAIL, "initialize must be the first request.");
    const ctx = {
      cfg: session.cfg,
      osb: session.osb,
      state,
      log,
      signal: call.signal,
      notify: call.notify,
      afterResponse: call.afterResponse,
      track(task) {
        session.tasks.add(task);
        task.finally(() => session.tasks.delete(task));
      },
    };
    try {
      return await handler(params, ctx);
    } catch (err) {
      if (err instanceof RpcError) err.message = redact(err.message, session.cfg.secrets);
      throw err;
    }
  };

  return { dispatch, session };
}

export function main() {
  const log = (message) => process.stderr.write(`[opensandbox] ${message}\n`);
  const { dispatch } = createPlugin({ log });
  const exit = () => process.stdout.write("", () => process.exit(0));
  process.on("uncaughtException", (err) => {
    log(`fatal: ${err?.stack ?? err}`);
    process.exit(1);
  });
  serve({ input: process.stdin, output: process.stdout, dispatch, onClose: exit, log });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
