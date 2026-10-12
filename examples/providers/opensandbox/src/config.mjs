// Turns the `initialize` payload into a validated, immutable plugin configuration.

import { badParams } from "./errors.mjs";
import { parseAliasMap, shellSplit } from "./convert.mjs";

export const DEFAULT_BASE_URL = "http://127.0.0.1:8080";
export const DEFAULT_IMAGE = "python:3.12-slim";
export const DEFAULT_ALIASES = { code: "opensandbox/code-interpreter:v1.1.0" };
export const DEFAULT_ENTRYPOINT = ["tail", "-f", "/dev/null"];
export const CODE_INTERPRETER_ENTRYPOINT = ["/opt/code-interpreter/code-interpreter.sh"];

const blank = (v) => v === undefined || v === null || (typeof v === "string" && v.trim() === "");

function toBool(value, key, fallback) {
  if (blank(value)) return fallback;
  if (typeof value === "boolean") return value;
  const text = String(value).trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(text)) return true;
  if (["0", "false", "no", "off"].includes(text)) return false;
  throw badParams(`Invalid boolean for '${key}': ${JSON.stringify(value)}.`);
}

function toInt(value, key, fallback, min) {
  if (blank(value)) return fallback;
  const n = Number(value);
  if (!Number.isInteger(n) || n < min) throw badParams(`'${key}' must be an integer >= ${min} (got ${JSON.stringify(value)}).`);
  return n;
}

/** `https://host:8080/v1/` -> `https://host:8080` (the plugin appends `/v1` itself). */
export function normalizeBaseUrl(raw) {
  let url;
  try {
    url = new URL(String(raw).trim());
  } catch {
    throw badParams(`Invalid base_url '${raw}': expected an http(s) URL such as http://127.0.0.1:8080.`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw badParams(`Invalid base_url '${raw}': only http and https are supported.`);
  }
  const path = url.pathname.replace(/\/+$/, "").replace(/\/v1$/, "");
  return `${url.protocol}//${url.host}${path}`;
}

export function parseConfig(config = {}, core = {}) {
  const protocol = blank(config.protocol) ? "http" : String(config.protocol).toLowerCase();
  if (protocol !== "http" && protocol !== "https") throw badParams(`Invalid protocol '${config.protocol}': use http or https.`);

  let root;
  if (!blank(config.base_url)) root = normalizeBaseUrl(config.base_url);
  else if (!blank(config.domain)) root = normalizeBaseUrl(`${protocol}://${String(config.domain).trim()}`);
  else root = DEFAULT_BASE_URL;

  let networkPolicy;
  if (!blank(config.network_policy)) {
    try {
      networkPolicy = typeof config.network_policy === "string" ? JSON.parse(config.network_policy) : config.network_policy;
    } catch (err) {
      throw badParams(`'network_policy' must be a JSON object: ${err.message}`);
    }
  }

  let platform;
  if (!blank(config.platform)) {
    const m = /^(linux|windows)\/(amd64|arm64)$/.exec(String(config.platform).trim());
    if (!m) throw badParams(`Invalid platform '${config.platform}': use linux/amd64, linux/arm64, windows/amd64 or windows/arm64.`);
    platform = { os: m[1], arch: m[2] };
  }

  const entrypoint = blank(config.entrypoint) ? undefined : shellSplit(String(config.entrypoint));
  const httpTimeout = Number(core.http_timeout);

  const parsed = {
    baseUrl: root,
    apiBase: `${root}/v1`,
    scheme: new URL(root).protocol.replace(":", ""),
    apiKey: blank(config.api_key) ? undefined : String(config.api_key),
    useServerProxy: toBool(config.use_server_proxy, "use_server_proxy", false),
    secureAccess: toBool(config.secure_access, "secure_access", false),
    defaultImage: blank(config.default_image) ? DEFAULT_IMAGE : String(config.default_image).trim(),
    imageAliases: blank(config.image_aliases) ? { ...DEFAULT_ALIASES } : parseAliasMap(config.image_aliases),
    entrypoint,
    readyTimeout: toInt(config.ready_timeout, "ready_timeout", 60, 1),
    registryUsername: blank(config.registry_username) ? undefined : String(config.registry_username),
    registryPassword: blank(config.registry_password) ? undefined : String(config.registry_password),
    networkPolicy,
    platform,
    httpTimeoutMs: Number.isFinite(httpTimeout) && httpTimeout >= 1 ? Math.round(httpTimeout * 1000) : 30_000,
    maxRetries: Number.isInteger(core.max_retries) && core.max_retries >= 0 ? core.max_retries : 3,
    secrets: [config.api_key, config.registry_password].filter((s) => typeof s === "string" && s.length >= 4),
  };
  Object.defineProperty(parsed, "raw", { value: { ...config }, enumerable: false });
  return Object.freeze(parsed);
}

/** Options a caller may override per `sandbox.create` (never the server address or the API key). */
export const CREATE_OPTION_KEYS = Object.freeze([
  "default_image",
  "image_aliases",
  "entrypoint",
  "ready_timeout",
  "registry_username",
  "registry_password",
  "network_policy",
  "platform",
  "secure_access",
]);

/** The configuration for one create: `initialize` config plus the whitelisted per-create `options`. */
export function withCreateOptions(cfg, options) {
  if (!options || typeof options !== "object" || Array.isArray(options)) return cfg;
  const overrides = Object.fromEntries(Object.entries(options).filter(([k, v]) => CREATE_OPTION_KEYS.includes(k) && !blank(v)));
  if (Object.keys(overrides).length === 0) return cfg;
  return parseConfig({ ...cfg.raw, ...overrides }, { http_timeout: cfg.httpTimeoutMs / 1000, max_retries: cfg.maxRetries });
}
