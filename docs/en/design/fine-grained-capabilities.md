# Fine-Grained Capabilities, Scoping and Permissions

> Status: **v2 (reviewed)**. Draft v1 went through the two review rounds recorded in
> [fine-grained-capabilities-review.md](fine-grained-capabilities-review.md); the resolutions
> are folded in below and summarised in section 11.
> Scope: `easy-sandbox-server` (`easy_sandbox.server`) enforcement, `template.yaml`
> declarative config, and `easy-sandbox` (`easy_sandbox`) client discovery / errors / helpers.
> Companion docs: [client-server-alignment.md](client-server-alignment.md),
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md),
> [server-api.md](server-api.md).

## 1. Problem

The server exposes endpoints through **coarse capability groups** (`FILE_OPS`, `PROCESS`, ...).
Turning on `FILE_OPS` exposes eleven endpoints (list, stat, mkdir, delete, move, search,
upload, download, archive, legacy upload/download), all confined only by one process-wide
`EBX_SERVER_BASE_DIR`. Product needs finer control:

* expose **only** the upload and download endpoints;
* make download usable only from specified directories;
* per-endpoint permissions (who may call what), size limits, read-only mode;
* the same rules visible to, and enforced consistently by, the client SDK.

Non-goals: this is *not* an OS sandbox. Path scoping is an API-level control; if the same caller
may also run arbitrary processes (`shell`, `code_run`, PTY, `process_start`) it can bypass any file
rule. The server lints for this combination (see 3.9).

## 2. Design principles

1. **Backward compatible by construction.** With no policy configured, every request takes the
   code path that exists today (same status codes, same bodies; new fields are additive).
2. **Fail closed.** A policy that is present but invalid prevents the server from starting; it
   never degrades to "allow all".
3. **One decision point, keyed by the matched route.** Policy attaches to the `RouteInfo`
   chosen by the router, never to a re-parsed URL string, so router/policy discrepancies
   (encoded paths, method override, trailing slashes) cannot exist.
4. **Resolve once, use the resolved value.** Path checks return the resolved path that the
   operation then uses (no second resolution); the open is hardened against symlink swaps.
5. **Narrowing is easy, widening is explicit.** Presets start from a deny posture; deny rules
   accumulate across selectors; allow roots are explicit.
6. **Discovery <= execution.** A caller sees (and can pre-check) exactly what it may use.
7. **Single schema, two spellings.** JSON policy (stdlib-only server) == `server:` block of
   `template.yaml` (compiled to JSON by tooling).

## 3. Model

### 3.1 Endpoint identity

Every built-in route already has a stable `name` (`files_list`, `files_download_stream`,
`shell`, `process_signal`, ...). The name is the **endpoint ID** used in policy, discovery,
audit and client errors. Method + path are *not* identifiers. Custom routes registered with
`RouteTable.route(...)` get the same treatment (their `name`).

New built-in endpoints introduced for client/server alignment (see alignment doc):
`files_watch`, `process_stdin`, `process_output`, `pty_detail`, `pty_resize`,
`capabilities_check`.

### 3.2 Scopes (permission model)

Each endpoint requires a set of **scopes** (all-of). Defaults come from a built-in catalogue
(`policy.ENDPOINT_CATALOG`; a unit test asserts every registered built-in route has an entry).

| Scope | Endpoints (default) |
|-------|---------------------|
| `core:read` | `capabilities`, `capabilities_check` (implicit for every authenticated identity) |
| `commands:list` / `commands:run` | `list_commands` / `run_command` (+ per-command scopes, 3.8) |
| `files:read` | `download`, `files_list`, `files_stat`, `files_search`, `files_download_stream`, `files_archive`, `files_watch` |
| `files:write` | `upload`, `files_mkdir`, `files_upload_stream` |
| `files:write` + `files:delete` | `files_move` |
| `files:delete` | `files_delete` |
| `process:run` | `shell`, `shell_stream`, `process_start` |
| `process:read` | `process_list`, `process_detail`, `process_output` |
| `process:manage` | `process_signal`, `process_stdin` |
| `terminal:use` | `pty_*` and the PTY WebSocket |
| `system:read` / `system:write` | `system_info`, `system_metrics`, `ports`, `packages`, `env_get` / `env_set` |
| `devtools:run` / `devtools:read` | `code_run` / `git_status`, `git_diff` |
| `browser:use` / `browser:evaluate` | `browser_*` / `browser_evaluate` |

Scope syntax: `namespace:action`; `*` grants everything; `namespace:*` grants a namespace.
`health` needs no authentication (unchanged).

### 3.3 Identities and tokens

Today: one optional `EBX_SERVER_TOKEN` compared against `X-Access-Token`.

* **Unchanged default.** No token -> anonymous identity with scope `*` (local mode). One
  `EBX_SERVER_TOKEN` -> identity `legacy` with scope `*` (override via `auth.legacy_scopes`).
* **New:** `auth.tokens` — a list of `{id, scopes, token_env | token_sha256}`. Plain tokens
  are never accepted inline in files (a secret in a baked image file is a leak). `token_env`
  names an environment variable read at start; `token_sha256` is the hex digest of the token.
* When `auth.tokens` is present, anonymous access is disabled (`auth.allow_anonymous: true`
  opts back in with `auth.anonymous_scopes`).
* **Transport.** `X-Access-Token` (compatible with the FC gateway header) *or*
  `Authorization: Bearer <token>`. If both are sent, the `Authorization` header is used for the
  server identity (the gateway token may legitimately differ).
* Comparison is constant time over **all** configured tokens (digest then `compare_digest`; no
  early exit) so response time does not reveal which token matched.

### 3.4 Endpoint rules

```jsonc
{
  "version": 1,
  "preset": "default",                // default | transfer-only | read-only | hardened | locked
  "base_dir": "/home/user",           // optional; overrides EBX_SERVER_BASE_DIR
  "groups": { "dev_tools": false },   // same effect as enable_group / disable_group
  "defaults": { "audit": "deny", "limits": { "max_request_bytes": 10485760 } },
  "auth": {
    "tokens": [
      { "id": "uploader", "token_env": "EBX_TOKEN_UPLOADER", "scopes": ["files:write"] },
      { "id": "reader",   "token_sha256": "9f86d0...", "scopes": ["files:read"] }
    ]
  },
  "endpoints": {
    "*":                       { "enabled": false },               // glob selector
    "files_download_stream":   {
      "enabled": true,
      "scopes": ["files:read"],                                    // replaces catalogue default
      "paths": { "allow": ["/home/user/out"], "deny": ["**/.env", "**/*.pem"],
                 "read_only": false, "symlinks": "within" },
      "limits": { "max_bytes": 5242880, "rate_per_minute": 60, "max_concurrency": 4 },
      "audit": "all"
    },
    "files_upload_stream": {
      "enabled": true,
      "paths": { "allow": ["/home/user/uploads"] },
      "limits": { "max_bytes": 10485760 },
      "params": { "overwrite": false, "deny_extensions": [".sh", ".so"] }
    }
  }
}
```

**Selectors** (keys of `endpoints`): exact ID, glob (`files_*`, `*`), or `group:<name>`.
**Merge order** (later wins, per field): built-in defaults < preset < `defaults` < `group:` rules
< glob rules (shorter literal prefix first) < exact rules. Merge semantics per field:
scalars/`allow` lists **replace**; `deny` lists and `deny_*` params **union**; `enabled: false`
at the same specificity beats `true`.

**Effective enabled** = group enabled (route table, env, `groups`) **AND** rule `enabled`.
A rule can never re-enable a disabled group, and `CORE` endpoints (`health`, `capabilities`,
`capabilities_check`) cannot be disabled.

### 3.5 Path scoping

For endpoints that take filesystem paths (`files_*`, `upload`, `download`, `git_*`, and `cwd` of
`shell`, `shell_stream`, `process_start`, `code_run` is cwd-less):

* `paths.allow` — absolute directories. **When present it replaces `base_dir` as the boundary
  of that endpoint** (so `/tmp/exports` can be exposed even though `base_dir` is
  `/home/user`). Absent -> `base_dir` (unchanged behaviour). Allow roots are `realpath`-ed per
  request.
* `paths.deny` — absolute directory prefixes or glob patterns (`**/.env`, `*.pem`). A pattern
  without `/` matches basenames. Deny always wins, evaluated on the *resolved* path.
* `paths.read_only` — rejects write/delete operations on that endpoint (operations are
  classified per endpoint: `read`, `write`, `delete`, `exec`).
* `paths.symlinks` — `within` (default; symlinks may be followed if the *target* stays inside the
  allowed boundary) or `never` (any symlink in the requested path -> denied).

Algorithm (`PathGuard.resolve(raw, op)`): reject NUL/non-str -> make absolute (relative paths
resolve against `base_dir`... see compat note below) -> `realpath` -> boundary check -> deny
check -> read-only check -> return resolved path. Policy is evaluated **before** any existence
check so error responses are not a filesystem oracle. File opens use `O_NOFOLLOW` on the final
component and re-verify the opened fd (`/proc/self/fd/N`, fallback `fstat` identity) to narrow
the check/use window.

Compat note: today relative paths resolve against the server process CWD. This is kept for
the unconfigured case; when `paths.allow` is configured relative paths resolve against the
first allow root, which is the only sensible reading.

Directory-expanding endpoints enforce the policy **on every produced entry**: `files_list` and
`files_search` omit denied entries and never descend into denied directories; `files_archive`
excludes denied descendants and refuses file symlinks whose target is outside the boundary (this
also fixes the existing `zipfile` symlink read).

### 3.6 Limits and parameters

Closed vocabularies per endpoint (unknown keys are validation errors, so typos fail loudly).

| Where | Keys |
|-------|------|
| all endpoints | `limits.max_request_bytes`, `limits.rate_per_minute`, `limits.max_concurrency`, `audit` |
| `upload`, `files_upload_stream` | `limits.max_bytes`; `params.overwrite`, `params.allow_extensions`, `params.deny_extensions` |
| `download`, `files_download_stream` | `limits.max_bytes` |
| `files_list` | `limits.max_entries`, `limits.max_depth` |
| `files_search` | `limits.max_results`, `limits.max_depth`, `limits.timeout_seconds` |
| `files_archive` | `limits.max_files`, `limits.max_bytes` |
| `files_watch` | `limits.max_duration_seconds` |
| `shell`, `shell_stream`, `process_start` | `params.allow_commands`, `params.deny_commands` (argv[0] basename *and* full path), `limits.timeout_seconds` (cap), `limits.max_output_bytes`, `limits.max_processes` |
| `process_signal` | `params.allowed_signals` |
| `pty_create_session` | `params.shells`, `limits.max_sessions`, `params.env_deny` |
| `env_get`, `env_set` | `params.allow_vars`, `params.deny_vars` (glob) |
| `code_run` | `params.languages`, `limits.timeout_seconds`, `limits.max_output_bytes` |
| `browser_navigate` | `params.url_allow`, `params.url_deny`, `params.block_private_networks` |

Limits default to *today's* constants when unset. A configured limit can only be as large as the
user wrote; there is no hidden ceiling.

### 3.7 Rate limiting, concurrency, audit

Per `(identity, endpoint)` token bucket (`rate_per_minute`, burst = rate) and semaphore
(`max_concurrency`). Denied with `429` + `Retry-After`. Audit events go to the
`easy_sandbox.server.audit` logger as one JSON object per line: `ts, identity, endpoint,
method, decision, code, status, paths(resolved, truncated)` — never tokens, bodies or file
contents. `audit`: `off` | `deny` (default) | `all`.

### 3.8 Per-command scopes (custom commands)

`registry.command("deploy", scopes=["deploy"])` — callers need `commands:run` **and** `deploy`.
`GET /commands` lists only the commands the caller may run (discovery <= execution).

### 3.9 Lint

`ServerPolicy.lint()` returns human-readable warnings, logged at startup and printed by
`easy-sandbox-server check-config`: path scoping configured while `process`/`terminal`/
`dev_tools`/`browser` endpoints are reachable by the same scopes; allow root `/`; wildcard
token scopes with other tokens defined; `overwrite: false` without `paths.allow`; etc.

### 3.10 Subprocess environment

When `auth.tokens` is configured, child processes started by `shell*`, `process_start`,
`code_run`, `git_*` and PTY sessions receive `os.environ` **minus** `EBX_SERVER_TOKEN`,
`EBX_SERVER_POLICY*` and every `token_env` variable, so a `process:run` identity cannot read
another identity's secret. Unconfigured servers keep today's behaviour.

## 4. Configuration surfaces

Resolution order (low -> high): code defaults < well-known file
(`/etc/easy-sandbox/server-policy.json` if present) < `EBX_SERVER_POLICY_FILE` <
`EBX_SERVER_POLICY` (inline JSON) < `SandboxServer(policy=...)`. Legacy env vars
(`EBX_SERVER_DISABLED_GROUPS`, `EBX_SERVER_BASE_DIR`, `EBX_MAX_UPLOAD_SIZE`, `EBX_SERVER_TOKEN`)
keep working and are applied as the lowest-priority inputs **except** that
`EBX_SERVER_DISABLED_GROUPS` still wins over policy `groups` (an operator kill switch).

Python:

```python
from easy_sandbox.server import SandboxServer, ServerPolicy

policy = ServerPolicy.from_dict({
    "preset": "transfer-only",
    "endpoints": {"files_download_stream": {"paths": {"allow": ["/home/user/out"]}}},
})
SandboxServer(policy=policy).serve(9000)
```

Helpers: `ServerPolicy.preset(name, **overrides)`, `ServerPolicy.only(*endpoint_ids, paths=None,
**rule)`, `ServerPolicy.from_file(path)`, `policy.with_endpoint(selector, **rule)`,
`policy.explain(endpoint, *, scopes, path=None, op=None)` -> decision (debug aid).

Declarative (`template.yaml`):

```yaml
server:
  preset: transfer-only
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out] }
      limits: { max_bytes: 5MB }          # human sizes accepted: 5MB, 1GiB
```

Size strings (`5MB`, `1GiB`) are accepted in YAML/JSON and normalised to integers by the
loader. The client SDK validates the block (`SandboxTemplate.server`), the toolchain compiles it
to `server-policy.json` placed at `/etc/easy-sandbox/server-policy.json` in the image
(CLI follow-up). The in-container server stays stdlib-only: JSON natively, YAML only if PyYAML
happens to be installed.

Presets (all plain policy dicts, documented in `server-api.md`):
`default` (today), `transfer-only`, `read-only`, `hardened`, `locked`.

## 5. Request pipeline

```
route = match(method, raw_path)                 # no override headers/params honoured
identity = authenticate(headers)                # 401   (skipped for auth_required=False)
group gate                                      # 404 endpoint_disabled (as today)
rule gate: enabled -> scopes -> rate -> concurrency       # 404 / 403 / 429
body gate: Content-Length valid -> <= max_request_bytes   # 400 / 413 (before reading)
handler(request with request.context["policy"]=EndpointContext)
   PathGuard / limits / params enforced inside the handler on the *same* values it uses
audit(decision)
```

Handlers raise `PolicyDenied(code, message, ...)`; the dispatcher maps it to `403`.
Direct handler calls without a context (existing unit tests) use a default context that
reproduces legacy behaviour.

## 6. Discovery contract

`GET /capabilities` (authenticated) stays backward compatible (`groups` kept) and adds:
`api_version: 2`, `server_version`, `identity {id, scopes}`, `policy {preset, revision}`,
`endpoints{name -> {method, path, group, streaming, enabled, allowed, reason, scopes, limits,
paths{allow, read_only, deny_count}, params}}`, `warnings` (only for identities holding `*`).
`POST /capabilities/check` `{endpoint, path?, op?, paths?}` returns the server's authoritative
decision for a hypothetical call (policy only; never touches the filesystem) so clients do not
re-implement path rules. `revision` is a hash of the effective policy so caches can invalidate.

## 7. Error contract

All error bodies keep `{"error", "type"}` and gain `code` (stable machine string) plus
optional `endpoint`, `scope`, `retry_after`.

| HTTP | `type` | `code` examples |
|------|--------|-----------------|
| 401 | `AuthError` | `unauthorized` |
| 403 | `PolicyDenied` | `missing_scope`, `path_not_allowed`, `path_denied`, `read_only`, `symlink_denied`, `command_not_allowed`, `language_not_allowed`, `signal_not_allowed`, `shell_not_allowed`, `url_not_allowed`, `extension_not_allowed`, `env_var_not_allowed` |
| 404 | `ValueError` (kept) | `endpoint_disabled` |
| 409 | `PolicyDenied` | `file_exists` |
| 413 | `ValueError` (kept) | `payload_too_large` (+ `limit`) |
| 429 | `RateLimited` | `rate_limited`, `concurrency_limited` |

Client exceptions (new `E8xxx` family, subclassing existing classes where the semantics match so
current `except` clauses keep working): `ServerAPIError` (E8000), `ServerAuthError` (E8001,
also `AuthenticationError`), `PolicyDeniedError` (E8002; `FilePolicyDeniedError` also
`PermissionDeniedError`), `EndpointNotAvailableError` (E8003, also
`CapabilityNotSupportedError`), `PayloadTooLargeError` (E8004), `RateLimitedError` (E8005,
`retry_after`). OS-level 404/403 map to the existing `FileNotFoundError_` /
`PermissionDeniedError`; process timeouts to `CommandTimeoutError`.

## 8. Client SDK

* `easy_sandbox.api.server_client.ServerClient` — typed async client for **every** server
  endpoint with `*_sync` twins (see alignment doc); `Sandbox.server` (port 9000) and
  `Sandbox.server_at(port, token=...)` hand out instances bound to the sandbox's port URL and
  gateway headers.
* `await client.discover()` -> `ServerCapabilities` with `can(endpoint)`, `require(endpoint)`,
  `limit(endpoint, key)`, `check_path(endpoint, path, op)` (server-side check) and
  `endpoints_for(scope)`. Methods consult a populated cache and fail fast with the typed error
  *before* the network round trip; server responses remain authoritative and map to the same
  exceptions. No hidden discovery request is ever made.
* Legacy servers (no `endpoints` key): `ServerCapabilities.legacy = True`, group-level gating
  only, no pre-checks.
* `template.yaml` gains `server:` (validated by `SandboxTemplate`; unknown keys rejected).

## 9. Backward compatibility matrix

| Behaviour | Unconfigured today | After |
|-----------|--------------------|-------|
| Default groups | all but `dev_tools`, `browser` | same |
| `EBX_SERVER_TOKEN` / `X-Access-Token` | all-or-nothing | same (identity `legacy`, `*`) |
| `GET /capabilities` | `{"groups"}` | superset |
| Error bodies | `{error,type}` | superset (`code`...) |
| Relative path resolution | server CWD | same |
| Download size | unlimited (`/files/download-stream`), 100MB (`/download`) | same |
| Unsupported HTTP methods | stdlib 501 | same |
| `enable_builtin`/`_enabled_builtins` | works | same |
| Direct `ThreadingHTTPServer(..., SandboxRequestHandler)` wiring | works | works (policy attrs read via `getattr`) |

## 10. Security test plan (bypass matrix)

Path: `..`, `//`, `/./`, trailing slash, symlink to outside / inside-to-denied, symlink swap
(`symlinks: never`), `%2e%2e` and double-encoded `%252e%252e`, NUL byte, unicode look-alikes, very
long paths, duplicate `path=` query parameters, relative path vs allow root, case variants of deny
globs, archive/search/list leaking denied entries, `files_move` into/out of scope, existence
oracle ordering. Transport: method override header/param, HEAD/PUT/PATCH, `Content-Length` negative or
non-numeric, oversized body vs per-endpoint cap, chunked encoding, two `X-Access-Token` headers.
Authz: wrong/missing/other-identity token, scope escalation via `shell`, per-command scopes,
discovery listing, rate-limit and concurrency exhaustion, token-in-env exposure through `GET /env`
and child processes.

## 11. Changes after review (Draft v1 -> v2)

Full findings: [fine-grained-capabilities-review.md](fine-grained-capabilities-review.md).

* **`ServerPolicy.only(*ids)`** is normative: disables every non-core endpoint then enables the
  listed IDs; the token `"transfer"` expands to `upload`, `download`, `files_upload_stream`,
  `files_download_stream`. The `transfer-only` preset is the same thing with default size caps.
* **Path roles** for multi-path endpoints: `files_move` source is `delete`, destination is
  `write`; both must pass allow/deny/read-only. Archive/search/list re-check *every produced
  entry*.
* **Byte limits are enforced while streaming**, not only via `Content-Length`; chunked
  `Transfer-Encoding` is rejected; partial uploads are removed on abort.
* **Strict config**: unknown keys and unknown exact endpoint IDs are errors with a
  did-you-mean hint and the JSON path.
* **HTTP hardening in all modes** (bug fixes): strict `Content-Length` (non-numeric/negative/
  duplicate -> 400), zip archives never follow symlinks that leave the boundary.
* **Policy-mode only hardening**: duplicate path parameters rejected; boundary/deny check
  before any `stat` (no existence oracle); relative paths resolve against the first allow
  root; ambiguous credential headers rejected; `Authorization: Bearer` is consulted first.
* **Secrets**: in identities mode `GET /env` redacts `EBX_SERVER_*`, `EBX_*TOKEN*` and all
  `token_env` names; `env_set` refuses them; child processes get a scrubbed environment.
* **PTY WebSocket** is covered by the policy (`pty_connect`, scope `terminal:use`, header
  auth); the legacy `?token=` still works.
* **Custom routes** may declare `scopes=` and receive `request.context["policy"]`.
* **Residual risks** (documented, not closable in stdlib Python): intermediate-component symlink
  swap between check and open, hardlinks created through process endpoints, and per-IP
  brute-force throttling (left to the gateway). Lint L1 (`process`/`terminal`/`dev_tools`/
  `browser` reachable together with path scoping) covers the first two.
* **Deferred**: per-identity path scopes (OQ-2).
* `Image()` default base is unchanged; official base is opt-in (see base-image doc).
