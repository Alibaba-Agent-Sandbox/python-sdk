# Fine-Grained Capabilities, Scoping and Permissions

> Status: **v2 (reviewed)**. Draft v1 went through the two review rounds recorded in
> [fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md); the resolutions
> are folded in below and summarised in section 11.
> Scope: `agent-sandbox-server` (`agent_sandbox.server`) enforcement, `template.yaml`
> declarative config, and `agent-sandbox-client` (`agent_sandbox`) client discovery / errors / helpers.
> Companion docs: [client-server-alignment.md](client-server-alignment.md),
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md),
> [server-api.md](server-api.md).

## 1. Problem

The server exposes endpoints through **coarse capability groups** (`FILE_OPS`, `PROCESS`, ...).
Turning on `FILE_OPS` exposes eleven endpoints (list, stat, mkdir, delete, move, search,
upload, download, archive, legacy upload/download), all confined only by one process-wide
`ABX_SERVER_BASE_DIR`. Product needs finer control:

* expose **only** the upload and download endpoints;
* make download usable only from specified directories;
* per-endpoint permissions (who may call what), size limits, read-only mode;
* the same rules visible to, and enforced consistently by, the client SDK.

Non-goals: this is *not* an OS sandbox. Path scoping is an API-level control; if the same caller
may also run arbitrary processes (`shell`, `code_run`, PTY, `process_start`) it can bypass any file
rule. The server lints for this combination (see 3.9).

## 2. Design principles

1. **One engine, always on.** There is no "unconfigured" code path. No policy is the empty policy,
   which still applies the default boundary (`/home/user`) and the opt-in groups. The project is
   unreleased, so nothing is kept for compatibility.
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

Today: one optional `ABX_SERVER_TOKEN` compared against `X-Access-Token`.

* **Unchanged default.** No token -> anonymous identity with scope `*` (local mode). One
  `ABX_SERVER_TOKEN` -> identity `legacy` with scope `*` (override via `auth.legacy_scopes`).
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
  "base_dir": "/home/user",           // optional; overrides ABX_SERVER_BASE_DIR
  "groups": { "dev_tools": true },    // alias for the group's endpoint ids; a list ["dev_tools"] also works
  "defaults": { "audit": "deny", "limits": { "max_request_bytes": 10485760 } },
  "auth": {
    "tokens": [
      { "id": "uploader", "token_env": "ABX_TOKEN_UPLOADER", "scopes": ["files:write"] },
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

**A group is an alias, not a gate.** `groups: {file_ops: false}`, `groups: [agents]`,
`table.enable_group(...)`, and `ABX_SERVER_ENABLED_GROUPS=agents` all expand to the endpoint ids of
that group and become ordinary endpoint rules in one of five layers: default (opt-in groups start
off), code (`enable_group` / `disable_group`), preset, policy, environment (turn-on only). There is
no separate group gate and no group-level state. The more specific selector wins (exact id > glob >
`group:` > `@defaults`), then the later layer; at equal specificity and layer a single
`enabled: false` wins. Every denial names its rule (`policy:endpoints.shell`, `preset:read-only`,
`code:enable_group:file_ops`, `default:opt-in:browser`). `CORE` endpoints (`health`, `capabilities`,
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
`agent_sandbox.server.audit` logger as one JSON object per line: `ts, identity, endpoint,
method, decision, code, status, paths(resolved, truncated)` — never tokens, bodies or file
contents. `audit`: `off` | `deny` (default) | `all`.

### 3.8 Per-command scopes (custom commands)

`registry.command("deploy", scopes=["deploy"])` — callers need `commands:run` **and** `deploy`.
`GET /commands` lists only the commands the caller may run (discovery <= execution).

### 3.9 Lint

`ServerPolicy.lint()` returns human-readable warnings, logged at startup and printed by
`agent-sandbox-server check-config`: path scoping configured while `process`/`terminal`/
`dev_tools`/`browser` endpoints are reachable by the same scopes; allow root `/`; wildcard
token scopes with other tokens defined; `overwrite: false` without `paths.allow`; etc.

### 3.10 Subprocess environment

When `auth.tokens` is configured, child processes started by `shell*`, `process_start`,
`code_run`, `git_*` and PTY sessions receive `os.environ` **minus** `ABX_SERVER_TOKEN`,
`ABX_SERVER_POLICY*` and every `token_env` variable, so a `process:run` identity cannot read
another identity's secret. Unconfigured servers keep today's behaviour.

## 4. Configuration surfaces

Resolution order (low -> high): code defaults < well-known file
(`/etc/agent-sandbox/server-policy.json` if present) < `ABX_SERVER_POLICY_FILE` <
`ABX_SERVER_POLICY` (inline JSON) < `SandboxServer(policy=...)` (the highest present source wins; sources are
not merged). `ABX_SERVER_BASE_DIR`, `ABX_MAX_UPLOAD_SIZE`, and `ABX_SERVER_TOKEN` are read as the
lowest-priority inputs. The only group variable is `ABX_SERVER_ENABLED_GROUPS` (turn on, environment
layer); there is no variable that turns a group off.

Python:

```python
from agent_sandbox.server import SandboxServer, ServerPolicy

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
to `server-policy.json` placed at `/etc/agent-sandbox/server-policy.json` in the image
(CLI follow-up). The in-container server stays stdlib-only: JSON natively, YAML only if PyYAML
happens to be installed.

Presets (all plain policy dicts, documented in `server-api.md`):
`default` (today), `transfer-only`, `read-only`, `hardened`, `locked`.

## 5. Request pipeline

```
route = match(method, raw_path)                 # no override headers/params honoured
identity = authenticate(headers)                # 401   (skipped for auth_required=False)
rule gate: enabled -> scopes -> rate -> concurrency       # 404 endpoint_disabled(+rule) / 403 / 429
duplicate query parameters                                # 400
body gate: Content-Length valid -> <= max_request_bytes   # 400 / 413 (before reading)
handler(request with request.context["policy"]=EndpointContext)
   PathGuard / limits / params enforced inside the handler on the *same* values it uses
audit(decision)
```

Handlers raise `PolicyDenied(code, message, ...)`; the dispatcher maps it to `403`. Every handler
receives an `EndpointContext`; there is no context-less mode.

## 6. Discovery contract

`GET /capabilities` (authenticated) stays backward compatible (`groups` kept) and adds:
`api_version: 2`, `server_version`, `identity {id, scopes}`, `policy {preset, revision}`,
`groups` and `group_summary` (derived from the endpoint state), `endpoints{name -> {method, path, group,
summary, streaming, enabled, allowed, reason, rule, scopes, limits, paths{allow, read_only, deny_count},
params}}`, `warnings` (only for identities holding `*`).
`POST /capabilities/check` `{endpoint, path?, op?, paths?}` returns the server's authoritative
decision for a hypothetical call (policy only; never touches the filesystem) so clients do not
re-implement path rules. `revision` is a hash of the effective policy so caches can invalidate.

## 7. Error contract

All error bodies keep `{"error", "type"}` and gain `code` (stable machine string) plus
optional `endpoint`, `scope`, `retry_after`.

| HTTP | `type` | `code` examples |
|------|--------|-----------------|
| 401 | `AuthError` | `unauthorized` |
| 403 | `PolicyDenied` | `missing_scope`, `path_not_allowed`, `path_denied`, `read_only`, `symlink_denied`, `command_not_allowed`, `language_not_allowed`, `signal_not_allowed`, `shell_not_allowed`, `url_denied`, `extension_not_allowed`, `env_var_not_allowed`, `env_var_denied`, `process_denied` |
| 404 | `ValueError` | `endpoint_disabled` (+ `rule`) |
| 409 | `FileExistsError` | `file_exists` (upload with `overwrite: false`) |
| 413 | `ValueError` (kept) | `payload_too_large` (+ `limit`) |
| 429 | `RateLimited` | `rate_limited`, `concurrency_limited` |

Client exceptions (new `E9xxx` family, subclassing existing classes where the semantics match so
current `except` clauses keep working): `ServerAPIError` (E9000), `ServerAuthError` (E9001,
also `AuthenticationError`), `PolicyDeniedError` (E9002; `FilePolicyDeniedError` also
`PermissionDeniedError`), `EndpointNotAvailableError` (E9003, also
`CapabilityNotSupportedError`), `PayloadTooLargeError` (E9004), `RateLimitedError` (E9005,
`retry_after`). OS-level 404/403 map to the existing `FileNotFoundError_` /
`PermissionDeniedError`; process timeouts to `CommandTimeoutError`.

## 8. Client SDK

* `agent_sandbox.api.server_client.ServerClient` — typed async client for **every** server
  endpoint with `*_sync` twins (see alignment doc); `Sandbox.server` (port 9000) and
  `Sandbox.server_at(port, token=...)` hand out instances bound to the sandbox's port URL and
  gateway headers.
* `await client.discover()` -> `ServerCapabilities` with `can(endpoint)`, `require(endpoint)`,
  `limit(endpoint, key)`, `check_path(endpoint, path, op)` (server-side check) and
  `endpoints_for(scope)`. Methods consult a populated cache and fail fast with the typed error
  *before* the network round trip; server responses remain authoritative and map to the same
  exceptions. No hidden discovery request is ever made.
* `template.yaml` gains `server:` (validated by `SandboxTemplate`; unknown keys rejected).

## 9. Behaviour without a policy

| Behaviour | Value |
|-----------|-------|
| Default groups | all but `dev_tools`, `browser`, `agents` (opt-in) |
| `ABX_SERVER_TOKEN` / `X-Access-Token` or `Authorization: Bearer` | all-or-nothing; identity `legacy`, scope `*` (`anonymous` when no token is set) |
| Path boundary | `ABX_SERVER_BASE_DIR` (default `/home/user`) for every path-taking endpoint including shell `cwd`; violations are `403 path_not_allowed` |
| `GET /capabilities` | per-endpoint state, `rule`, derived `groups` and `group_summary` |
| Error bodies | `{error, type}` plus `code`, `endpoint`, `rule` where they apply |
| Relative path resolution | server CWD, then still inside the boundary |
| Unsupported HTTP methods | stdlib 501 |
| Capability switches | one layer: the endpoint rule (`enable_builtin`, `disable_builtin` and `ABX_SERVER_DISABLED_GROUPS` do not exist) |

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

Full findings: [fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md).

* **`ServerPolicy.only(*ids)`** is normative: disables every non-core endpoint then enables the
  listed IDs; the token `"transfer"` expands to `upload`, `download`, `files_upload_stream`,
  `files_download_stream`. The `transfer-only` preset is the same thing with default size caps.
* **Path roles** for multi-path endpoints: `files_move` source is `delete`, destination is
  `write`; both must pass allow/deny/read-only. Archive/search/list re-check *every produced
  entry*.
* **Byte limits**: the request body is bounded by `max_request_bytes` (default: the transfer cap)
  applied to the validated `Content-Length` *before* the body is read, `max_bytes` bounds the
  decoded payload; chunked `Transfer-Encoding` is rejected in policy mode; partial uploads are
  removed on abort. (There is no counting reader: the server reads exactly the declared length.)
* **Strict config**: unknown keys and unknown exact endpoint IDs are errors with a
  did-you-mean hint and the JSON path.
* **HTTP hardening in all modes** (bug fixes): strict `Content-Length` (non-numeric/negative/
  duplicate -> 400), zip archives never follow symlinks that leave the boundary.
* **Policy-mode only hardening**: duplicate query parameters and `Transfer-Encoding` rejected; boundary/deny check
  before any `stat` (no existence oracle); relative paths resolve against the first allow
  root; ambiguous credential headers rejected; `Authorization: Bearer` is consulted first.
* **Secrets**: in identities mode `GET /env` redacts the server's own secrets (`ABX_SERVER_*` and
  every `token_env` name); `env_set` refuses them and the `ABX_` prefix; child processes get an
  environment scrubbed of the same names only. Arbitrary user variables are never touched (legacy
  `GET /env` still returns the full environment; use `endpoints.env_get` / `groups.system` to
  restrict it).
* **PTY WebSocket** is covered by the policy (`pty_connect`, scope `terminal:use`, header
  auth); the legacy `?token=` still works.
* **Custom routes** may declare `scopes=` and receive `request.context["policy"]`.
* **Residual risks** (documented, not closable in stdlib Python): intermediate-component symlink
  swap between check and open, hardlinks created through process endpoints, and per-IP
  brute-force throttling (left to the gateway). Lint L1 (`process`/`terminal`/`dev_tools`/
  `browser` reachable together with path scoping) covers the first two.
* **Deferred**: per-identity path scopes (OQ-2).
* `Image()` default base is unchanged; official base is opt-in (see base-image doc).
