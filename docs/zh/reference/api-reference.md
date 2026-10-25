# API 参考

本文介绍 ProviderSandbox 扩展 API。根入口 Sandbox / AsyncSandbox 使用独立标准契约，见 [E2B 迁移](../guide/migrate-from-e2b.md)。

---

## Sandbox 类

```python
from agent_sandbox import ProviderSandbox as Sandbox
```

### 类方法

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
    volume_mounts: dict[str, str] | None = None,
    cpu: int | None = None,
    memory: int | None = None,
    disk: int | None = None,
    gpu: str | None = None,
    secure: bool | None = None,
    sandbox_api_key: str | None = None,
    sandbox_base_url: str | None = None,
    sandbox_domain: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> Sandbox
```

创建新沙箱。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `template` | `str` | `"base"` | 沙箱模板名称 |
| `timeout` | `int` | `300` | 沙箱生存时长（TTL）秒数（1~86400）；非 HTTP 请求超时 |
| `request_timeout` | `float` | `None` | 仅针对本次创建请求的 HTTP 超时（秒）。为 `None` 时使用 `ABX_HTTP_TIMEOUT` / `http_timeout`。与 E2B SDK 对齐。调大它无法绕过平台侧创建挂起。 |
| `metadata` | `dict` | `None` | 任意元数据键值对 |
| `envs` | `dict` | `None` | 注入的环境变量 |
| `volume_mounts` | `dict[str, str]` | `None` | 仅内置提供方：规范化的沙箱绝对路径 → 已有 Volume 名称。省略或空字典不挂载，其他提供方的非空参数返回 E8004。见[挂载要求与请求 schema](../guide/provider-commands.md#创建沙箱时挂载已有-volume)。 |
| `cpu` | `int` | `None` | CPU 核数 |
| `memory` | `int` | `None` | 内存 MB |
| `disk` | `int` | `None` | 磁盘 MB |
| `gpu` | `str` | `None` | GPU 规格（如 `"A10"`） |
| `secure` | `bool` | `None` | 安全模式（端口访问需 token） |
| `sandbox_api_key` | `str` | `None` | API Key 覆盖 |
| `sandbox_base_url` | `str` | `None` | 平台 API URL 覆盖 |
| `sandbox_domain` | `str` | `None` | 域名覆盖 |
| `access_key_id` | `str` | `None` | 阿里云 AK |
| `access_key_secret` | `str` | `None` | 阿里云 SK |

**返回**：`Sandbox` 实例

**同步版**：`Sandbox.create_sync(...)`

#### `Sandbox.connect()`

```python
@classmethod
async def connect(
    cls,
    sandbox_id: str,
    *,
    sandbox_api_key: str | None = None,
    sandbox_base_url: str | None = None,
    sandbox_domain: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> Sandbox
```

连接到已有沙箱。

**返回**：`Sandbox` 实例

**同步版**：`Sandbox.connect_sync(...)`

#### `Sandbox.list()`

```python
@classmethod
async def list(
    cls,
    *,
    status: SandboxStatus | None = None,
    limit: int = 100,
    offset: int = 0,
    sandbox_api_key: str | None = None,
    sandbox_base_url: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> list[SandboxInfo]
```

列出沙箱（类方法，不需要实例）。

**返回**：`list[SandboxInfo]`

**同步版**：`Sandbox.list_sync(...)`

#### `Sandbox.kill_by_id()`

```python
@classmethod
async def kill_by_id(
    cls,
    sandbox_id: str,
    *,
    sandbox_api_key: str | None = None,
    sandbox_base_url: str | None = None,
    access_key_id: str | None = None,
    access_key_secret: str | None = None,
) -> None
```

按 ID 销毁沙箱（类方法，不需要先连接）。

**同步版**：`Sandbox.kill_by_id_sync(...)`

### 实例方法

| 方法 | 签名 | 说明 | 同步版 |
|------|------|------|--------|
| `kill()` | `async def kill() -> None` | 销毁沙箱并释放资源 | `kill_sync()` |
| `set_timeout()` | `async def set_timeout(timeout: int) -> None` | 更新超时时间 | `set_timeout_sync()` |
| `is_running()` | `async def is_running() -> bool` | 检查运行状态（发起 API 调用） | `is_running_sync()` |
| `pause()` | `async def pause() -> None` | 暂停沙箱 | `pause_sync()` |
| `resume()` | `async def resume() -> None` | 恢复暂停的沙箱 | `resume_sync()` |
| `refresh_info()` | `async def refresh_info() -> SandboxInfo` | 刷新沙箱信息 | `refresh_info_sync()` |

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

通过 Code Interpreter 执行代码。需要 `code` 能力。

**返回**：`CodeResult`（含 `text`、`stdout`、`stderr`、`exit_code`、`execution_time`、`output_files`）

**异常**：`CapabilityNotSupportedError`（E3004）— 若 `code` 能力未启用

**同步版**：`run_code_sync()`

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

打开交互式 PTY 终端会话。逻辑上关联 `terminal` 能力（无运行时门控）。

**返回**：`TerminalSession`（WebSocket 连接）

**同步版**：`get_terminal_sync()`

#### `list_commands()`

```python
async def list_commands(
    self,
    *,
    server_port: int = 9000,
) -> list[ServerCommand]
```

列出沙箱内 SandboxServer 上注册的命名命令（`GET /commands`）。命令在沙箱内通过 `@sandbox.register` 或 server 的 `CommandRegistry` 注册。

**返回**：`ServerCommand` 列表（`name`、`description`、`args`）

**抛出**：provider 没有 HTTP 数据面时抛 `ProviderFeatureNotSupportedError`（E8004）；server 不可达时抛 `ConnectionError_`

**同步版**：`list_commands_sync()`

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

调用沙箱内 SandboxServer 上注册的命名命令：`sandbox.run("name", x=1)` 即以 `kwargs` 作为 JSON body 的 `POST /commands/name`。这是调用命名命令的唯一方式。裸 shell 命令请使用 `sandbox.commands.run(cmd, ...)`。

**返回**：命令的返回值

**抛出**：`CommandNotFoundError`（404）、`ServerAPIError`（其他 server 错误）、`ProviderFeatureNotSupportedError`（E8004）

**同步版**：`run_sync()`

### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 沙箱 ID |
| `status` | `SandboxStatus` | 当前状态（缓存值，调用 `refresh_info()` 更新） |
| `url` | `str` | envd URL |
| `info` | `SandboxInfo` | 完整沙箱信息 |
| `capabilities` | `frozenset[str]` | 有效能力集 |

### 子模块

| 属性 | 类型 | 说明 |
|------|------|------|
| `commands` | `CommandsModule` | Shell 命令执行 |
| `files` | `FilesModule` | 文件系统操作 |
| `network` | `NetworkModule` | 端口 URL 计算 |
| `code` | `CodeContextModule` | Code Interpreter 操作 |

### Context Manager

```python
async with await Sandbox.create() as sandbox:
    ...  # 退出时自动 kill()
```

---

## CommandsModule

```python
sandbox.commands  # CommandsModule 实例
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `run()` | `async def run(cmd, *, timeout=60, env=None, cwd="", user="", background=False) -> ProcessResult \| StreamReader` | 执行命令并等待。`background=True` 时返回 `StreamReader` |
| `stream()` | `async def stream(cmd, *, timeout=60, env=None, cwd="", user="") -> AsyncIterator[ProcessChunk]` | 流式输出命令结果 |
| `start()` | `async def start(cmd, *, timeout=60, env=None, cwd="", user="") -> StreamReader[ProcessChunk]` | 后台启动命令，返回 StreamReader |
| `list()` | `async def list() -> list[ProcessInfo]` | 列出运行中的进程 |
| `kill()` | `async def kill(pid: int) -> None` | 终止进程 |
| `send_input()` | `async def send_input(pid: int, data: str) -> None` | 向进程 stdin 发送数据 |
| `send_signal()` | `async def send_signal(pid: int, signal: int = 15) -> None` | 向进程发送 SIGTERM（15）或 SIGKILL（9）；其他信号值抛出 `ValueError`（envd 仅支持这两种） |

逻辑上关联 `shell` 能力（在 `template.yaml` 中声明；无运行时门控——请求会直接转发到沙箱）。每个异步方法都有 `_sync` 后缀的同步版本（如 `run_sync()`）。

---

## FilesModule

```python
sandbox.files  # FilesModule 实例
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `read()` | `async def read(path, *, encoding="utf-8") -> str` | 读取文本文件 |
| `read_bytes()` | `async def read_bytes(path) -> bytes` | 读取二进制文件 |
| `write()` | `async def write(path, content: str \| bytes) -> None` | 写入文件 |
| `list()` | `async def list(path="/") -> list[FileInfo]` | 列出目录 |
| `remove()` | `async def remove(path) -> None` | 删除文件/目录 |
| `exists()` | `async def exists(path) -> bool` | 检查路径是否存在 |
| `make_dir()` | `async def make_dir(path) -> None` | 创建目录（含父目录） |
| `upload()` | `async def upload(local_path, remote_path) -> None` | 上传本地文件到沙箱 |
| `download()` | `async def download(remote_path, local_path) -> None` | 下载沙箱文件到本地 |
| `watch()` | `async def watch(path) -> StreamReader[WatchEvent]` | 监听目录变更 |
| `move()` | `async def move(source, destination) -> None` | 移动/重命名 |
| `get_info()` | `async def get_info(path) -> FileInfo` | 获取文件信息 |
| `upload_url()` | `async def upload_url(path) -> str` | envd `/files` 地址。请求必须带 `X-Access-Token`，不是签名 URL |
| `download_url()` | `async def download_url(path) -> str` | 同上 |

逻辑上关联 `files` 能力（在 `template.yaml` 中声明；无运行时门控）。每个异步方法都有 `_sync` 后缀的同步版本。

---

## NetworkModule

```python
sandbox.network  # NetworkModule 实例
```

所有方法均为本地计算，不涉及网络请求。逻辑上关联 `ports` 能力（无运行时门控）。

| 方法 | 签名 | 说明 |
|------|------|------|
| `get_host()` | `def get_host(port: int) -> str` | 返回 `{port}-{sandbox_id}.{domain}` |
| `get_url()` | `def get_url(port: int) -> str` | 返回 `https://{port}-{sandbox_id}.{domain}` |
| `get_access_headers()` | `def get_access_headers() -> dict[str, str]` | secure 模式返回给平台网关的 `X-Access-Token`。`sandbox.run` 不发送它 |

---

## CodeContextModule

```python
sandbox.code  # CodeContextModule 实例
```

| 方法 | 签名 | 说明 |
|------|------|------|
| `run()` | `async def run(code, *, language="python", timeout=30, context_id=None, mode="stateless", envs=None, on_stdout=None, on_stderr=None, on_result=None) -> CodeResult` | 执行代码 |
| `create_context()` | `async def create_context(*, language="python") -> dict` | 创建执行上下文 |
| `list_contexts()` | `async def list_contexts() -> list[dict]` | 列出所有上下文 |
| `restart_context()` | `async def restart_context(context_id) -> dict` | 重启上下文 |
| `remove_context()` | `async def remove_context(context_id) -> None` | 删除上下文 |

每个方法均需精确的 Provider 操作：`run()` 默认选择 `code.execute`，`mode="default-context"` 选择 `code.default-context.execute`，非空 `context_id` 选择 `code.context.execute`。上下文创建、列出、重启、删除分别授权。实时回调另需 `code.stream`。适配器未实现时在发送负载前抛 E8004；实际 runtime 缺失或 HTTP 404 不会自动转 Shell。各异步方法提供 `_sync` 版本。当前适配器边界及独立固定标准客户端见[工作流](../guide/template-workflows.md)。

---

## ServerClient（沙箱内 SandboxServer）

```python
from agent_sandbox.api import ServerClient, ServerCapabilities
```

面向模板作者自带 SandboxServer（端口 9000，PTY WebSocket 为 9001）的类型化客户端。它与基于 envd 的
`sandbox.files` / `sandbox.commands` 相互独立：当模板自带服务端、需要按策略/scope 受控访问，或需要 envd 没有的端点
（`files.search`、`files.archive`、`files.watch`、`process.output`、git、浏览器）时使用 `Sandbox.server`。每个协程都有
`*_sync` 孪生方法；异步生成器（`files.watch`、`process.shell_stream`、`process.follow`）没有同步孪生，改用收集型协程
（`files.watch_for`、`process.run_stream`）。模型位于 `agent_sandbox.models.server`。

| 成员 | 签名 | 说明 |
|------|------|------|
| `ServerClient()` | `(base_url, *, token=None, headers=None, pty_url=None, timeout=30.0, http_client=None, expires_at=None)` | `token` 以 `Authorization: Bearer` 发送；`headers` 携带网关的 `X-Access-Token` |
| `ProviderSandbox.application_client()` | `async (port=9000, *, token=None, timeout=30.0) -> ServerClient` | 解析 Provider 应用网关描述符，保留其路径前缀、查询参数及网关头，应用令牌单独传入；跨 Provider 推荐使用 |
| `Sandbox.server` | `cached_property -> ServerClient` | 9000 端口原生本地 URL 辅助入口；跨 Provider 使用 application_client |
| `Sandbox.server_at()` | `(port=9000, *, token=None, pty_port=9001, timeout=30.0) -> ServerClient` | 原生本地 URL 辅助入口；需 Provider 网关描述符时使用 application_client；`token` 是应用令牌 |
| `Sandbox.start_server()` | `async (*, port=9000, commands=None, policy=None, token=None, env=None, command=None, wait=True, timeout=30.0) -> ServerClient` | 以 envd 后台命令启动 `agent-sandbox-server serve` 并轮询 `/health`；`policy` 为字典（`ABX_SERVER_POLICY`）或预设名；超时抛 `ConnectionError_` |
| `health()` | `async -> bool` | `GET /health`，服务端不可达时返回 `False` 而不抛异常 |
| `discover()` | `async -> ServerCapabilities` | `GET /capabilities`；要求精确整数 `api_version=2` 和端点映射后才允许调用，并缓存已检查文档 |
| `forget_discovery()` | `() -> None` | 丢弃缓存（策略变更后） |
| `check()` | `async (endpoint, path=None, op=None) -> PathDecision` | `POST /capabilities/check` |
| `with_token()` | `(token) -> ServerClient` | 同一服务端、另一个身份 |
| `aclose()` | `async` | 关闭 HTTP 会话 |

子 API（均返回类型化模型；线上格式见[服务端 HTTP API](./server-http-api.md)）：

| 子 API | 方法 |
|--------|------|
| `files` | `list`、`stat`、`exists`、`mkdir`、`delete`、`move`、`search`、`archive`、`watch`/`watch_for`、`upload`、`download`、`read_text`、`upload_file`、`download_file` |
| `process` | `shell`、`shell_stream`/`run_stream`、`start`、`list`、`get`、`signal`、`terminate`、`kill`、`send_stdin`、`close_stdin`、`output`、`follow`、`wait` |
| `pty` | `create`、`list`、`get`、`resize`、`delete`、`connect`（WebSocket `PtyConnection`） |
| `system` | `info`、`metrics`、`env`、`set_env`、`ports`、`packages` |
| `devtools` | `run_code`、`git_status`、`git_diff` |
| `browser` | `navigate`、`screenshot`、`content`、`click`、`type`、`evaluate`、`pdf`、`console` |
| `commands` | `list`、`run` |

`ServerClient.ENDPOINT_METHODS` 把每个服务端端点 id 映射到对应的客户端方法（有测试保证服务端默认路由表中的每条路由都在其中）。

### ServerCapabilities

由 `discover()` 返回。没有 legacy 模式：`/capabilities` 中没有 `endpoints` 的服务端不受支持。

| 成员 | 说明 |
|------|------|
| `can(endpoint)` | 端点存在、已启用且当前身份可调用时为 `True` |
| `denial(endpoint)` | 原因字符串（`endpoint_disabled`、`unknown_endpoint`、`missing_scope`）或 `None` |
| `rule(endpoint)` | 禁用该端点的规则代码（`policy:groups.file_ops`、`default:opt-in:dev_tools` 等）或 `None` |
| `require(endpoint)` | 抛出 `EndpointNotAvailableError` / `PolicyDeniedError`；否则返回 `EndpointInfo` |
| `info(endpoint)` | `EndpointInfo`（`method`、`path`、`group`、`enabled`、`allowed`、`scopes`、`limits`、`paths`、`params`） |
| `limit(endpoint, key, default=None)` / `param(...)` | 已配置的限制 / 参数 |
| `paths(endpoint)` | `EndpointPaths`（`allow`、`read_only`、`deny_count`、`symlinks`） |
| `endpoints_for(scope)` / `available()` | 某 scope 授予的端点 id / 当前可调用的端点 id |
| `check_path(endpoint, path, op=None)`（及 `_sync`） | 服务端给出的权威路径判定（不会成为存在性探测口） |
| `groups`、`group_summary` | `{组: 是否启用}` 和 `{组: {enabled, total}}`，都是派生视图；开关是端点规则 |
| `identity_id`、`scopes`、`preset`、`revision`、`warnings`、`api_version`、`server_version`、`configured` | 文档元数据 |

### 错误（E9xxx）

`ServerAPIError`（E9000）-> `ServerAuthError`（E9001，同时是 `AuthenticationError`）、`PolicyDeniedError`（E9002；`scope`）->
`FilePolicyDeniedError`（同时是 `PermissionDeniedError`）、`EndpointNotAvailableError`（E9003，同时是 `CapabilityNotSupportedError`）、
`PayloadTooLargeError`（E9004；`limit`）、`RateLimitedError`（E9005；`retry_after`）。详见[错误码](./error-codes.md)。

---

## 数据模型

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `sandbox_id` | `str` | 沙箱 ID |
| `template` | `str` | 模板名称 |
| `status` | `SandboxStatus` | 当前状态 |
| `envd_url` | `str \| None` | envd 数据平面 URL |
| `envd_access_token` | `str \| None` | envd 认证令牌 |
| `metadata` | `dict` | 用户元数据 |
| `started_at` | `datetime \| None` | 创建时间 |

### CodeResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `text` | `str` | stdout（去除尾部空白） |
| `stdout` | `str` | 原始 stdout |
| `stderr` | `str` | 原始 stderr |
| `exit_code` | `int` | 退出码 |
| `execution_time` | `float` | 执行耗时（秒） |
| `output_files` | `list` | 输出文件列表 |

### OutputFile

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 文件名 |
| `path` | `str` | 文件路径 |
| `size` | `int` | 文件大小（字节，默认 0） |
| `mime_type` | `str` | MIME 类型（默认 `"application/octet-stream"`） |

### ProcessResult

| 字段 | 类型 | 说明 |
|------|------|------|
| `stdout` | `str` | 标准输出 |
| `stderr` | `str` | 标准错误 |
| `exit_code` | `int` | 退出码 |
| `execution_time` | `float` | 执行耗时（秒） |
| `success` | `bool` | `exit_code == 0`（属性） |

### ProcessChunk

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `ProcessChunkType` | `stdout` / `stderr` / `exit` |
| `data` | `str` | 数据内容 |
| `exit_code` | `int \| None` | 退出码（仅 `exit` 类型） |
| `pid` | `int \| str \| None` | 原生启动确认的进程标识，保留整数或不透明字符串 |

### FileInfo

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 文件名 |
| `path` | `str` | 绝对路径 |
| `type` | `FileType` | `file` / `directory` |
| `size` | `int` | 文件大小（字节） |

---

## 异常层级

所有异常继承自 `SandboxError`，携带 `code`、`message`、`suggestion`、`docs_url` 属性。

详细错误码列表参见 [错误码参考](./error-codes.md)。
