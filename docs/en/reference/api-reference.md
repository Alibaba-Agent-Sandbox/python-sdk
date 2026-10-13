# API Reference

This document lists all public API signatures, parameters, return values, and exceptions of the Agent Sandbox Python SDK.

---

## Sandbox Class

```python
from agent_sandbox.api.sandbox import Sandbox
```

### Class Methods

#### `Sandbox.create()`

```python
@classmethod
async def create(
    cls,
    template: str = "base",
    *,
    timeout: int = 300,
    request_timeout: float | None = None,
    metadata: dict[str, str] | None = None,
    envs: dict[str, str] | None = None,
    cpu: int | None = None,
    memory: int | None = None,
    disk: int | None = None,
    gpu: str | None = None,
    secure: bool = True,
    api_key: str | None = None,
    api_url: str | None = None,
    domain: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> Sandbox
```

Create a new sandbox.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `template` | `str` | `"base"` | Sandbox template name |
| `timeout` | `int` | `300` | Sandbox lifetime (TTL) in seconds (1–86400); not an HTTP timeout |
| `request_timeout` | `float` | `None` | Per-request HTTP timeout (seconds) for the create call only. When `None`, uses `SANDBOX_HTTP_TIMEOUT` / `http_timeout`. Aligns with the E2B SDK. Raising it does not work around platform-side create stalls. |
| `metadata` | `dict` | `None` | Arbitrary metadata key-value pairs |
| `envs` | `dict` | `None` | Injected environment variables |
| `cpu` | `int` | `None` | Number of CPU cores |
| `memory` | `int` | `None` | Memory in MB |
| `disk` | `int` | `None` | Disk in MB |
| `gpu` | `str` | `None` | GPU specification (e.g., `"A10"`) |
| `secure` | `bool` | `True` | Secure mode (port access requires token) |
| `api_key` | `str` | `None` | API Key override |
| `api_url` | `str` | `None` | Platform API URL override |
| `domain` | `str` | `None` | Domain override |
| `access_key_id` | `str` | `None` | Alibaba Cloud AK |
| `access_key_secret` | `str` | `None` | Alibaba Cloud SK |

**Returns**: `Sandbox` instance

**Sync version**: `Sandbox.create_sync(...)`

#### `Sandbox.connect()`

```python
@classmethod
async def connect(
    cls,
    sandbox_id: str,
    *,
    api_key: str | None = None,
    api_url: str | None = None,
    domain: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> Sandbox
```

Connect to an existing sandbox.

**Returns**: `Sandbox` instance

**Sync version**: `Sandbox.connect_sync(...)`

#### `Sandbox.list()`

```python
@classmethod
async def list(
    cls,
    *,
    status: SandboxStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    api_key: str | None = None,
    api_url: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> list[SandboxInfo]
```

List sandboxes (class method, no instance required).

**Returns**: `list[SandboxInfo]`

**Sync version**: `Sandbox.list_sync(...)`

#### `Sandbox.kill_by_id()`

```python
@classmethod
async def kill_by_id(
    cls,
    sandbox_id: str,
    *,
    api_key: str | None = None,
    api_url: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> None
```

Destroy a sandbox by ID (class method, no prior connection required).

**Sync version**: `Sandbox.kill_by_id_sync(...)`

### Instance Methods

| Method | Signature | Description | Sync Version |
|--------|-----------|-------------|--------------|
| `kill()` | `async def kill() -> None` | Destroy the sandbox and release resources | `kill_sync()` |
| `set_timeout()` | `async def set_timeout(timeout: int) -> None` | Update timeout duration | `set_timeout_sync()` |
| `is_running()` | `async def is_running() -> bool` | Check running status (makes an API call) | `is_running_sync()` |
| `pause()` | `async def pause() -> None` | Pause the sandbox | `pause_sync()` |
| `resume()` | `async def resume() -> None` | Resume a paused sandbox | `resume_sync()` |
| `refresh_info()` | `async def refresh_info() -> SandboxInfo` | Refresh sandbox info | `refresh_info_sync()` |

#### `run_code()`

```python
async def run_code(
    self,
    code: str,
    *,
    language: str = "python",
    timeout: int = 30,
    envs: dict[str, str] | None = None,
    on_stdout: Callable[[str], None] | None = None,
    on_stderr: Callable[[str], None] | None = None,
    on_result: Callable[..., None] | None = None,
) -> CodeResult
```

Execute code via the Code Interpreter. Requires the `code` capability.

**Returns**: `CodeResult` (with `text`, `stdout`, `stderr`, `exit_code`, `execution_time`, `output_files`)

**Raises**: `CapabilityNotSupportedError` (E3004) — if the `code` capability is not enabled

**Sync version**: `run_code_sync()`

#### `get_terminal()`

```python
async def get_terminal(
    self,
    *,
    cols: int = 80,
    rows: int = 24,
    shell: str = "/bin/bash",
) -> TerminalSession
```

Open an interactive PTY terminal session. Logically associated with the `terminal` capability (no runtime gate).

**Returns**: `TerminalSession` (WebSocket connection)

**Sync version**: `get_terminal_sync()`

#### `list_commands()`

```python
async def list_commands(
    self,
    *,
    server_port: int = 9000,
) -> list[ServerCommand]
```

List the named commands registered on the sandbox's SandboxServer (`GET /commands`). Commands are registered inside the sandbox with `@sandbox.register` or the server's `CommandRegistry`.

**Returns**: List of `ServerCommand` (`name`, `description`, `args`)

**Raises**: `ProviderFeatureNotSupportedError` (E8004) when the provider has no HTTP data plane; `ConnectionError_` when the server is unreachable

**Sync version**: `list_commands_sync()`

#### `run()`

```python
async def run(
    self,
    name: str,
    /,
    *,
    server_port: int = 9000,
    **kwargs: Any,
) -> Any
```

Call a named command registered on the sandbox's SandboxServer: `sandbox.run("name", x=1)` is `POST /commands/name` with `kwargs` as the JSON body. This is the only way to call a named command. For a raw shell command use `sandbox.commands.run(cmd, ...)`.

**Returns**: The command's result value

**Raises**: `CommandNotFoundError` (404), `ServerAPIError` (other server errors), `ProviderFeatureNotSupportedError` (E8004)

**Sync version**: `run_sync()`

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `id` | `str` | Sandbox ID |
| `status` | `SandboxStatus` | Current status (cached value; call `refresh_info()` to update) |
| `url` | `str` | envd URL |
| `info` | `SandboxInfo` | Full sandbox info |
| `capabilities` | `frozenset[str]` | Effective capability set |

### Submodules

| Property | Type | Description |
|----------|------|-------------|
| `commands` | `CommandsModule` | Shell command execution |
| `files` | `FilesModule` | Filesystem operations |
| `network` | `NetworkModule` | Port URL computation |
| `code` | `CodeContextModule` | Code Interpreter operations |

### Context Manager

```python
async with await Sandbox.create() as sandbox:
    ...  # Automatically calls kill() on exit
```

---

## CommandsModule

```python
sandbox.commands  # CommandsModule instance
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `run()` | `async def run(cmd, *, timeout=60, env=None, cwd="", user="", background=False) -> ProcessResult \| StreamReader` | Execute a command and wait. Returns `StreamReader` when `background=True` |
| `stream()` | `async def stream(cmd, *, timeout=60, env=None, cwd="", user="") -> AsyncIterator[ProcessChunk]` | Stream command output |
| `start()` | `async def start(cmd, *, timeout=60, env=None, cwd="", user="") -> StreamReader[ProcessChunk]` | Start a command in the background, return StreamReader |
| `list()` | `async def list() -> list[ProcessInfo]` | List running processes |
| `kill()` | `async def kill(pid: int) -> None` | Terminate a process |
| `send_input()` | `async def send_input(pid: int, data: str) -> None` | Send data to process stdin |
| `send_stdin()` | `async def send_stdin(pid: int, data: str) -> None` | (Deprecated) Same as `send_input()` |
| `send_signal()` | `async def send_signal(pid: int, signal: int = 15) -> None` | Send SIGTERM (15) or SIGKILL (9) to a process; any other number raises `ValueError` (envd only delivers these two) |

Logically associated with the `shell` capability (declared in `template.yaml`; no runtime gate — requests are forwarded to the sandbox regardless). Each async method has a `_sync` suffixed sync version (e.g., `run_sync()`).

---

## FilesModule

```python
sandbox.files  # FilesModule instance
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `read()` | `async def read(path, *, encoding="utf-8") -> str` | Read a text file |
| `read_bytes()` | `async def read_bytes(path) -> bytes` | Read a binary file |
| `write()` | `async def write(path, content: str \| bytes) -> None` | Write a file |
| `list()` | `async def list(path="/") -> list[FileInfo]` | List a directory |
| `remove()` | `async def remove(path) -> None` | Delete a file/directory |
| `exists()` | `async def exists(path) -> bool` | Check if a path exists |
| `make_dir()` | `async def make_dir(path) -> None` | Create a directory (including parents) |
| `upload()` | `async def upload(local_path, remote_path) -> None` | Upload a local file to the sandbox |
| `download()` | `async def download(remote_path, local_path) -> None` | Download a sandbox file to local |
| `watch()` | `async def watch(path) -> StreamReader[WatchEvent]` | Watch for directory changes |
| `move()` | `async def move(source, destination) -> None` | Move/rename |
| `rename()` | `async def rename(old_path, new_path) -> None` | (Deprecated) Same as `move()` |
| `get_info()` | `async def get_info(path) -> FileInfo` | Get file info |
| `upload_url()` | `async def upload_url(path) -> str` | Get upload URL (for compatibility) |
| `download_url()` | `async def download_url(path) -> str` | Get download URL (for compatibility) |

Logically associated with the `files` capability (declared in `template.yaml`; no runtime gate). Each async method has a `_sync` suffixed sync version.

---

## NetworkModule

```python
sandbox.network  # NetworkModule instance
```

All methods are local computations with no network requests. Logically associated with the `ports` capability (no runtime gate).

| Method | Signature | Description |
|--------|-----------|-------------|
| `get_host()` | `def get_host(port: int) -> str` | Returns `{port}-{sandbox_id}.{domain}` |
| `get_url()` | `def get_url(port: int) -> str` | Returns `https://{port}-{sandbox_id}.{domain}` |
| `get_access_headers()` | `def get_access_headers() -> dict[str, str]` | Returns HTTP headers required for port access |

---

## CodeContextModule

```python
sandbox.code  # CodeContextModule instance
```

| Method | Signature | Description |
|--------|-----------|-------------|
| `run()` | `async def run(code, *, language="python", timeout=30, context_id=None, envs=None, on_stdout=None, on_stderr=None, on_result=None) -> CodeResult` | Execute code |
| `create_context()` | `async def create_context(*, language="python") -> dict` | Create an execution context |
| `list_contexts()` | `async def list_contexts() -> list[dict]` | List all contexts |
| `restart_context()` | `async def restart_context(context_id) -> dict` | Restart a context |
| `remove_context()` | `async def remove_context(context_id) -> None` | Delete a context |

All methods require the `code` capability and enforce it at runtime — calling any method without the `code` capability raises `CapabilityNotSupportedError` (E3004). Each async method has a `_sync` suffixed sync version.

---

## ServerClient (in-sandbox SandboxServer)

```python
from agent_sandbox.api import ServerClient, ServerCapabilities
```

Typed client for the template-authored SandboxServer (port 9000, PTY WebSocket on 9001). It is separate from
the envd-backed `sandbox.files` / `sandbox.commands`: use `Sandbox.server` when the template ships a server and
you want policy-scoped, scope-checked access, or need endpoints envd lacks (`files.search`, `files.archive`,
`files.watch`, `process.output`, git, browser). Every coroutine has a `*_sync` twin; async generators
(`files.watch`, `process.shell_stream`, `process.follow`) have collecting coroutines (`files.watch_for`,
`process.run_stream`) instead. Models live in `agent_sandbox.models.server`.

| Member | Signature | Description |
|--------|-----------|-------------|
| `ServerClient()` | `(base_url, *, token=None, headers=None, pty_url=None, timeout=30.0, http_client=None)` | `token` is sent as `Authorization: Bearer`; `headers` carry the gateway `X-Access-Token` |
| `Sandbox.server` | `cached_property -> ServerClient` | Client for port 9000 with the sandbox gateway headers |
| `Sandbox.server_at()` | `(port=9000, *, token=None, pty_port=9001, timeout=30.0) -> ServerClient` | A fresh client for another port/token |
| `Sandbox.start_server()` | `async (*, port=9000, commands=None, policy=None, token=None, env=None, command=None, wait=True, timeout=30.0) -> ServerClient` | Starts `agent-sandbox-server serve` as a background envd command and polls `/health`; `policy` is a dict (`ABX_SERVER_POLICY`) or a preset name; raises `ConnectionError_` on timeout |
| `health()` | `async -> bool` | `GET /health`, never raises for an unreachable server |
| `discover()` | `async -> ServerCapabilities` | `GET /capabilities`; caches the result in `client.capabilities` and enables fail-fast pre-checks |
| `forget_discovery()` | `() -> None` | Drop the cache (policy changed) |
| `check()` | `async (endpoint, path=None, op=None) -> PathDecision` | `POST /capabilities/check` |
| `with_token()` | `(token) -> ServerClient` | Same server, another identity |
| `aclose()` | `async` | Close the HTTP session |

Sub-APIs (all return typed models; see [Server HTTP API](./server-http-api.md) for the wire format):

| Sub-API | Methods |
|---------|---------|
| `files` | `list`, `stat`, `exists`, `mkdir`, `delete`, `move`, `search`, `archive`, `watch`/`watch_for`, `upload`, `download`, `read_text`, `upload_file`, `download_file`, `upload_legacy`, `download_legacy` (the `/upload` and `/download` endpoints) |
| `process` | `shell`, `shell_stream`/`run_stream`, `start`, `list`, `get`, `signal`, `terminate`, `kill`, `send_stdin`, `close_stdin`, `output`, `follow`, `wait` |
| `pty` | `create`, `list`, `get`, `resize`, `delete`, `connect` (WebSocket `PtyConnection`) |
| `system` | `info`, `metrics`, `env`, `set_env`, `ports`, `packages` |
| `devtools` | `run_code`, `git_status`, `git_diff` |
| `browser` | `navigate`, `screenshot`, `content`, `click`, `type`, `evaluate`, `pdf`, `console` |
| `commands` | `list`, `run` |

`ServerClient.ENDPOINT_METHODS` maps every server endpoint id to its client methods (a test asserts that every
route of the server's default table is present).

### ServerCapabilities

Returned by `discover()`. There is no legacy mode: a server whose `/capabilities` lacks `endpoints` is not supported.

| Member | Description |
|--------|-------------|
| `can(endpoint)` | `True` when the endpoint exists, is enabled and the identity may call it |
| `denial(endpoint)` | Reason string (`endpoint_disabled`, `unknown_endpoint`, `missing_scope`) or `None` |
| `rule(endpoint)` | The rule code that disabled the endpoint (`policy:groups.file_ops`, `default:opt-in:dev_tools`, ...) or `None` |
| `require(endpoint)` | Raises `EndpointNotAvailableError` / `PolicyDeniedError`; otherwise returns the `EndpointInfo` |
| `info(endpoint)` | `EndpointInfo` (`method`, `path`, `group`, `enabled`, `allowed`, `scopes`, `limits`, `paths`, `params`) |
| `limit(endpoint, key, default=None)` / `param(...)` | A configured limit / parameter |
| `paths(endpoint)` | `EndpointPaths` (`allow`, `read_only`, `deny_count`, `symlinks`) |
| `endpoints_for(scope)` / `available()` | Endpoint ids granted by a scope / callable now |
| `check_path(endpoint, path, op=None)` (+ `_sync`) | Authoritative server-side path decision (never an existence oracle) |
| `groups`, `group_summary` | `{group: enabled}` and `{group: {enabled, total}}` derived views; the switch is the endpoint rule |
| `identity_id`, `scopes`, `preset`, `revision`, `warnings`, `api_version`, `server_version`, `configured` | Document metadata |

### Errors (E9xxx)

`ServerAPIError` (E9000) -> `ServerAuthError` (E9001, also `AuthenticationError`), `PolicyDeniedError` (E9002; `scope`) ->
`FilePolicyDeniedError` (also `PermissionDeniedError`), `EndpointNotAvailableError` (E9003, also
`CapabilityNotSupportedError`), `PayloadTooLargeError` (E9004; `limit`), `RateLimitedError` (E9005; `retry_after`).
See [Error Codes](./error-codes.md#e9xxx--in-sandbox-server-api-errors-serverapierror).

---

## Data Models

### SandboxStatus

```python
from agent_sandbox.models.sandbox import SandboxStatus

class SandboxStatus(str, Enum):
    CREATING = "creating"
    RUNNING  = "running"
    PAUSED   = "paused"
    STOPPING = "stopping"
    STOPPED  = "stopped"
    ERROR    = "error"
```

### SandboxInfo

| Field | Type | Description |
|-------|------|-------------|
| `sandbox_id` | `str` | Sandbox ID |
| `template` | `str` | Template name |
| `status` | `SandboxStatus` | Current status |
| `envd_url` | `str \| None` | envd data plane URL |
| `envd_access_token` | `str \| None` | envd authentication token |
| `metadata` | `dict` | User metadata |
| `started_at` | `datetime \| None` | Creation time |

### CodeResult

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | stdout (trailing whitespace stripped) |
| `stdout` | `str` | Raw stdout |
| `stderr` | `str` | Raw stderr |
| `exit_code` | `int` | Exit code |
| `execution_time` | `float` | Execution time (seconds) |
| `output_files` | `list` | Output file list |

### OutputFile

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | File name |
| `path` | `str` | File path |
| `size` | `int` | File size (bytes, default 0) |
| `mime_type` | `str` | MIME type (default `"application/octet-stream"`) |

### ProcessResult

| Field | Type | Description |
|-------|------|-------------|
| `stdout` | `str` | Standard output |
| `stderr` | `str` | Standard error |
| `exit_code` | `int` | Exit code |
| `execution_time` | `float` | Execution time (seconds) |
| `success` | `bool` | `exit_code == 0` (property) |

### ProcessChunk

| Field | Type | Description |
|-------|------|-------------|
| `type` | `ProcessChunkType` | `stdout` / `stderr` / `exit` |
| `data` | `str` | Data content |
| `exit_code` | `int \| None` | Exit code (only for `exit` type) |

### FileInfo

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | File name |
| `path` | `str` | Absolute path |
| `type` | `FileType` | `file` / `directory` |
| `size` | `int` | File size (bytes) |

---

## Exception Hierarchy

All exceptions inherit from `SandboxError` and carry `code`, `message`, `suggestion`, and `docs_url` attributes.

See [Error Codes Reference](./error-codes.md) for the complete error code listing.
