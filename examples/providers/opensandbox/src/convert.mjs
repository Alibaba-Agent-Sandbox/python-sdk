// Pure conversion helpers (no I/O): easy to unit test.

import { badParams } from "./errors.mjs";

export const EXECD_PORT = 44772;
export const MIN_TTL_SECONDS = 60;

const NAME_RE = /^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$/;
const DNS_RE = /^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$/;

/** OpenSandbox stores metadata as Kubernetes labels and rejects anything else at create time. */
export function validateMetadata(metadata) {
  const out = {};
  for (const [key, rawValue] of Object.entries(metadata ?? {})) {
    const value = String(rawValue);
    const slash = key.indexOf("/");
    const prefix = slash >= 0 ? key.slice(0, slash) : "";
    const name = slash >= 0 ? key.slice(slash + 1) : key;
    if (slash >= 0 && (prefix.length === 0 || prefix.length > 253 || !DNS_RE.test(prefix))) {
      throw badParams(`Invalid metadata key '${key}': the prefix before '/' must be a DNS subdomain (max 253 chars).`);
    }
    if (name.length === 0 || name.length > 63 || !NAME_RE.test(name)) {
      throw badParams(
        `Invalid metadata key '${key}': OpenSandbox stores metadata as Kubernetes labels; ` +
          `a key name is 1-63 chars of [A-Za-z0-9._-], starting and ending alphanumeric.`,
      );
    }
    if (value.length > 63 || (value.length > 0 && !NAME_RE.test(value))) {
      throw badParams(
        `Invalid metadata value for '${key}': at most 63 chars of [A-Za-z0-9._-], ` +
          `starting and ending alphanumeric (got ${JSON.stringify(value.slice(0, 40))}).`,
      );
    }
    out[key] = value;
  }
  return out;
}

const STATE_TO_STATUS = {
  Pending: "creating",
  Running: "running",
  Pausing: "paused",
  Paused: "paused",
  Resuming: "creating",
  Stopping: "stopping",
  Terminated: "stopped",
  Failed: "error",
};

export function mapState(state) {
  return STATE_TO_STATUS[state] ?? "error";
}

const STATUS_TO_STATES = {
  running: ["Running"],
  paused: ["Paused", "Pausing"],
  creating: ["Pending", "Resuming"],
  stopping: ["Stopping"],
  stopped: ["Terminated"],
  error: ["Failed"],
};

export function statusToStates(status) {
  return status ? (STATUS_TO_STATES[status] ?? []) : [];
}

export function cpuLimit(cpu) {
  if (cpu === undefined || cpu === null || cpu === "") return "500m";
  const n = Number(cpu);
  if (!Number.isFinite(n) || n <= 0) throw badParams(`Invalid cpu '${cpu}': expected a positive number of cores.`);
  return Number.isInteger(n) ? String(n) : `${Math.round(n * 1000)}m`;
}

export function memoryLimit(memoryMb) {
  if (memoryMb === undefined || memoryMb === null || memoryMb === "") return "512Mi";
  const n = Number(memoryMb);
  if (!Number.isFinite(n) || n <= 0) throw badParams(`Invalid memory '${memoryMb}': expected megabytes.`);
  return `${Math.round(n)}Mi`;
}

/** OpenSandbox accepts only a numeric GPU count; Easy Sandbox's gpu is a free-form spec such as "A10". */
export function gpuLimit(gpu) {
  if (gpu === undefined || gpu === null || gpu === "") return undefined;
  if (/^\d+$/.test(String(gpu))) return String(gpu);
  throw badParams(`Unsupported gpu '${gpu}': OpenSandbox takes a numeric GPU count, not a GPU type.`);
}

/** TTL seconds -> server `timeout` (minimum 60). Returns {timeout, clamped}. */
export function ttlSeconds(timeout) {
  if (timeout === undefined || timeout === null) return { timeout: undefined, clamped: false };
  const n = Math.ceil(Number(timeout));
  if (!Number.isFinite(n) || n <= 0) throw badParams(`Invalid timeout '${timeout}': expected seconds.`);
  return n < MIN_TTL_SECONDS ? { timeout: MIN_TTL_SECONDS, clamped: true } : { timeout: n, clamped: false };
}

/** "a=b,c=d" or ["a=b"] or {a: "b"} -> object. */
export function parseAliasMap(value) {
  if (!value) return {};
  if (typeof value === "object" && !Array.isArray(value)) return { ...value };
  const items = Array.isArray(value) ? value : String(value).split(",");
  const out = {};
  for (const item of items) {
    const eq = String(item).indexOf("=");
    if (eq > 0) out[String(item).slice(0, eq).trim()] = String(item).slice(eq + 1).trim();
  }
  return out;
}

/** Minimal POSIX-ish word splitter (quotes and backslashes) for the `entrypoint` setting. */
export function shellSplit(text) {
  const out = [];
  let cur = "";
  let quote = "";
  let active = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = "";
      else if (ch === "\\" && quote === '"' && i + 1 < text.length) cur += text[++i];
      else cur += ch;
    } else if (ch === "'" || ch === '"') {
      quote = ch;
      active = true;
    } else if (ch === "\\" && i + 1 < text.length) {
      cur += text[++i];
      active = true;
    } else if (/\s/.test(ch)) {
      if (active || cur) out.push(cur);
      cur = "";
      active = false;
    } else {
      cur += ch;
      active = true;
    }
  }
  if (quote) throw badParams(`Unterminated quote in '${text}'.`);
  if (active || cur) out.push(cur);
  return out;
}

export function shellQuote(word) {
  const s = String(word);
  return s === "" ? "''" : /^[A-Za-z0-9_@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;
}

export const shellJoin = (argv) => argv.map(shellQuote).join(" ");

/** Template -> image URI: `base`/empty -> default image, alias -> image, anything else is a literal URI. */
export function resolveImage(template, cfg) {
  const name = String(template ?? "").trim();
  if (!name || name === "base") return cfg.defaultImage;
  if (Object.hasOwn(cfg.imageAliases, name)) return cfg.imageAliases[name];
  return name;
}

export function isCodeInterpreterImage(uri) {
  return /(^|\/)opensandbox\/code-interpreter(:|@|$)/.test(uri);
}

/** `Endpoint.endpoint` has no scheme ("host:port[/path]"). */
export function endpointUrl(endpoint, scheme) {
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(endpoint) ? endpoint : `${scheme}://${endpoint}`;
}

/** Mode accepted as int (0o644 = 420), "0644"/"644"/"0o644" (octal text) -> execd's octal-digits int (644). */
export function modeDigits(mode) {
  if (mode === undefined || mode === null || mode === "") return undefined;
  if (typeof mode === "number") {
    if (!Number.isInteger(mode) || mode < 0) throw badParams(`Invalid file mode '${mode}'.`);
    return Number.parseInt(mode.toString(8), 10);
  }
  const text = String(mode).replace(/^0o/i, "");
  if (!/^[0-7]{1,4}$/.test(text)) throw badParams(`Invalid file mode '${mode}': expected octal digits.`);
  return Number.parseInt(text, 10);
}

export const basename = (path) => {
  const trimmed = String(path).replace(/\/+$/, "");
  return trimmed.slice(trimmed.lastIndexOf("/") + 1) || "/";
};

/** execd FileInfo -> EPP files entry. */
export function fileEntry(info) {
  const kind = info.type === "directory" ? "directory" : "file";
  const entry = {
    name: basename(info.path),
    path: info.path,
    type: kind,
    size: Number(info.size ?? 0),
  };
  if (info.modified_at) entry.mtime = info.modified_at;
  if (info.type === "symlink") entry.symlink = true;
  if (info.mode !== undefined) entry.mode = info.mode;
  if (info.owner) entry.owner = info.owner;
  if (info.group) entry.group = info.group;
  return entry;
}

/** Exit code carried by an execd `error` stream event (see the mapping doc §1.4). */
export function exitFromErrorEvent(error) {
  const evalue = String(error?.evalue ?? "");
  const trace = Array.isArray(error?.traceback) ? error.traceback.join(" ") : "";
  if (/^-?\d+$/.test(evalue)) {
    const code = Number(evalue);
    if (code === -1 && /killed|signal/i.test(trace)) return { exitCode: -1, killed: true, message: trace };
    return { exitCode: code, killed: false, message: trace };
  }
  const lower = evalue.toLowerCase();
  const notFound = lower.includes("not found") || lower.includes("no such file") || lower.includes("executable file");
  return { exitCode: notFound ? 127 : 126, killed: false, message: evalue || trace, startFailure: true };
}

/** execd < the line-preserving build emits one event per line without the terminator. */
export function restoreLineEnding(text) {
  return /[\r\n]$/.test(text) ? text : `${text}\n`;
}

export function parseHttpDate(value) {
  if (!value) return undefined;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? undefined : ms;
}
