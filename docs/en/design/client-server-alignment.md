# Client / Server Alignment: Gap Matrix

> Status: **v2 (reviewed; see fine-grained-capabilities-review.md)** — audit of every `agent-sandbox-server` route against `agent-sandbox-client`
> (`api/`, `protocol/`) and the envd (E2B) protocol the client otherwise speaks. The "Status" column
> is updated when the work lands (see the end of this file for the final tally).
> Related: [fine-grained-capabilities.md](fine-grained-capabilities.md).

## 1. The two data planes

| Plane | Process | Port | Who talks to it | Protocol |
|-------|---------|------|-----------------|----------|
| **envd** (platform-injected, in the official base image) | `/.fce2b/envd` | 49983 | `Sandbox.commands/files/code/get_terminal` | Connect RPC + `GET/POST /files` |
| **SandboxServer** (`agent-sandbox-server`, template-authored) | `agent_sandbox.server` | 9000 (+ PTY WS 9001) | `Sandbox.run(name)` / `list_commands()`, plus the typed `Sandbox.server` client | plain HTTP/JSON, SSE, WS |

Before this work the client reached exactly **two** of the ~45 server routes (`GET /commands`,
`POST /commands/{name}`). Everything else was server-only and unreachable from the SDK.
Conversely, the client's envd-oriented surface has features the server does not offer.

Decision: the server is **not** an envd clone. Instead the client gets a typed
`ServerClient` (`Sandbox.server`) covering every server route, and the server grows the handful
of endpoints needed so that its surface is a *functional superset of the envd-facing client
modules where that makes sense* (watch, background-process IO, PTY control). Deliberate
asymmetries are justified in section 4.

## 2. Server routes -> client coverage

Legend — Status: **NEW** = added by this work, **OK** = already aligned, **N/A** = deliberately
one-sided (section 4).

### 2.1 Core / commands

| Server route | Endpoint ID | Scope | Client (before) | Client (after) | Status |
|--------------|-------------|-------|-----------------|----------------|--------|
| `GET /health` | `health` | — | — | `ServerClient.health()` | NEW |
| `GET /capabilities` | `capabilities` | core:read | — | `ServerClient.discover()` -> `ServerCapabilities` | NEW |
| `POST /capabilities/check` | `capabilities_check` | core:read | — | `ServerClient.check()` / `caps.check_path()` | NEW (server+client) |
| `GET /commands` | `list_commands` | commands:list | `Sandbox.list_commands()` | `server.commands.list()` -> `ServerCommand[]`; `Sandbox.list_commands` is a thin wrapper | NEW typed |
| `POST /commands/{name}` | `run_command` | commands:run | `Sandbox.run(name, **kw)` | `server.commands.run(name, **kw)`; `Sandbox.run` is a thin wrapper | NEW typed + errors |

### 2.2 Files

| Server route | Endpoint ID | envd/client analogue | Client (after) | Status |
|--------------|-------------|----------------------|----------------|--------|
| `GET /files/list` | `files_list` | `files.list` (ListDir) | `server.files.list(path, recursive, max_entries)` | NEW |
| `GET /files/stat` | `files_stat` | `files.get_info`, `files.exists` | `server.files.stat(path)`, `.exists(path)` | NEW |
| `POST /files/mkdir` | `files_mkdir` | `files.make_dir` | `server.files.mkdir(path)` | NEW |
| `DELETE /files` | `files_delete` | `files.remove` | `server.files.delete(path)` | NEW |
| `POST /files/move` | `files_move` | `files.move/rename` | `server.files.move(src, dst)` | NEW |
| `POST /files/search` | `files_search` | — (no envd analogue) | `server.files.search(path, pattern, ...)` | NEW |
| `POST /files/upload-stream` | `files_upload_stream` | `files.write/upload` | `server.files.upload(path, data)`, `.upload_file(local, remote)` | NEW |
| `GET /files/download-stream` | `files_download_stream` | `files.read/download` | `server.files.download(path)`, `.read_text`, `.download_file` | NEW |
| `POST /files/archive` | `files_archive` | — | `server.files.archive(paths, format)` | NEW |
| `GET /files/watch` | `files_watch` | `files.watch` (WatchDir) | `server.files.watch(path)` -> async iterator of `ServerWatchEvent` (a `WatchEvent` subclass with `is_dir`) | NEW server + client |
| `POST /upload` (legacy) | `upload` | — | `server.files.upload_legacy(path, data)` | NEW (documented legacy) |
| `GET /download` (legacy) | `download` | — | `server.files.download_legacy(path)` | NEW (documented legacy) |

### 2.3 Processes

| Server route | Endpoint ID | envd/client analogue | Client (after) | Status |
|--------------|-------------|----------------------|----------------|--------|
| `POST /shell` | `shell` | `commands.run` | `server.process.shell(command, cwd, env, timeout)` | NEW; server gains `cwd`, `env`, `timeout` (additive) |
| `POST /shell/stream` (SSE) | `shell_stream` | `commands.stream` | `server.process.shell_stream(...)` async iterator of `ShellEvent`; `.run_stream(on_stdout=...)` | NEW; server gains `env` (additive) |
| `POST /process/start` | `process_start` | `commands.start` (background) | `server.process.start(command, cwd, env, capture_output, stdin)` | NEW; server gains `env`, `capture_output`, `stdin` (default off = today) |
| `GET /process/list` | `process_list` | `commands.list` | `server.process.list()` | NEW |
| `GET /process/{pid}` | `process_detail` | `commands.connect` (status part) | `server.process.get(pid)` | NEW |
| `POST /process/{pid}/signal` | `process_signal` | `commands.send_signal/kill` | `server.process.signal(pid, sig)`, `.kill(pid)` | NEW |
| `POST /process/{pid}/stdin` | `process_stdin` | `commands.send_stdin` | `server.process.send_stdin(pid, data)` | NEW server + client |
| `GET /process/{pid}/output` | `process_output` | `commands.connect` (output part) | `server.process.output(pid, since, wait)` | NEW server + client |

### 2.4 Terminal

| Server route | Endpoint ID | Client analogue | Client (after) | Status |
|--------------|-------------|-----------------|----------------|--------|
| `POST /pty/sessions` | `pty_create_session` | `Sandbox.get_terminal` | `server.pty.create(...)` | NEW |
| `GET /pty/sessions` | `pty_list_sessions` | — | `server.pty.list()` | NEW |
| `GET /pty/sessions/{id}` | `pty_detail` | — | `server.pty.get(id)` | NEW server + client |
| `POST /pty/sessions/{id}/resize` | `pty_resize` | `TerminalSession.resize` | `server.pty.resize(id, cols, rows)` | NEW server + client |
| `DELETE /pty/sessions/{id}` | `pty_delete_session` | `TerminalSession.close` | `server.pty.delete(id)` | NEW |
| WS `:9001/pty?session_id=` | (scope terminal:use) | `TerminalSession` speaks the *envd* `/terminal` path | `server.pty.connect(id)` -> `PtyConnection` (async context manager speaking the server's JSON protocol: `send`, `resize`, `signal`, `recv`, `expect`, message iteration) | NEW |

### 2.5 System

| Server route | Endpoint ID | envd analogue | Client (after) | Status |
|--------------|-------------|---------------|----------------|--------|
| `GET /system/info` | `system_info` | — | `server.system.info()` | NEW |
| `GET /system/metrics` | `system_metrics` | envd `GET /metrics` | `server.system.metrics()` | NEW |
| `GET /env` | `env_get` | envd `GET /envs` | `server.system.env(names)` | NEW |
| `POST /env` | `env_set` | — | `server.system.set_env(vars)` | NEW |
| `GET /ports` | `ports` | — (`Sandbox.network` computes URLs locally) | `server.system.ports()` | NEW |
| `GET /packages` | `packages` | — | `server.system.packages(manager)` | NEW |

### 2.6 Developer tools and browser (opt-in groups)

| Server route | Endpoint ID | Client analogue | Client (after) | Status |
|--------------|-------------|-----------------|----------------|--------|
| `POST /code/run` | `code_run` | `sandbox.code.run` (envd code-interpreter, stateful) | `server.devtools.run_code(code, language, timeout)` | NEW (stateless; see N/A-2) |
| `GET /git/status` | `git_status` | — | `server.devtools.git_status(path)` | NEW |
| `GET /git/diff` | `git_diff` | — | `server.devtools.git_diff(path, staged, file)` | NEW |
| `POST /browser/navigate` | `browser_navigate` | — | `server.browser.navigate(url, ...)` | NEW |
| `POST /browser/screenshot` | `browser_screenshot` | — | `server.browser.screenshot(...)` -> bytes | NEW |
| `GET /browser/content` | `browser_content` | — | `server.browser.content(type)` | NEW |
| `POST /browser/click` | `browser_click` | — | `server.browser.click(selector)` | NEW |
| `POST /browser/type` | `browser_type` | — | `server.browser.type(selector, text)` | NEW |
| `POST /browser/evaluate` | `browser_evaluate` | — | `server.browser.evaluate(script)` | NEW |
| `POST /browser/pdf` | `browser_pdf` | — | `server.browser.pdf(...)` -> bytes | NEW |
| `GET /browser/console` | `browser_console` | — | `server.browser.console()` | NEW |

## 3. Client/envd features -> server coverage (the other direction)

| Client capability (envd) | Server equivalent | Action |
|--------------------------|-------------------|--------|
| `files.list/exists/get_info/make_dir/remove/move/rename` | `files_*` | covered (aligned via `ServerClient.files`) |
| `files.read/read_bytes/write/upload/download` | `files_download_stream` / `files_upload_stream` (base64 JSON) | covered |
| `files.watch` (WatchDir stream) | **missing** | **added** `files_watch` (SSE, polling, bounded) |
| `files.upload_url/download_url` | n/a (pre-signed URL concept is platform-only) | N/A-4 |
| `commands.run/stream` | `shell`, `shell_stream` | covered; added `cwd/env/timeout` parity |
| `commands.start` (background) | `process_start` | covered; added `env`, `capture_output`, `stdin` |
| `commands.list` | `process_list` | covered |
| `commands.connect(pid)` | **missing output attach** | **added** `process_output` (+ `?wait`) |
| `commands.send_stdin` | **missing** | **added** `process_stdin` |
| `commands.send_signal/kill` | `process_signal` | covered |
| `ProcessProtocol.update` (pty resize via process) | `pty_resize` | **added** (PTY only) |
| `get_terminal` (envd WS `/terminal`) | PTY WS on 9001 with REST session create | client `server.pty` implements the server protocol; envd path unchanged |
| `code.run` / contexts (CodeInterpreter RPC) | `code_run` only (stateless) | N/A-2 |
| `network.get_url/get_host` | `ports` (listening ports) | covered; independent concepts |
| `sandbox.run(name)` | `commands` | covered |

## 4. Deliberate one-sided items

* **N/A-1 envd Connect RPC / `/files` multipart is not reimplemented on the server.** The base image
  already ships envd on 49983; duplicating it on 9000 would create two sources of truth for the same
  operations and a second place to harden. `ServerClient` covers the server's own protocol.
* **N/A-2 Stateful code-interpreter contexts** (create/list/restart/remove) need a kernel
  (`ipykernel`/Jupyter) — a heavy, non-stdlib dependency. The official `code-interpreter-v1` image provides
  it on its own port; the server offers the stateless `code_run` instead. Documented, not built.
* **N/A-3 `Sandbox.pause/resume/set_timeout/kill`** are platform control-plane operations, not
  in-container.
* **N/A-4 `files.upload_url/download_url`** are envd URL conveniences; the server would need
  signed URLs (token handling) — out of scope.
* **N/A-5 Template/build APIs** are control-plane.
* **N/A-6 Raw octet-stream bodies** for large downloads: server responses are JSON (base64) by
  design of the current `ServerResponse`; limits (`max_bytes`) bound the cost. Candidate follow-up.
* **N/A-7 The `agents` group (OpenAI-compatible Agents API) routes.** They are owned by the Agents
  API workstream ([agents-api.md](agents-api.md)) and have their own client surface; they are
  excluded from `ServerClient.ENDPOINT_METHODS` and from the matrix-completeness test by name
  (`group == agents`), so adding an agents route never breaks this guard, and adding any *other*
  route without a client method does.

## 5. Cross-cutting alignment

| Concern | Server | Client |
|---------|--------|--------|
| Errors | `{error,type,code,...}`, status codes | mapped to typed exceptions (fine-grained doc 7) |
| Auth | `X-Access-Token` / `Authorization: Bearer` | `ServerClient(token=...)` sends Bearer; gateway headers from `Sandbox.network` |
| Discovery | `GET /capabilities` v2 | `ServerCapabilities` |
| Streaming | SSE (`shell_stream`, `files_watch`); `process_output` is cursor-polled (`process.follow()`) | async iterators with deterministic close |
| Sync | — | `*_sync` twin for every public coroutine, same `make_sync` style |
| Limits | per-endpoint | `caps.limit(endpoint, key)`; uploads fail fast on `max_bytes` |

## 6. Test strategy

* Server: unit tests for each new endpoint and each changed request parameter; compat tests for
  unchanged defaults.
* Client: `tests/test_api/server_e2e/test_server_client_*.py` run `ServerClient` against a **real in-process
  `SandboxServer` on a free port** (fixtures in `tests/test_api/server_e2e/conftest.py`) for every
  method in the matrix; a matrix-completeness test asserts every route in the server's route table
  has a client method (via a declared mapping `ServerClient.ENDPOINT_METHODS`) so future routes
  cannot silently lose their client.

## 7. Changes after review (Draft v1 -> v2)

See [fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md) section 3.

* `process_output` is backed by a bounded ring buffer (`limits.max_output_bytes`, default 1 MiB per
  process) with cursor-based reads (`since=<offset>`); `process_start(capture_output=false)`
  keeps today's behaviour (output discarded).
* Decision table, `ServerClient` vs envd-backed modules: use `Sandbox.files/commands` when code must
  work on any sandbox; use `Sandbox.server` when the template author ships a server and wants
  policy-scoped, scope-checked access (or needs endpoints envd lacks: `files_search`,
  `files_archive`, `process_output`, browser, git).
* Streaming methods close the HTTP response on generator `aclose()`; sync twins return iterators that
  support `close()`.
* A 404 with `code: endpoint_disabled` maps to `EndpointNotAvailableError` (its `rule` field names the rule that
  disabled the endpoint, such as `policy:groups.file_ops`); path violations are 403 `path_not_allowed` and map to
  `FilePolicyDeniedError`. A server without `endpoints` in `/capabilities` is not supported.

## 8. Final tally (as implemented)

* Server endpoints audited: the single `ENDPOINTS` table declares 118 ids. The 48 outside the `agents` group
  (core 3, commands 2, file_ops 12, process 8, terminal 6 including the `pty_connect` WebSocket, system 6,
  dev_tools 3, browser 8) are **all mapped** in `ServerClient.ENDPOINT_METHODS` to 59
  client methods (async coroutines, each with a `*_sync` twin; streaming generators have
  collecting coroutines `watch_for` / `run_stream` instead of a sync twin). The 70 `agents` endpoints
  (`/v1/agents/*`, `/v1/vaults`, `/v1/responses`, ...) are the Agents API and are not wrapped by `ServerClient`
  (see [Agents API](../reference/agents-api.md)).
* Client-to-server gaps filled: `files_watch`, `process_output`, `process_stdin`,
  `pty_resize` / session detail, `cwd`/`env`/`timeout` for `shell*`, `env`/`capture_output`/`stdin`
  for `process_start`.
* Deliberately one-sided: N/A-1 .. N/A-7.
* Typed models live in `agent_sandbox.models.server`; errors in `agent_sandbox.models.errors`
  (E9xxx); everything is exercised by `tests/test_api/server_e2e/` against a real in-process
  `SandboxServer`.
