// files.* methods (execd `/files` and `/directories`).

import { RpcError, CODES, badParams, unsupported } from "./errors.mjs";
import { fileEntry, modeDigits } from "./convert.mjs";
import { buildUpload } from "./multipart.mjs";
import { sandboxId } from "./sandbox.mjs";

/** A single EPP line is capped at 8 MiB and base64 adds a third. */
export const MAX_INLINE_BYTES = 4 * 1024 * 1024;

const pathOf = (params, key = "path") => {
  const value = params[key];
  if (typeof value !== "string" || value === "") throw badParams(`Missing parameter '${key}'.`);
  return value;
};

const fileOp = (ctx, id, method, path, opts = {}) =>
  ctx.osb.execd(id, method, path, { signal: ctx.signal, what: "file", timeoutMs: Math.max(ctx.cfg.httpTimeoutMs, 60_000), ...opts });

async function statOf(ctx, id, path) {
  const json = await ctx.osb.execdJson(id, "GET", "/files/info", {
    query: [["path", path]],
    signal: ctx.signal,
    what: "file",
    operation: `stat ${path}`,
  });
  const info = json?.[path] ?? Object.values(json ?? {})[0];
  if (!info) throw new RpcError(CODES.NOT_FOUND, `No such file or directory: ${path}`, { sdk_code: "E4001" });
  return info;
}

const exists = async (ctx, id, path) => {
  try {
    await statOf(ctx, id, path);
    return true;
  } catch (err) {
    if (err.code === CODES.NOT_FOUND) return false;
    throw err;
  }
};

async function removeAny(ctx, id, path, info) {
  const isDir = info.type === "directory";
  await fileOp(ctx, id, "DELETE", isDir ? "/directories" : "/files", {
    query: [["path", path]],
    idempotent: false,
    operation: `remove ${path}`,
  });
}

export const methods = {
  async "files.read"(params, ctx) {
    const id = sandboxId(params);
    const path = pathOf(params);
    const info = await statOf(ctx, id, path);
    if (info.type === "directory") {
      throw new RpcError(CODES.BAD_PARAMS, `'${path}' is a directory, not a file.`, { sdk_code: "E4000" });
    }
    const total = Number(info.size ?? 0);
    const offset = Math.max(Number(params.offset) || 0, 0);
    const wanted = params.length === undefined || params.length === null ? total - offset : Number(params.length);
    const length = Math.max(Math.min(wanted, total - offset), 0);
    if (length > MAX_INLINE_BYTES) {
      throw badParams(
        `'${path}' has ${length} bytes to read, above the ${MAX_INLINE_BYTES}-byte limit of one EPP message.`,
        { suggestion: "Pass offset/length to read it in chunks.", total_size: total },
      );
    }
    const headers = {};
    if (offset > 0 || params.length !== undefined) {
      if (length === 0) return { content_b64: "", size: 0, total_size: total, offset, eof: offset >= total };
      headers.Range = `bytes=${offset}-${offset + length - 1}`;
    }
    const { buffer } = await fileOp(ctx, id, "GET", "/files/download", { query: [["path", path]], headers, operation: `read ${path}` });
    return { content_b64: buffer.toString("base64"), size: buffer.length, total_size: total, offset, eof: offset + buffer.length >= total };
  },

  async "files.write"(params, ctx) {
    const id = sandboxId(params);
    const path = pathOf(params);
    const content = Buffer.from(String(params.content_b64 ?? ""), "base64");
    const { body, contentType } = buildUpload({ path, mode: modeDigits(params.mode), content });
    await fileOp(ctx, id, "POST", "/files/upload", { rawBody: body, contentType, idempotent: false, operation: `write ${path}` });
    return { size: content.length };
  },

  async "files.list"(params, ctx) {
    const id = sandboxId(params);
    const path = pathOf(params);
    const depth = Math.max(Number(params.depth) || 1, 1);
    const json = await ctx.osb.execdJson(id, "GET", "/directories/list", {
      query: [["path", path], ["depth", String(depth)]],
      signal: ctx.signal,
      what: "file",
      operation: `list ${path}`,
    });
    return { entries: (Array.isArray(json) ? json : []).map(fileEntry) };
  },

  async "files.stat"(params, ctx) {
    return fileEntry(await statOf(ctx, sandboxId(params), pathOf(params)));
  },

  async "files.mkdir"(params, ctx) {
    const path = pathOf(params);
    const mode = modeDigits(params.mode) ?? 755;
    await fileOp(ctx, sandboxId(params), "POST", "/directories", { body: { [path]: { mode } }, idempotent: false, operation: `mkdir ${path}` });
    return {};
  },

  async "files.remove"(params, ctx) {
    const id = sandboxId(params);
    const path = pathOf(params);
    await removeAny(ctx, id, path, await statOf(ctx, id, path));
    return {};
  },

  async "files.move"(params, ctx) {
    const id = sandboxId(params);
    const source = pathOf(params, params.source !== undefined ? "source" : "src");
    const destination = pathOf(params, params.destination !== undefined ? "destination" : "dest");
    await statOf(ctx, id, source);
    let existing;
    try {
      existing = await statOf(ctx, id, destination);
    } catch (err) {
      if (err.code !== CODES.NOT_FOUND) throw err;
    }
    if (existing) {
      if (params.overwrite !== true) throw badParams(`Destination '${destination}' already exists.`, { suggestion: "Pass overwrite=true to replace it." });
      await removeAny(ctx, id, destination, existing);
    }
    await fileOp(ctx, id, "POST", "/files/mv", { body: [{ src: source, dest: destination }], idempotent: false, operation: `move ${source}` });
    return {};
  },

  /** Extension (not in the EPP/1 table): recursive glob. */
  async "files.search"(params, ctx) {
    const id = sandboxId(params);
    const root = pathOf(params);
    const json = await ctx.osb.execdJson(id, "GET", "/files/search", {
      query: [["path", root], ["pattern", String(params.pattern ?? "**")]],
      signal: ctx.signal,
      what: "file",
      operation: `search ${root}`,
    });
    let entries = (Array.isArray(json) ? json : []).map(fileEntry);
    if (params.type === "file" || params.type === "directory") entries = entries.filter((e) => e.type === params.type);
    if (Number.isInteger(params.max_depth) && params.max_depth > 0) {
      const base = root.replace(/\/+$/, "");
      entries = entries.filter((e) => e.path.slice(base.length).split("/").filter(Boolean).length <= params.max_depth);
    }
    return { entries };
  },

  /** Extension: change mode/owner. */
  async "files.chmod"(params, ctx) {
    const path = pathOf(params);
    const spec = { mode: modeDigits(params.mode) ?? 644 };
    if (params.owner) spec.owner = String(params.owner);
    if (params.group) spec.group = String(params.group);
    await fileOp(ctx, sandboxId(params), "POST", "/files/permissions", { body: { [path]: spec }, idempotent: false, operation: `chmod ${path}` });
    return {};
  },

  async "files.watch"() {
    throw unsupported("files.watch", "OpenSandbox's execd has no file-watch endpoint.");
  },
  async "files.transfer"() {
    throw unsupported("files.transfer", "OpenSandbox has no signed upload/download URLs.");
  },
  async "files.upload_url"() {
    throw unsupported("files.transfer", "OpenSandbox has no signed upload/download URLs.");
  },
  async "files.download_url"() {
    throw unsupported("files.transfer", "OpenSandbox has no signed upload/download URLs.");
  },
};

export { exists };
