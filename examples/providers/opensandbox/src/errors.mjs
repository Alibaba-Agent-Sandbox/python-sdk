// EPP/1 error codes and the translation of OpenSandbox HTTP failures into them.

export const CODES = Object.freeze({
  AUTH: -32001,
  NOT_FOUND: -32002,
  NO_FEATURE: -32003,
  QUOTA: -32004,
  TIMEOUT: -32005,
  BAD_PARAMS: -32006,
  FAIL: -32000,
  METHOD_NOT_FOUND: -32601,
});

export class RpcError extends Error {
  constructor(code, message, data = {}) {
    super(message);
    this.name = "RpcError";
    this.code = code;
    this.data = data;
  }

  toJSON() {
    return { code: this.code, message: this.message, data: this.data };
  }
}

export const badParams = (message, data = {}) => new RpcError(CODES.BAD_PARAMS, message, data);
export const notFound = (message, data = {}) => new RpcError(CODES.NOT_FOUND, message, data);
export const failure = (message, data = {}) => new RpcError(CODES.FAIL, message, data);

export function unsupported(feature, message) {
  return new RpcError(
    CODES.NO_FEATURE,
    message ?? `OpenSandbox does not support '${feature}'.`,
    { feature, details: { feature } },
  );
}

/** Replace every secret (4+ chars) in `text` with `***`. */
export function redact(text, secrets = []) {
  let out = String(text);
  for (const secret of secrets) {
    if (secret && secret.length >= 4) out = out.split(secret).join("***");
  }
  return out;
}

/**
 * Normalise the three error body shapes OpenSandbox produces, plus non-JSON bodies:
 *   lifecycle   {"code": "DOCKER::SANDBOX_NOT_FOUND", "message": "..."}
 *   FastAPI     {"detail": [{"type", "loc", "msg", "input"}]}   (422)
 *   execd 401   {"error": "Unauthorized: ..."}
 */
export function parseErrorBody(raw) {
  const text = typeof raw === "string" ? raw : "";
  let json;
  try {
    json = text ? JSON.parse(text) : undefined;
  } catch {
    json = undefined;
  }
  if (json && typeof json === "object" && !Array.isArray(json)) {
    if (Array.isArray(json.detail)) {
      const msgs = json.detail.map((d) => {
        const where = Array.isArray(d.loc) ? d.loc.filter((p) => p !== "body").join(".") : "";
        return where ? `${where}: ${d.msg}` : String(d.msg ?? JSON.stringify(d));
      });
      return { code: "VALIDATION_ERROR", message: msgs.join("; "), details: json.detail };
    }
    if (typeof json.detail === "string") return { code: json.code ?? "", message: json.detail };
    if (typeof json.error === "string") return { code: json.code ?? "", message: json.error };
    if (typeof json.message === "string") return { code: String(json.code ?? ""), message: json.message };
  }
  const plain = text.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return { code: "", message: plain.slice(0, 300) };
}

/**
 * Map an HTTP failure to an RpcError.
 * `ctx.what` is "sandbox" | "file" | "command" | "endpoint" (selects the not-found flavour).
 */
export function mapHttpError(status, rawBody, ctx = {}) {
  const parsed = parseErrorBody(rawBody);
  const where = ctx.operation ? ` (${ctx.operation})` : "";
  const detail = parsed.message ? `: ${parsed.message}` : "";
  const base = `OpenSandbox HTTP ${status}${where}${detail}`;
  const data = { http_status: status };
  if (parsed.code) data.code = parsed.code;
  if (parsed.details) data.details = parsed.details;
  const make = (code, message, extra = {}) => {
    const err = new RpcError(code, message, { ...data, ...extra });
    err.httpStatus = status;
    err.rawMessage = parsed.message;
    err.rawCode = parsed.code;
    return err;
  };
  const upper = String(parsed.code).toUpperCase();
  const lower = parsed.message.toLowerCase();

  if (status === 401) {
    return make(CODES.AUTH, `OpenSandbox rejected the API key${where}${detail}`, {
      sdk_code: "E1001",
      suggestion: "Set EBX_OPENSANDBOX_API_KEY (or OPEN_SANDBOX_API_KEY) to a valid key.",
    });
  }
  if (lower.includes("runtime server not configured")) {
    return make(CODES.NO_FEATURE, `${base}. The sandbox image has no code-interpreter runtime.`, {
      feature: "code.interpret",
      details: { feature: "code.interpret" },
    });
  }
  if (status === 501 || upper.includes("NOT_SUPPORTED")) {
    return make(CODES.NO_FEATURE, base, { feature: ctx.feature ?? "unknown", details: { feature: ctx.feature ?? "unknown" } });
  }
  if (status === 404) {
    const sdk = ctx.what === "file" || upper.includes("FILE_NOT_FOUND") ? { sdk_code: "E4001" } : {};
    return make(CODES.NOT_FOUND, base, sdk);
  }
  if (upper.includes("IMAGE_PULL") || (upper.includes("IMAGE") && lower.includes("not found"))) {
    return make(CODES.NOT_FOUND, base, { sdk_code: "E2001", suggestion: "Check the image URI used as template." });
  }
  if (status === 429) return make(CODES.QUOTA, base, { retryable: true, sdk_code: "E2002" });
  if (status === 403 && (upper.includes("QUOTA") || lower.includes("quota"))) {
    return make(CODES.QUOTA, base, { sdk_code: "E2002" });
  }
  if (status === 400 || status === 422) return make(CODES.BAD_PARAMS, base);
  if (status === 502 || status === 503 || status === 504) return make(CODES.FAIL, base, { retryable: true });
  return make(CODES.FAIL, base);
}
