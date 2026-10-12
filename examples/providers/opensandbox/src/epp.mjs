// EPP/1: newline-delimited JSON-RPC 2.0 over stdin/stdout. Logs go to stderr only.

import { createInterface } from "node:readline";
import { CODES, RpcError } from "./errors.mjs";

const MAX_LINE_BYTES = 8 * 1024 * 1024 - 1024;

/**
 * Serve requests until stdin closes or `shutdown` is answered.
 *
 * `dispatch(method, params, call)` returns the result or throws; `call` carries:
 *   signal          aborted on `$/cancel` or shutdown
 *   notify(m, p)    send a notification
 *   afterResponse(fn)  run `fn` once this request's response has been written
 *   shutdown()      ask the loop to stop after this response
 */
export function serve({ input, output, dispatch, onClose = () => {}, log = () => {} }) {
  const inflight = new Map();
  let stopping = false;

  const write = (obj) => {
    let line = JSON.stringify(obj);
    if (Buffer.byteLength(line) > MAX_LINE_BYTES) {
      line = JSON.stringify({
        jsonrpc: "2.0",
        id: obj.id ?? null,
        error: {
          code: CODES.BAD_PARAMS,
          message: "Result is larger than the 8 MiB EPP line limit; request a smaller range.",
          data: { suggestion: "Read the file in chunks (offset/length)." },
        },
      });
    }
    return output.write(`${line}\n`);
  };
  const notify = (method, params) => write({ jsonrpc: "2.0", method, params });

  const finish = () => {
    if (stopping) return;
    stopping = true;
    for (const controller of inflight.values()) controller.abort();
    inflight.clear();
    onClose();
  };

  async function handle(message) {
    const { id, method, params } = message;
    if (id === undefined || id === null) {
      if (method === "$/cancel" && params && inflight.has(params.id)) inflight.get(params.id).abort();
      return;
    }
    if (typeof method !== "string") {
      write({ jsonrpc: "2.0", id, error: { code: -32600, message: "Invalid request" } });
      return;
    }
    const controller = new AbortController();
    inflight.set(id, controller);
    const after = [];
    let stopAfter = false;
    try {
      const result = await dispatch(method, params ?? {}, {
        signal: controller.signal,
        notify,
        afterResponse: (fn) => after.push(fn),
        shutdown: () => { stopAfter = true; },
      });
      write({ jsonrpc: "2.0", id, result: result ?? {} });
    } catch (err) {
      if (err instanceof RpcError) {
        write({ jsonrpc: "2.0", id, error: { code: err.code, message: err.message, data: err.data } });
      } else {
        log(`internal error in ${method}: ${err?.stack ?? err}`);
        write({
          jsonrpc: "2.0",
          id,
          error: { code: CODES.FAIL, message: `${err?.name ?? "Error"}: ${err?.message ?? err}`, data: {} },
        });
      }
    } finally {
      inflight.delete(id);
    }
    for (const fn of after) {
      try {
        fn();
      } catch (err) {
        log(`afterResponse hook failed: ${err}`);
      }
    }
    if (stopAfter) finish();
  }

  const rl = createInterface({ input, crlfDelay: Infinity });
  rl.on("line", (line) => {
    const text = line.trim();
    if (!text) return;
    let message;
    try {
      message = JSON.parse(text);
    } catch {
      write({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Parse error" } });
      return;
    }
    if (!message || typeof message !== "object") return;
    handle(message).catch((err) => log(`unhandled: ${err?.stack ?? err}`));
  });
  rl.on("close", finish);
  return { notify, close: finish };
}
