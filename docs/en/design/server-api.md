# Container-Side HTTP Server API Reference

> Complete API reference for the container-side HTTP Server (`agent_sandbox.server`).
>
> All endpoint methods, paths, parameters, request body fields, and response formats in this document
> are read directly from the implementation code under `src/agent_sandbox/server/`, staying consistent
> with the source code. Where the code does not explicitly define certain behavior, this document
> faithfully notes it rather than speculating.

---

## 1. Overview

### 1.1 Server Positioning

The container-side HTTP Server is a lightweight HTTP service that relies **solely on the Python standard library** (stdlib-only, zero third-party dependencies). It runs inside a Sandbox container and exposes file, process, terminal, system information, development tools, and browser automation capabilities to external consumers (SDK / CLI / Agent).

- Built on [`http.server.ThreadingHTTPServer`](../../../server-sdk/src/agent_sandbox/server/app.py) with a custom `BaseHTTPRequestHandler` subclass.
- Request dispatching is handled by a data-driven [`RouteTable`](../../../server-sdk/src/agent_sandbox/server/router.py), not a hard-coded `if/elif` chain.
- Each route is an endpoint with one id, declared once in [`endpoints.py`](../../../server-sdk/src/agent_sandbox/server/endpoints.py). A **Capability Group** is a name for a set of endpoint ids.
- Request/response objects are stdlib `dataclass`es ([`types.py`](../../../server-sdk/src/agent_sandbox/server/types.py)), not Pydantic models.

> Note: The "capability groups" described here are **runtime switches in the Server-side RouteTable**, which is an independent mechanism from `STANDARD_CAPABILITIES` in the SDK template layer (`models/template.py` / `api/capability.py`). Do not confuse the two.

### 1.2 Startup

**Convenience function** —
[`start()`](../../../server-sdk/src/agent_sandbox/server/app.py#L320-L334):

```python
from agent_sandbox.server import start

start(9000)  # Listen on 0.0.0.0:9000, blocking
```

**Class interface** —
[`SandboxServer`](../../../server-sdk/src/agent_sandbox/server/app.py#L215-L317) (accepts custom `registry` / `route_table`):

```python
from agent_sandbox.server import SandboxServer, CommandRegistry

registry = CommandRegistry()
# ... register custom commands ...
server = SandboxServer(host="0.0.0.0", registry=registry)
server.serve(port=9000)  # Blocks until KeyboardInterrupt / shutdown()
```

`serve()` calls `registry.freeze()` at startup to freeze the command registry, then begins accepting requests.

### 1.3 Dual-Port Architecture

The Server uses two ports:

| Port | Protocol | Purpose | Default | Override Variable |
|------|----------|---------|---------|-------------------|
| HTTP Port | HTTP/1.1 | All REST / SSE endpoints | `9000` (`serve(port=...)` parameter) | — |
| PTY Port | WebSocket | Interactive terminal (PTY) | `9001` | `ABX_PTY_PORT` |

The PTY WebSocket service starts in a background daemon thread only when the `TERMINAL` capability group is enabled (see
[`SandboxServer.serve`](../../../server-sdk/src/agent_sandbox/server/app.py#L254-L280)). `TERMINAL` is enabled by default, so the PTY service starts alongside the main service by default.

---

## 2. Capability Groups

Every route is one **endpoint** with one id (see [Fine-grained capabilities](fine-grained-capabilities.md)); the table is [`endpoints.py`](../../../server-sdk/src/agent_sandbox/server/endpoints.py). A **capability group** is a name for a set of endpoint ids. There is one switch, the endpoint rule. A group name expands to the ids it contains, in every place it is accepted (`groups:` in the policy, `enable_group()` in code, `ABX_SERVER_ENABLED_GROUPS` in the environment). There is no second gate in front of the endpoint rules.

| Capability Group | Enum Value | Endpoints | Default State | Description |
|------------------|------------|:---------:|:-------------:|-------------|
| `CORE` | `core` | 3 | **Always enabled** (cannot be disabled) | Health check, capability query and check |
| `COMMANDS` | `commands` | 2 | Enabled | Named command listing and execution |
| `FILE_OPS` | `file_ops` | 12 | Enabled | File upload/download/listing/search/archive etc. |
| `PROCESS` | `process` | 8 | Enabled | Shell execution, SSE streaming shell, background process management |
| `TERMINAL` | `terminal` | 5 REST + WS | Enabled | PTY session management + WebSocket interactive terminal |
| `SYSTEM` | `system` | 6 | Enabled | System info, environment variables, ports, packages, metrics |
| `DEV_TOOLS` | `dev_tools` | 3 | **Opt-in (off by default)** | Code execution, Git inspection |
| `BROWSER` | `browser` | 8 | **Opt-in (off by default)** | Playwright browser automation |
| `AGENTS` | `agents` | 70 | **Opt-in (off by default)** | The Agents API (`/v1/agents/...`, `/v1/vaults`, `/v1/responses`, ...) |

`TERMINAL` is enabled by default, so the PTY WebSocket service starts with the main service. It runs in a background daemon thread and only when `pty_connect` is enabled.

### 2.1 Layers

Rules for one endpoint come from five layers, merged per endpoint: default (the opt-in groups start off), code (`enable_group` / `disable_group` on the route table), preset, policy (`groups`, `defaults`, `endpoints`), and environment (`ABX_SERVER_ENABLED_GROUPS`, which can only turn groups on). The more specific selector wins (exact id, then glob, then `group:`, then `@defaults`); at equal specificity the later layer wins; inside one layer a single `enabled: false` turns the endpoint off. `CORE` (`health`, `capabilities`, `capabilities_check`) cannot be disabled: `disable_group(CapabilityGroup.CORE)` raises `ValueError`.

Every denial names the rule that denied it: the `404` body carries `code: endpoint_disabled` and `rule` (`policy:endpoints.shell`, `preset:read-only`, `code:enable_group:file_ops`, `default:opt-in:browser`).

### 2.2 Environment Variable

`ABX_SERVER_ENABLED_GROUPS` is a comma-separated list of group names (`agents,dev_tools`). It turns groups on. An unknown name stops the process with a did-you-mean message. There is no variable for turning groups off; write `groups: {process: false}` or an `endpoints` rule in the policy.

### 2.3 Code API

`RouteTable` has two code-level switches, both of which edit the code layer of the endpoint rules:

| Method | Description |
|--------|-------------|
| `enable_group(group)` | Turn on every endpoint of the group (no-op for `CORE`) |
| `disable_group(group)` | Turn off every endpoint of the group (raises `ValueError` for `CORE`) |

Template author example:

```python
from agent_sandbox.server import CapabilityGroup, default_table

table = default_table()
table.enable_group(CapabilityGroup.DEV_TOOLS)
```

`GET /capabilities` reports the state per endpoint and derives `groups` and `group_summary` from it.

---

## 3. Authentication

Authentication is step 2 of the pipeline in `SandboxRequestHandler._pipeline` ([`app.py`](../../../server-sdk/src/agent_sandbox/server/app.py)).

- The Server reads the environment variable `ABX_SERVER_TOKEN` at startup (`os.environ.get("ABX_SERVER_TOKEN") or None`).
- **Token not set**: local mode, all requests bypass authentication. The caller is the identity `anonymous`.
- **Token set**: requests must carry the token in `X-Access-Token` or `Authorization: Bearer <token>` (both accepted on every route), compared with `hmac.compare_digest` (constant-time comparison). Missing or mismatched is `401`, body `{"error": "unauthorized", "type": "AuthError"}`. Two different `X-Access-Token` values are `400` `ambiguous_credentials`.

### 3.1 Auth-Exempt Endpoints

Only `GET /health` is registered with `auth_required=False` (`GET /capabilities` and `POST /capabilities/check` always require authentication):

| Endpoint | Capability Group |
|----------|------------------|
| `GET /health` | `CORE` |

Example request with token:

```bash
curl -H "X-Access-Token: $ABX_SERVER_TOKEN" http://localhost:9000/system/info
```

### 3.2 Dispatch Order

There is one pipeline and every route goes through it, in this order:

1. Path normalization: `urlparse` followed by `path.rstrip("/") or "/"` (strip trailing slash).
2. `RouteTable.match(method, path)`: no match is `404 {"error": "Not found: <path>", "type": "ValueError"}`.
3. Authenticate (only when `route.auth_required`): failure is `401`.
4. Admission by the policy engine, for the matched endpoint: enabled (else `404 endpoint_disabled` with `rule`), scopes (`403 missing_scope`), rate and concurrency limits (`429`).
5. Duplicate query parameters (`400 duplicate_parameter`) and `Transfer-Encoding` rejection.
6. For `POST/PUT/PATCH/DELETE`, read the JSON request body, bounded by `max_request_bytes` (`413`); a parse failure is `400`.
7. Invoke the handler (path, command, URL and parameter rules apply here); `streaming=True` takes the SSE dispatch path.
8. Write the audit entry.

> Only `do_GET` / `do_POST` / `do_DELETE` are implemented. `PUT` / `PATCH` have no corresponding entry points; stdlib returns `501`.

---

## 3.3 Request/Response Data Models

Route handler inputs and outputs use stdlib `dataclass` definitions (not Pydantic), located in
[`types.py`](../../../server-sdk/src/agent_sandbox/server/types.py).

#### `ServerRequest`

The request object passed to handlers after parsing by `_dispatch`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `method` | `str` | — | HTTP method (uppercase, e.g., `"GET"`, `"POST"`) |
| `path` | `str` | — | URL path (e.g., `"/commands/greet"`) |
| `query` | `dict[str, list[str]]` | `{}` | Query parameters, each key maps to a value list (supports duplicate keys) |
| `headers` | `dict[str, str]` | `{}` | Request headers (single-value) |
| `body` | `dict[str, Any] \| None` | `None` | Parsed JSON request body; `None` when absent or non-JSON |
| `path_params` | `dict[str, str]` | `{}` | Path parameters extracted from `{param}` route templates |
| `context` | `dict[str, Any]` | `{}` | Request context injected by the dispatcher (e.g., `CommandRegistry` under the `"registry"` key) |

#### `ServerResponse`

Return type for normal (non-streaming) handlers.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | `int` | — | HTTP status code (e.g., `200`, `404`) |
| `body` | `dict[str, Any]` | `{}` | JSON-serializable response body |
| `headers` | `dict[str, str]` | `{}` | Additional response headers |

Factory methods:

| Method | Returns | Description |
|--------|---------|-------------|
| `ServerResponse.ok(data)` | `ServerResponse(200, data)` | Success response |
| `ServerResponse.error(status, message, error_type="ValueError")` | `ServerResponse(status, {"error": message, "type": error_type})` | Error response |

#### `SSEResponse`

Return type for SSE streaming handlers (`streaming=True` routes).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `status` | `int` | `200` | HTTP status code |
| `headers` | `dict[str, str]` | `{"Content-Type": "text/event-stream"}` | Response headers |
| `event_iterator` | `Any` | `None` | Iterator yielding SSE event payloads (`str` or `bytes`), flushed to the client one by one |

---

## 4. Endpoint Reference

Response bodies are uniformly JSON. Success generally returns `200`; error bodies follow the format
`{"error": "<message>", "type": "<ExceptionName>"}` (see
[`ServerResponse.error`](../../../server-sdk/src/agent_sandbox/server/types.py#L70-L88)).

### 4.1 CORE (3)

#### `GET /health`

Health check, always returns `200`, no authentication required.

Response:

```json
{"status": "ok"}
```

```bash
curl http://localhost:9000/health
```

#### `GET /capabilities`

Lists all capability groups and their enabled status (authentication required when a token is configured). Servers that run a policy (or any v2 server) add `api_version`, `server_version`, `identity`, `policy` and `endpoints` to this document, see section 10.4; the `groups` object is unchanged.

Response (`groups` is `{enum_value: bool}`):

```json
{
  "groups": {
    "core": true,
    "commands": true,
    "file_ops": true,
    "process": true,
    "terminal": true,
    "system": true,
    "dev_tools": false,
    "browser": false
  }
}
```

---

### 4.2 COMMANDS (2)

#### `GET /commands`

Lists **visible** (non-`hidden`) commands in the registry along with their parameter definitions.

Response:

```json
{
  "commands": [
    {
      "name": "hello",
      "args": [
        {"name": "name", "type": "string", "required": false, "default": "World", "description": ""}
      ]
    }
  ]
}
```

Parameter fields from
[`handle_list_commands`](../../../server-sdk/src/agent_sandbox/server/routes.py#L96-L119):
`name` / `type` / `required` / `default` / `description`.

#### `POST /commands/{name}`

Execute a registered command. The request body contains the command's keyword arguments (kwargs).

Request body example:

```json
{"name": "Qoder"}
```

Processing flow (see
[`handle_run_command`](../../../server-sdk/src/agent_sandbox/server/routes.py#L229-L269)):

1. Command does not exist → `404 {"error": "Unknown command '<name>'; available: ...", "type": "ValueError"}`.
2. Parameter validation/type coercion failure → `400` (missing required parameter, unknown parameter, type conversion failure).
3. Command function raises exception → `500 {"error": "...", "type": "<ExceptionName>"}`.
4. Success → `200 {"result": <return_value>}`.

Type coercion supports `string` / `integer` / `float` / `boolean`; boolean accepts
`true/false/yes/no/1/0` (see
[`_parse_boolean`](../../../server-sdk/src/agent_sandbox/server/routes.py#L130-L152)).

```bash
curl -X POST http://localhost:9000/commands/hello \
  -H "Content-Type: application/json" \
  -d '{"name": "Qoder"}'
# -> {"result": "Hello, Qoder!"}
```

---

### 4.3 FILE_OPS

File operations are registered in [routes_files.py](../../../server-sdk/src/agent_sandbox/server/routes_files.py). Upload and download use `/files/upload-stream` and `/files/download-stream`. All paths pass through the path guard (see §8.1).

#### `GET /files/list?path=...`

Lists directory contents. Query parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `path` | (required) | Directory path |
| `recursive` | `false` | `true/yes/1` for recursive; max recursive depth `3` (`_DEFAULT_MAX_DEPTH`) |
| `max_entries` | `1000` | Upper limit clamped to `1000` (`_DEFAULT_MAX_ENTRIES`) |

Response:

```json
{
  "entries": [
    {"name": "a.txt", "type": "file", "size": 12, "modified": "2026-09-21T00:00:00+00:00"}
  ]
}
```

`type` is `file` or `directory`; `modified` is ISO 8601 UTC. Symlinks pointing outside the base directory are skipped.
Directory not found → `404`.

#### `GET /files/stat?path=...`

Returns metadata for a single file/directory. When the file does not exist, still returns `200` with `exists=false`:

```json
{"name": "x", "path": "/home/user/x", "type": "unknown", "size": 0, "permissions": "", "modified": "", "exists": false}
```

When present: `type` is `file`/`directory`/`symlink`, `permissions` is the last three octal digits (e.g., `"644"`),
`modified` is ISO 8601 UTC, `exists=true`.

#### `POST /files/mkdir`

Creates a directory (including parents, `exist_ok=True`). Request body `{"path": "..."}`;
success `{"path": "...", "created": true}`.

#### `DELETE /files?path=...`

Deletes a file or directory (directories use `shutil.rmtree`). Success `{"path": "...", "deleted": true}`;
not found → `404`.

#### `POST /files/move`

Move/rename. Request body:

```json
{"source": "/home/user/a.txt", "destination": "/home/user/b.txt"}
```

Response `{"source": "...", "destination": "..."}`; source not found → `404`; `source`/`destination`
path escape errors are prefixed with `source: ` / `destination: ` respectively.

#### `POST /files/search`

Searches files by glob pattern (`fnmatch`). Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `path` | (required) | Search root directory |
| `pattern` | (required) | Glob pattern, e.g., `*.py` |
| `max_depth` | `5` (`_SEARCH_MAX_DEPTH`) | Maximum recursion depth |
| `max_results` | `100` (`_SEARCH_MAX_RESULTS`) | Maximum result count |

Timeout upper limit `10` seconds (`_SEARCH_TIMEOUT_SECONDS`, implemented via a timer thread). Response:

```json
{"results": [{"name": "app.py", "path": "/home/user/app.py"}], "timed_out": false}
```

#### `POST /files/upload-stream`

Chunked (64 KB) base64 upload with size limit. Request body
`{"path": "...", "content_base64": "..."}`. Exceeding the limit (default 100 MB, overridable via
`ABX_MAX_UPLOAD_SIZE`) → `413`. Success `{"path": "...", "bytes": N}`.

#### `GET /files/download-stream?path=...`

Chunked read returning base64, with an additional `bytes` field:

```json
{"path": "...", "content_base64": "<base64>", "bytes": 1024}
```

File not found → `404`.

#### `POST /files/archive`

Archives multiple paths and returns base64. Request body:

```json
{"paths": ["/home/user/dir", "/home/user/a.txt"], "format": "tar.gz"}
```

`format` supports `tar.gz` (default) or `zip`; other values → `400`. Limits: total file count
`10000` (`_ARCHIVE_MAX_FILES`), archive size `100 MB` (`_ARCHIVE_MAX_SIZE`, exceeding → `413`).
Path not found → `404`. Response:

```json
{"content_base64": "<base64>", "format": "tar.gz", "bytes": 2048}
```

---

### 4.4 PROCESS (8)

Includes `/shell` (registered in [routes.py](../../../server-sdk/src/agent_sandbox/server/routes.py#L462-L465)) and SSE streaming shell with background process management (registered in
[routes_process.py](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L268-L288)).

#### `POST /shell`

Synchronous shell command execution (`shlex.split` + `shell=False`), 300-second timeout. Request body:

```json
{"command": "ls -la /tmp"}
```

Response:

```json
{"stdout": "...", "stderr": "...", "exit_code": 0}
```

Missing/invalid `command` → `400`; timeout → `500 {"type": "TimeoutError"}`.

#### `POST /shell/stream`

Executes a command and streams output via **SSE** (`streaming=True`). Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `command` | (required) | Command string |
| `timeout` | `300` | Seconds; `<=0` or invalid falls back to `300` |
| `cwd` | (empty) | Working directory; empty means `None` |

SSE event format described in §6. Missing/invalid `command` or `shlex` parsing failure → `400` (plain JSON response).

#### `POST /process/start`

Starts a background process (`subprocess.Popen`). Request body `{"command": "...", "cwd": "..."}`.
Process limit `100` (`_MAX_PROCESSES`, exceeding → `429 {"type": "ResourceError"}`). Success:

```json
{"pid": 12345, "command": "sleep 60"}
```

#### `GET /process/list`

Lists managed background processes (cleans up exited processes before listing). Response:

```json
{"processes": [{"pid": 12345, "command": "sleep 60", "state": "running", "started_at": 1758412800.0}]}
```

`state` is `running` or `exited`.

#### `GET /process/{pid}`

Single process details. `pid` not an integer → `400`; unmanaged → `404 {"type": "NotFoundError"}`. Response:

```json
{"pid": 12345, "command": "sleep 60", "state": "exited", "started_at": 1758412800.0, "exit_code": 0}
```

`state=running` has `exit_code` as `null`.

#### `POST /process/{pid}/signal`

Sends a signal to a managed process. Request body `{"signal": 15}`.

- Allowed signal whitelist `_ALLOWED_SIGNALS = {2, 9, 15, 18, 20}` (SIGINT/SIGKILL/SIGTERM/SIGCONT/SIGTSTP);
  others → `400`.
- Sending signals to `pid == 1` or the Server's own process is denied → `403 {"type": "PermissionError"}`.
- `pid` not an integer or missing `signal` → `400`; unmanaged → `404`.

Success `{"pid": 12345, "signal": 15}`.

---

### 4.5 TERMINAL (5 REST + WebSocket)

PTY session management endpoints (registered in
[routes_pty.py](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L398-L410)). WebSocket interaction protocol described in §5.

> PTY depends on the Unix `pty` module; creating sessions on non-Unix platforms raises `OSError` (→ `500`). Session limit
> `MAX_SESSIONS = 10`, idle timeout `IDLE_TIMEOUT = 1800` seconds.

#### `POST /pty/sessions`

Creates a PTY session. Request body (all optional):

| Field | Default | Description |
|-------|---------|-------------|
| `shell` | `/bin/bash` | Shell executable |
| `cols` | `80` | Terminal columns |
| `rows` | `24` | Terminal rows |
| `env` | `null` | Additional environment variable mapping |

Response:

```json
{"session_id": "a1b2c3d4e5f6", "ws_url": "ws://localhost:9001/pty?session_id=a1b2c3d4e5f6", "pid": 4321}
```

`cols`/`rows` not integer → `400`; session limit reached → `429 {"type": "RuntimeError"}`; PTY creation failure →
`500 {"type": "OSError"}`. The port in `ws_url` comes from `ABX_PTY_PORT` (default `9001`).

#### `GET /pty/sessions`

Lists active sessions (reaps dead sessions first). Response:

```json
{
  "sessions": [
    {"id": "a1b2c3d4e5f6", "pid": 4321, "created_at": 1758412800.0, "cols": 80, "rows": 24, "alive": true}
  ]
}
```

#### `DELETE /pty/sessions/{id}`

Closes and destroys a session. Success `{"status": "closed", "session_id": "<id>"}`; missing id → `400`;
not found → `404`.

---

### 4.6 SYSTEM (6)

System information endpoints (registered in
[routes_system.py](../../../server-sdk/src/agent_sandbox/server/routes_system.py#L416-L440)). All implemented using only the standard library (no `psutil`).

#### `GET /system/info`

OS / CPU / memory / disk / Python version:

```json
{
  "os": "Linux",
  "arch": "x86_64",
  "cpu_count": 4,
  "memory_total_mb": 8192,
  "memory_available_mb": 4096,
  "disk_total_gb": 40.0,
  "disk_free_gb": 25.5,
  "python_version": "3.11.5",
  "hostname": "sandbox-01"
}
```

Memory is preferentially parsed from `/proc/meminfo`; falls back to the `resource` module on non-Linux (less precise).

#### `GET /env`

Lists environment variables. Query parameter `filter` is a comma-separated whitelist (returns only those variables). **Variables whose names contain sensitive tokens (`TOKEN`/`SECRET`/`KEY`/`PASSWORD`/`CREDENTIAL`) are always excluded** (see §8.3).

```json
{"variables": {"LANG": "C.UTF-8", "PWD": "/home/user"}}
```

#### `POST /env`

Sets environment variables. Request body `{"vars": {"KEY": "value"}}`. **Protected variables**
(`PATH`/`HOME`/`USER`/`SHELL`/`ABX_SERVER_TOKEN`) cannot be overwritten → `403 {"type": "PermissionError"}`;
`vars` not an object → `400`. Success `{"updated": ["KEY1", "KEY2"]}` (sorted).

#### `GET /ports`

Lists listening TCP ports. Preferentially parses `/proc/net/tcp` and `/proc/net/tcp6` (state `0A` = LISTEN),
falls back to `ss -tlnp` when empty. Response:

```json
{"listening": [{"port": 8080, "protocol": "tcp", "address": "0.0.0.0", "pid": null}]}
```

> `pid` is usually `null` without root privileges.

#### `GET /packages`

Lists installed packages. Query parameter `manager` is `pip` (default) or `npm`; other values → `400`.
When the command is not found (`FileNotFoundError`), returns an empty list instead of an error; timeout → `500 {"type": "TimeoutError"}`.

```json
{"manager": "pip", "packages": [{"name": "requests", "version": "2.32.0"}]}
```

#### `GET /system/metrics`

Real-time resource metrics:

```json
{
  "cpu_load_1m": 0.15, "cpu_load_5m": 0.10, "cpu_load_15m": 0.05,
  "memory_used_mb": 2048, "memory_total_mb": 8192, "memory_percent": 25.0,
  "disk_used_gb": 14.5, "disk_total_gb": 40.0, "disk_percent": 36.3,
  "uptime_seconds": 123.4
}
```

`uptime_seconds` is relative to the process import time (`_BOOT_TIME`).

---

### 4.7 DEV_TOOLS (3) — Opt-in

Code execution and Git inspection (registered in
[routes_devtools.py](../../../server-sdk/src/agent_sandbox/server/routes_devtools.py#L385-L397)). Must
`default_table().enable_group(CapabilityGroup.DEV_TOOLS)` before use, otherwise requests return `404` (group disabled).

#### `POST /code/run`

Executes code in a subprocess. Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `code` | (required) | Source code string |
| `language` | `python` | `python` / `node` / `bash`; others → `400` |
| `timeout` | `30` | Seconds; upper limit `300` (`_MAX_TIMEOUT`), `<=0` falls back to `30` |

Language mapping: `python`→`python3 -c`, `node`→`node -e`, `bash`→`bash -c`. Response:

```json
{"stdout": "hello\n", "stderr": "", "exit_code": 0, "language": "python", "execution_time_ms": 42.5}
```

Timeout → `408 {"type": "TimeoutError"}`; runtime not found → `500 {"type": "FileNotFoundError"}`.

#### `GET /git/status?path=...`

Parses `git status --porcelain -b`. Query parameter `path` (default `.`). Path containing `..` segment → `400`.
git not installed → `500`; timeout → `408`; git returns non-zero → `400 {"type": "GitError"}`. Response:

```json
{"branch": "main", "clean": false, "files": [{"path": "app.py", "status": "modified"}]}
```

`status` values: `modified`/`added`/`deleted`/`renamed`/`untracked`/`copied`/`unmerged`.

#### `GET /git/diff?path=...`

Returns `git diff` text and statistics. Query parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `path` | `.` | Working directory (containing `..` → `400`) |
| `staged` | `false` | Uses `--staged` when `true` |
| `file` | (empty) | Restrict to a single file (containing `..` → `400`) |

Diff text exceeding 1 MB (`_MAX_DIFF_BYTES`) is truncated with `... (truncated at 1MB)` appended. Response:

```json
{"diff": "diff --git ...", "stats": {"files_changed": 3, "insertions": 10, "deletions": 2}}
```

---

### 4.8 BROWSER (8) — Opt-in

Playwright headless browser control (registered in
[routes_browser.py](../../../server-sdk/src/agent_sandbox/server/routes_browser.py#L484-L516)). Must
`default_table().enable_group(CapabilityGroup.BROWSER)` before use.

> **Playwright lazy loading and 503 degradation**: Playwright is imported and started only on first use
> ([`_get_playwright`](../../../server-sdk/src/agent_sandbox/server/routes_browser.py#L60-L96)).
> If `playwright` is not installed, all browser endpoints return
> `503 {"error": "Playwright is not installed. ...", "type": "RuntimeError"}`.
> The page is a process-wide shared singleton (same `page`), and operations are serialized by `_browser_lock`.

#### `POST /browser/navigate`

Navigates to a URL. Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `url` | (required) | Target URL |
| `wait_until` | `networkidle` | Playwright wait condition |
| `timeout` | `30000` | Milliseconds; `<=0` falls back to `30000` |

Response `{"url": "...", "title": "...", "status": 200}`.

#### `POST /browser/screenshot`

Takes a screenshot. Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `selector` | `null` | If specified, captures that element; element not found → `404` |
| `full_page` | `true` | Full-page screenshot (when no selector) |
| `format` | `png` | `png` or `jpeg` (others fall back to `png`) |

Response `{"image_base64": "...", "width": 1280, "height": 720}`.

#### `GET /browser/content?type=...`

Gets page content. Query parameter `type`: `html` (default, `page.content()`) or `text`
(`page.inner_text("body")`). Response `{"content": "...", "url": "...", "title": "..."}`.

#### `POST /browser/click`

Clicks an element. Request body `{"selector": "#btn", "timeout": 5000}` (`timeout` in milliseconds, `<=0` falls back to `5000`).
Response `{"clicked": true, "selector": "#btn"}`.

#### `POST /browser/type`

Types text into an element. Request body:

| Field | Default | Description |
|-------|---------|-------------|
| `selector` | (required) | Target selector |
| `text` | (required) | Input text |
| `delay` | `50` | Per-character delay (milliseconds), `<0` falls back to `50` |
| `clear` | `false` | Whether to clear before typing (`page.fill("")`) |

Response `{"typed": true, "selector": "...", "text": "..."}`.

#### `POST /browser/evaluate`

Executes JavaScript. Request body `{"script": "document.title", "timeout": 10000}`
(`timeout` in milliseconds, used as default timeout, `<=0` falls back to `10000`). Response `{"result": <JS_return_value>}`.

#### `POST /browser/pdf`

Generates a PDF. Request body `{"format": "A4", "landscape": false}`. Response
`{"pdf_base64": "...", "pages": 1}` (`pages` is a rough count based on `/Type /Page` occurrences, at least `1`).

#### `GET /browser/console`

Returns collected console logs and **clears the buffer**. Response:

```json
{"logs": [{"type": "log", "text": "hello", "timestamp": 1758412800.0}]}
```

Log buffer limit `1000` entries (`_MAX_CONSOLE_LOGS`).

---

## 5. WebSocket PTY Terminal Protocol

Implementation in
[`pty_ws_handler`](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L426-L503)
and [`start_pty_server`](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L546-L571).
The WebSocket service depends on the `websockets` library and runs on a separate port (default `9001`).

### 5.1 Connection URL

```
ws://<host>:<pty_port>/pty?session_id=<session_id>
```

`session_id` must come from a prior `POST /pty/sessions`. Missing `session_id` → server closes with code
`1008` and message `"Missing session_id parameter"`; unknown session → `1008` + `"Unknown session: <id>"`.

### 5.2 Client → Server Messages (JSON Text Frames)

| `type` | Fields | Description |
|--------|--------|-------------|
| `input` | `data` (string) | Input to write to the shell (UTF-8 encoded) |
| `resize` | `cols`, `rows` (integers) | Resize terminal; non-integer values cause the message to be ignored |
| `signal` | `signal` (string) | Send signal to the shell process group |

`signal` value mapping (`_SIGNAL_MAP`): `SIGINT` / `SIGTERM` / `SIGKILL` / `SIGHUP` / `SIGQUIT`;
unrecognized signal names are ignored. Invalid JSON frames are silently discarded.

```json
{"type": "input",  "data": "ls -la\n"}
{"type": "resize", "cols": 120, "rows": 40}
{"type": "signal", "signal": "SIGINT"}
```

### 5.3 Server → Client Messages (JSON Text Frames)

| `type` | Fields | Description |
|--------|--------|-------------|
| `output` | `data` (string) | PTY output (UTF-8, `errors="replace"`) |
| `event` | `event`, `session_id`, `pid`? | Lifecycle events |

`event` values:

- `started`: Sent immediately after connection, includes `session_id` and `pid`.
- `exited`: Sent after shell process ends, includes `session_id`.

```json
{"type": "output", "data": "total 0\n"}
{"type": "event",  "event": "started", "session_id": "a1b2c3d4e5f6", "pid": 4321}
{"type": "event",  "event": "exited",  "session_id": "a1b2c3d4e5f6"}
```

### 5.4 Session Lifecycle

1. `POST /pty/sessions` creates a session, returning `session_id` and `ws_url`.
2. Connect to `ws_url`; server pushes `started` event, then the background read loop continuously forwards `output`.
3. Client sends `input`/`resize`/`signal` messages.
4. Shell exit triggers `exited` push; or call `DELETE /pty/sessions/{id}` to actively destroy.

---

## 6. SSE Streaming Shell

Endpoint: `POST /shell/stream` (PROCESS group). Implementation in
[`_handle_shell_stream`](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L64-L121).
Response `Content-Type: text/event-stream` ([`SSEResponse`](../../../server-sdk/src/agent_sandbox/server/types.py#L91-L107)),
events flushed one by one as standard SSE frames `event: <name>\ndata: <json>\n\n`.

### 6.1 Event Types (Confirmed from Code)

| `event` | `data` Structure | Trigger |
|---------|------------------|---------|
| `stdout` | `{"data": "<line_text>"}` | Each line read from standard output (trailing `\n` stripped) |
| `stderr` | `{"data": "<line_text>"}` | After stdout is fully read, lines from standard error |
| `error` | `{"error": "<message>"}` | Process startup failure, or timeout (`{"error": "timeout"}`) |
| `exit` | `{"exit_code": <int>}` | Process ended (an `exit` event is also sent after timeout) |

> Implementation note: stdout and stderr are read **sequentially — all stdout lines first, then stderr** — not interleaved in real time.
> Timeout detection is based on `time.monotonic()` within the stdout read loop.

### 6.2 Example

```bash
curl -N -X POST http://localhost:9000/shell/stream \
  -H "Content-Type: application/json" \
  -d '{"command": "echo hello && echo err >&2", "timeout": 30}'
```

```
event: stdout
data: {"data": "hello"}

event: stderr
data: {"data": "err"}

event: exit
data: {"exit_code": 0}

```

---

## 7. Extensibility (Template Author Guide)

The Server's routes and commands can be extended by template `commands.py` without modifying SDK source code. See the complete example at
[`examples/templates/python-hello/commands.py`](../../../examples/templates/python-hello/commands.py).

### 7.1 Registering Custom HTTP Routes

Use the [`RouteTable.route()`](../../../server-sdk/src/agent_sandbox/server/router.py#L175-L204) decorator (or `register()`).
Path templates support `{param}` placeholders, compiled to named capture groups `(?P<param>[^/]+)`, accessible via
`request.path_params`:

```python
from agent_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request) -> ServerResponse:
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})
```

`route()` / `register()` keyword arguments: `group` (required), `auth_required` (default `True`),
`streaming` (default `False`), `name` (default `"<METHOD> <path>"`). Routes match in registration order.

#### Custom SSE Streaming Endpoints

When a route is registered with `streaming=True`, the handler should return an
[`SSEResponse`](../../../server-sdk/src/agent_sandbox/server/types.py#L91-L107) whose
`event_iterator` yields standard SSE frame format strings (refer to the implementation in
[`routes_process.py`](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L64-L121)):

```python
import json
from agent_sandbox.server import CapabilityGroup, default_table
from agent_sandbox.server.types import SSEResponse, ServerResponse

table = default_table()

@table.route("POST", "/my/stream", group=CapabilityGroup.COMMANDS, streaming=True)
def my_stream(request) -> SSEResponse | ServerResponse:
    body = request.body or {}
    count = body.get("count", 3)
    if not isinstance(count, int) or count <= 0:
        return ServerResponse.error(400, "Invalid 'count'", "ValueError")

    def event_gen():
        for i in range(count):
            yield f"event: progress\ndata: {json.dumps({'step': i + 1})}\n\n"
        yield f"event: done\ndata: {json.dumps({'total': count})}\n\n"

    return SSEResponse(event_iterator=event_gen())
```

The client will receive a `Content-Type: text/event-stream` response with events flushed one by one.

#### Auth-Exempt Endpoints

Setting `auth_required=False` makes an endpoint bypass authentication even when `ABX_SERVER_TOKEN` is configured (the built-in
`GET /health` uses this mode):

```python
from agent_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/public/status", group=CapabilityGroup.COMMANDS, auth_required=False)
def public_status(request) -> ServerResponse:
    return ServerResponse.ok({"status": "running", "public": True})
```

> Note: Auth-exempt endpoints are still subject to capability group gating; if their capability group is disabled, they return `404`.

### 7.2 Registering Custom Commands

A named command has one mechanism: register a function with the module-level [`command`](../../../server-sdk/src/agent_sandbox/server/registry.py) decorator. `GET /commands` lists it and `POST /commands/{name}` runs it. When `args` is not explicitly provided, parameter types are **inferred from the function signature** (`int`→`integer`, `float`→`float`, `bool`→`boolean`, others→`string`) along with required status (no default value means required):

```python
from agent_sandbox.server import command, start

@command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"

@command(hidden=True)                    # Executable but not listed in GET /commands
def _debug_info() -> dict:
    import platform
    return {"python": platform.python_version()}

start(9000)
```

- `hidden=True`: The command can still be executed via `POST /commands/{name}`, but is excluded from the `GET /commands` listing.
- `scopes=(...)`: scopes the caller must hold; a caller without them neither sees nor runs the command.
- The registry is frozen when the server starts; register at import time.
- A private `CommandRegistry()` can be passed to `SandboxServer(registry=...)` for tests.

`CommandArg`'s `type` must be one of `string`/`integer`/`float`/`boolean`, otherwise the constructor raises `ValueError`.

---

## 8. Security Model

### 8.1 Path Traversal Protection

Every endpoint that takes a path (file routes, the `cwd` of `/shell` and `/process/start`, git `path`) resolves it through one `PathGuard` ([`guard.py`](../../../server-sdk/src/agent_sandbox/server/guard.py)), built from the endpoint's `paths` rule. The default boundary is `ABX_SERVER_BASE_DIR` (default `/home/user`); a policy can set `base_dir` or per-endpoint `paths.allow`, `paths.deny`, `paths.read_only` and `paths.symlinks`. The guard `realpath`s the path, always denies `/proc`, `/sys` and `/dev`, refuses a root of `/`, and opens files with `O_NOFOLLOW` on the final component. A violation is `403 {"code": "path_not_allowed"}` (or `path_denied`, `read_only`, `symlink_denied`); there is no existence oracle.

- `/files/list`, search and archive skip entries the guard denies and symlinks pointing outside the boundary.

### 8.2 Signal Whitelist

- `POST /process/{pid}/signal` only allows `_ALLOWED_SIGNALS = {2, 9, 15, 18, 20}`;
  and denies signals to `pid == 1` or the Server's own process (`403`).
- WebSocket PTY `signal` messages only accept `_SIGNAL_MAP` entries:
  `SIGINT`/`SIGTERM`/`SIGKILL`/`SIGHUP`/`SIGQUIT`, targeting the shell process group.

### 8.3 Environment Variable Protection and Redaction

- **Redaction (`GET /env`)**: Variables whose names contain `_ENV_BLACKLIST_TOKENS`
  (`TOKEN`/`SECRET`/`KEY`/`PASSWORD`/`CREDENTIAL`, case-insensitive) are always excluded from the response.
- **Protection (`POST /env`)**: `_PROTECTED_ENV_VARS`
  (`PATH`/`HOME`/`USER`/`SHELL`/`ABX_SERVER_TOKEN`) cannot be overwritten; matching triggers `403`.
- **Policy mode**: the server's own secrets (`ABX_SERVER_*` and every configured `token_env` name) are also removed from the environment of child processes (`shell`, `process_start`, `code_run`, git, PTY) and refused by `POST /env`.

### 8.4 Other Limits

| Limit | Value | Location |
|-------|-------|----------|
| shell / code / git commands | `shell=False` + argument vector execution | Various handlers |
| `/shell` timeout | 300s | routes.py |
| `/code/run` timeout | Default 30s, max 300s | routes_devtools.py |
| Upload size limit | 100 MB (`ABX_MAX_UPLOAD_SIZE` adjustable) | routes_files.py |
| Archive file count/size | 10000 / 100 MB | routes_files.py |
| Background process limit | 100 | routes_process.py |
| PTY session limit / idle timeout | 10 / 1800s | routes_pty.py |
| Authentication comparison | `hmac.compare_digest` (constant-time) | app.py |

---

## 9. Configuration Reference (Environment Variable Summary)

| Environment Variable | Default | Purpose | Read Location |
|---------------------|---------|---------|---------------|
| `ABX_SERVER_TOKEN` | (unset = no auth) | Authentication token; when set, requires matching `X-Access-Token` header | [app.py#L43](../../../server-sdk/src/agent_sandbox/server/app.py#L43) |
| `ABX_SERVER_BASE_DIR` | `/home/user` | File endpoint path safety root directory | [routes.py#L54-L55](../../../server-sdk/src/agent_sandbox/server/routes.py#L54-L55) |
| `ABX_SERVER_ENABLED_GROUPS` | (empty) | Comma-separated groups to turn on (`agents,dev_tools`); the only group variable | [policy.py](../../../server-sdk/src/agent_sandbox/server/policy.py) |
| `ABX_PTY_PORT` | `9001` | PTY WebSocket port, also written into `ws_url` | [app.py#L247](../../../server-sdk/src/agent_sandbox/server/app.py#L247) / [routes_pty.py#L362](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L362) |
| `ABX_MAX_UPLOAD_SIZE` | `104857600` (100 MB) | `/files/upload-stream` upload byte limit | [routes_files.py#L39](../../../server-sdk/src/agent_sandbox/server/routes_files.py#L39) |

> The HTTP port is not controlled by an environment variable; it is a `start(port=...)` / `SandboxServer.serve(port=...)` parameter (default `9000`).

---

---

## 10. Fine-grained capability management (v2)

Design and rationale: [fine-grained-capabilities.md](fine-grained-capabilities.md); review log:
[fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md). An unconfigured server runs the same engine with the default policy (opt-in groups off, paths under the base directory).

### 10.1 Configuration sources

First match wins: `SandboxServer(policy=...)` / `serve --policy FILE --preset NAME` ->
`ABX_SERVER_POLICY` (inline JSON) -> `ABX_SERVER_POLICY_FILE` ->
`/etc/agent-sandbox/server-policy.json` -> none (the empty policy; the engine still runs). The `template.yaml` `server:` block is the
same document, compiled to JSON by tooling. Unknown keys and unknown endpoint ids are startup
errors with a did-you-mean hint. Validate with `agent-sandbox-server check-config --policy FILE
[--strict] [--json] [--explain ENDPOINT --path P --scopes S --op read]`.

```yaml
server:
  preset: transfer-only          # default | transfer-only | read-only | hardened | locked
  base_dir: /home/user
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out], deny: ["**/.git/**"] }
      limits: { max_bytes: 5MB, rate_per_minute: 60 }
    files_upload_stream:
      paths: { allow: [/home/user/in] }
      params: { overwrite: false, deny_extensions: [.sh, .so] }
      limits: { max_bytes: 20MB }
  auth:
    tokens:
      - { id: ci,    token_env: CI_TOKEN,    scopes: ["files:read"] }
      - { id: admin, token_sha256: "<hex>", scopes: ["*"] }
```

Rule keys per endpoint (or in `defaults`): `enabled`, `scopes`, `paths{allow, deny, read_only,
symlinks}`, `limits{max_bytes, max_request_bytes, max_entries, max_duration_seconds,
max_output_bytes, timeout_seconds, rate_per_minute, max_concurrency}`, `params{overwrite,
allow_extensions, deny_extensions, allow_commands, deny_commands, languages, allowed_signals,
url_allow, url_deny, block_private_networks, shells, env_deny, allow_vars, deny_vars}`, `audit`
(`off|deny|all`). Sizes accept `5MB`, `1GiB`.

### 10.2 Scopes

Identities hold scopes (`files:read`, `files:write`, `files:delete`, `process:run`,
`process:manage`, `terminal:use`, `system:read`, `system:write`, `devtools:run`, `browser:use`,
`commands:run`, `commands:run:<name>`, `core:read` (implicit), `*`). Each endpoint requires a
documented scope (`files_move` requires `files:write` **and** `files:delete`); a rule's `scopes`
overrides it. If no explicit token list is configured, `ABX_SERVER_TOKEN` supplies a current policy token with identity `server` and scope `*`.

### 10.3 Error codes

Bodies keep `{"error", "type"}` and add `code` (+ `endpoint`, `scope`, `limit`, `retry_after`):

| HTTP | `type` | `code` |
|------|--------|--------|
| 400 | `ValueError` | `ambiguous_credentials`, `duplicate_parameter`, `unsupported_encoding` (a malformed `Content-Length` is a plain 400 without `code`) |
| 401 | `AuthError` | `unauthorized` |
| 403 | `PolicyDenied` | `missing_scope`, `path_not_allowed`, `path_denied`, `read_only`, `symlink_denied`, `command_not_allowed`, `language_not_allowed`, `signal_not_allowed`, `shell_not_allowed`, `url_denied`, `extension_not_allowed`, `env_var_not_allowed`, `env_var_denied`, `process_denied` |
| 404 | `ValueError` | `endpoint_disabled` (identical to "unknown route" for callers lacking discovery rights) |
| 409 | `FileExistsError` | `file_exists` (upload with `overwrite: false`) |
| 413 | `ValueError` | `payload_too_large` (+ `limit`) |
| 429 | `RateLimited` | `rate_limited`, `concurrency_limited` (+ `Retry-After`) |

A disabled endpoint always carries `code: endpoint_disabled` and `rule`, whether or not a policy file is loaded.

### 10.4 Discovery

`GET /capabilities` (v2 fields): `api_version: 2`, `server_version`, `identity {id, scopes}`,
`policy {preset, revision}`, `groups` and `group_summary` (derived), `endpoints{name -> {method, path, group, summary, streaming, enabled, allowed,
reason, rule, scopes, limits, paths, params}}`, `warnings`. `POST /capabilities/check` with
`{"endpoint", "path"?, "op"?, "paths"?}` returns the policy decision for a hypothetical call; it is
policy-only and never touches the filesystem (no existence oracle).

### 10.5 New and extended endpoints (client/server alignment)

| Endpoint | Group | Notes |
|----------|-------|-------|
| `GET /files/watch?path=&recursive=&interval=&timeout=` | FILE_OPS | SSE: `ready`, `change{type: created\|modified\|deleted, path, is_dir}`, `end`; polling, bounded by `limits.max_duration_seconds` |
| `POST /process/{pid}/stdin` | PROCESS | body `{data \| data_base64, eof}`; process must be started with `stdin: true` (409 otherwise) |
| `GET /process/{pid}/output?since=&wait=` | PROCESS | cursor-based events `{seq, stream, data}`, `next`, `state`, `exit_code`, `dropped`; needs `capture_output: true` |
| `GET /pty/sessions/{id}` | TERMINAL | session metadata |
| `POST /pty/sessions/{id}/resize` | TERMINAL | `{cols, rows}` (1..1000) |
| `POST /capabilities/check` | CORE | see 10.4 |
| `POST /shell`, `/shell/stream` | PROCESS | additive `cwd`, `env`, `timeout` parameters |
| `POST /process/start` | PROCESS | additive `env`, `capture_output`, `stdin` |

The full list, with the 70 Agents routes, is in the appendix.

### 10.6 Container entrypoint

`agent-sandbox-server serve [--host --port --pty-port --commands FILE|MODULE --policy FILE --preset
NAME --base-dir DIR]`, `healthcheck [--host --port --timeout]` (exit 0/1, for `ready_cmd` and Docker
`HEALTHCHECK`), `check-config`, `version`. Base image contract:
[base-image-and-server-sdk.md](base-image-and-server-sdk.md).

---

## Appendix: Endpoint Count Verification

The declaration table `endpoints.py` has 118 endpoints: 117 HTTP routes and the PTY WebSocket (`pty_connect`, `ws://host:9001/pty?session_id=...`).

| Capability Group | Endpoints | Endpoint List |
|------------------|:---------:|---------------|
| CORE | 3 | `GET /health`, `GET /capabilities`, `POST /capabilities/check` |
| COMMANDS | 2 | `GET /commands`, `POST /commands/{name}` |
| FILE_OPS | 12 | `POST /upload`, `GET /download`, `GET /files/list`, `GET /files/stat`, `POST /files/mkdir`, `DELETE /files`, `POST /files/move`, `POST /files/search`, `POST /files/upload-stream`, `GET /files/download-stream`, `POST /files/archive`, `GET /files/watch` |
| PROCESS | 8 | `POST /shell`, `POST /shell/stream`, `POST /process/start`, `GET /process/list`, `GET /process/{pid}`, `POST /process/{pid}/signal`, `POST /process/{pid}/stdin`, `GET /process/{pid}/output` |
| TERMINAL | 6 | `POST /pty/sessions`, `GET /pty/sessions`, `GET /pty/sessions/{id}`, `POST /pty/sessions/{id}/resize`, `DELETE /pty/sessions/{id}`, `WS /pty` |
| SYSTEM | 6 | `GET /system/info`, `GET /env`, `POST /env`, `GET /ports`, `GET /packages`, `GET /system/metrics` |
| DEV_TOOLS | 3 | `POST /code/run`, `GET /git/status`, `GET /git/diff` |
| BROWSER | 8 | `POST /browser/navigate`, `POST /browser/screenshot`, `GET /browser/content`, `POST /browser/click`, `POST /browser/type`, `POST /browser/evaluate`, `POST /browser/pdf`, `GET /browser/console` |
| AGENTS | 70 | 70 routes under `/v1/agents/...`, `/v1/vaults`, `/v1/responses`, `/v1/models`, `/v1/files`, `/v1/webhook_endpoints`; see the [Agents API reference](../reference/agents-api.md) |
