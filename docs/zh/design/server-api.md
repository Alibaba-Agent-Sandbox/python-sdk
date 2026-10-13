# Container-Side HTTP Server API Reference

> 容器内 HTTP Server（`agent_sandbox.server`）的完整 API 参考文档。
>
> 本文档的所有端点方法、路径、参数、请求体字段、响应格式均逐一读取自
> `src/agent_sandbox/server/` 下的实现代码，与源码保持一致。若代码中未明确定义某项行为，
> 文档会如实标注而非臆测。

---

## 1. 概述

### 1.1 Server 定位

容器内 HTTP Server 是一个**仅依赖 Python 标准库**（stdlib-only，零第三方依赖）的轻量级 HTTP 服务，
运行在 Sandbox 容器内部，向外部（SDK / CLI / Agent）暴露文件、进程、终端、系统信息、开发工具、
浏览器自动化等能力。

- 基于 [`http.server.ThreadingHTTPServer`](../../../server-sdk/src/agent_sandbox/server/app.py) + 自定义 `BaseHTTPRequestHandler` 子类。
- 请求分发由数据驱动的 [`RouteTable`](../../../server-sdk/src/agent_sandbox/server/router.py) 完成，而非硬编码的 `if/elif` 链。
- 每个路由归属一个 **能力组（CapabilityGroup）**，可整组启用/禁用。
- 请求/响应对象是 stdlib `dataclass`（[`types.py`](../../../server-sdk/src/agent_sandbox/server/types.py)），不使用 Pydantic。

> 注意：本文所述「能力组」是 **Server 端 RouteTable 的运行时开关**，与 SDK 模板层
> （`models/template.py` / `api/capability.py`）的 `STANDARD_CAPABILITIES` 是两套独立机制，
> 不要混淆。

### 1.2 启动方式

**便捷函数** —
[`start()`](../../../server-sdk/src/agent_sandbox/server/app.py#L320-L334)：

```python
from agent_sandbox.server import start

start(9000)  # 监听 0.0.0.0:9000，阻塞运行
```

**类接口** —
[`SandboxServer`](../../../server-sdk/src/agent_sandbox/server/app.py#L215-L317)（可注入自定义 `registry` / `route_table`）：

```python
from agent_sandbox.server import SandboxServer, CommandRegistry

registry = CommandRegistry()
# ... 注册自定义命令 ...
server = SandboxServer(host="0.0.0.0", registry=registry)
server.serve(port=9000)  # 阻塞直到 KeyboardInterrupt / shutdown()
```

`serve()` 会在启动时调用 `registry.freeze()` 冻结命令注册表，随后开始接受请求。

### 1.3 两端口架构

Server 使用两个端口：

| 端口 | 协议 | 用途 | 默认值 | 覆盖变量 |
|------|------|------|--------|----------|
| HTTP 端口 | HTTP/1.1 | 全部 REST / SSE 端点 | `9000`（`serve(port=...)` 参数） | — |
| PTY 端口 | WebSocket | 交互式终端（PTY） | `9001` | `ABX_PTY_PORT` |

PTY WebSocket 服务仅在 `TERMINAL` 能力组启用时，于后台守护线程中启动（见
[`SandboxServer.serve`](../../../server-sdk/src/agent_sandbox/server/app.py#L254-L280)）。`TERMINAL` 默认启用，因此 PTY 服务默认随主服务一起启动。

---

## 2. 能力组（Capability Groups）

每条路由是一个**端点**，有一个 id（见[细粒度能力](fine-grained-capabilities.md)）；声明表是 [`endpoints.py`](../../../server-sdk/src/agent_sandbox/server/endpoints.py)。**能力组**是一组端点 id 的名字。开关只有一个：端点规则。组名在所有接受它的地方（策略里的 `groups:`、代码里的 `enable_group()`、环境变量 `ABX_SERVER_ENABLED_GROUPS`）都展开成它包含的 id。端点规则前面没有第二道门。

| 能力组 | 枚举值 | 端点数 | 默认状态 | 说明 |
|--------|--------|:------:|:--------:|------|
| `CORE` | `core` | 3 | **始终启用**（不可禁用） | 健康检查、能力查询与检查 |
| `COMMANDS` | `commands` | 2 | 启用 | 命名命令列举与执行 |
| `FILE_OPS` | `file_ops` | 12 | 启用 | 文件上传/下载/列举/搜索/归档等 |
| `PROCESS` | `process` | 8 | 启用 | shell 执行、SSE 流式 shell、后台进程管理 |
| `TERMINAL` | `terminal` | 5 REST + WS | 启用 | PTY 会话管理 + WebSocket 交互终端 |
| `SYSTEM` | `system` | 6 | 启用 | 系统信息、环境变量、端口、包、指标 |
| `DEV_TOOLS` | `dev_tools` | 3 | **可选（默认关闭）** | 代码执行、Git 检查 |
| `BROWSER` | `browser` | 8 | **可选（默认关闭）** | Playwright 浏览器自动化 |
| `AGENTS` | `agents` | 70 | **可选（默认关闭）** | Agents API（`/v1/agents/...`、`/v1/vaults`、`/v1/responses` 等） |

`TERMINAL` 默认启用，因此 PTY WebSocket 服务默认随主服务一起启动。它在后台守护线程里运行，并且只在 `pty_connect` 启用时才启动。

### 2.1 层

一个端点的规则来自五层，按端点合并：default（可选组一开始是关的）、code（路由表上的 `enable_group` / `disable_group`）、preset、policy（`groups`、`defaults`、`endpoints`）、environment（`ABX_SERVER_ENABLED_GROUPS`，只能打开组）。更具体的选择器优先（精确 id，然后 glob，然后 `group:`，然后 `@defaults`）；同样具体时后面的层优先；同一层里只要有一条 `enabled: false`，该端点就是关的。`CORE`（`health`、`capabilities`、`capabilities_check`）不能禁用：`disable_group(CapabilityGroup.CORE)` 会抛出 `ValueError`。

每次拒绝都会指出是哪条规则：`404` 正文带 `code: endpoint_disabled` 和 `rule`（`policy:endpoints.shell`、`preset:read-only`、`code:enable_group:file_ops`、`default:opt-in:browser`）。

### 2.2 环境变量

`ABX_SERVER_ENABLED_GROUPS` 是逗号分隔的组名列表（`agents,dev_tools`），用来打开组。未知名字会让进程带着拼写建议退出。没有用来关闭组的变量；请在策略里写 `groups: {process: false}` 或 `endpoints` 规则。

### 2.3 代码 API

`RouteTable` 有两个代码级开关，都是修改端点规则里的 code 层：

| 方法 | 说明 |
|------|------|
| `enable_group(group)` | 打开该组的所有端点（对 `CORE` 为 no-op） |
| `disable_group(group)` | 关闭该组的所有端点（对 `CORE` 抛 `ValueError`） |

模板作者示例：

```python
from agent_sandbox.server import CapabilityGroup, default_table

table = default_table()
table.enable_group(CapabilityGroup.DEV_TOOLS)
```

`GET /capabilities` 按端点报告状态，并由它推导 `groups` 和 `group_summary`。

---

## 3. 认证

认证是 `SandboxRequestHandler._pipeline`（[`app.py`](../../../server-sdk/src/agent_sandbox/server/app.py)）里管线的第 2 步。

- Server 启动时读取环境变量 `ABX_SERVER_TOKEN`（`os.environ.get("ABX_SERVER_TOKEN") or None`）。
- **未设置 token**：本地模式，所有请求都跳过认证。调用方身份是 `anonymous`。
- **已设置 token**：请求必须在 `X-Access-Token` 或 `Authorization: Bearer <token>` 里带上 token（所有路由两种都接受），用 `hmac.compare_digest`（常量时间比较）校验。缺失或不匹配返回 `401`，响应体 `{"error": "unauthorized", "type": "AuthError"}`。两个不同的 `X-Access-Token` 值是 `400` `ambiguous_credentials`。

### 3.1 免认证端点

只有 `GET /health` 以 `auth_required=False` 注册（`GET /capabilities` 和 `POST /capabilities/check` 始终需要认证）：

| 端点 | 能力组 |
|------|--------|
| `GET /health` | `CORE` |

带 token 的请求示例：

```bash
curl -H "X-Access-Token: $ABX_SERVER_TOKEN" http://localhost:9000/system/info
```

### 3.2 分发顺序

只有一条管线，每条路由都按这个顺序经过：

1. 路径规范化：`urlparse` 后 `path.rstrip("/") or "/"`（去掉尾部斜杠）。
2. `RouteTable.match(method, path)`：匹配不到是 `404 {"error": "Not found: <path>", "type": "ValueError"}`。
3. 认证（仅当 `route.auth_required`）：失败是 `401`。
4. 策略引擎对匹配到的端点放行：是否启用（否则 `404 endpoint_disabled`，带 `rule`）、scope（`403 missing_scope`）、频率和并发上限（`429`）。
5. 重复的查询参数（`400 duplicate_parameter`）和 `Transfer-Encoding` 拒绝。
6. 对 `POST/PUT/PATCH/DELETE`，读取 JSON 请求体，受 `max_request_bytes` 限制（`413`）；解析失败是 `400`。
7. 调用处理函数（路径、命令、URL 和参数规则在这里生效）；`streaming=True` 走 SSE 分发路径。
8. 写审计记录。

> 只实现了 `do_GET` / `do_POST` / `do_DELETE`。`PUT` / `PATCH` 没有对应入口；标准库返回 `501`。

---

## 3.3 请求/响应数据模型

路由 handler 的输入输出使用标准库 `dataclass` 定义（非 Pydantic），源码位于
[`types.py`](../../../server-sdk/src/agent_sandbox/server/types.py)。

#### `ServerRequest`

经 `_dispatch` 解析后传入 handler 的请求对象。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `method` | `str` | — | HTTP 方法（大写，如 `"GET"`、`"POST"`） |
| `path` | `str` | — | URL 路径（如 `"/commands/greet"`） |
| `query` | `dict[str, list[str]]` | `{}` | 查询参数，每个 key 映射到值列表（支持重复 key） |
| `headers` | `dict[str, str]` | `{}` | 请求头（单值） |
| `body` | `dict[str, Any] \| None` | `None` | 解析后的 JSON 请求体；无体或非 JSON 时为 `None` |
| `path_params` | `dict[str, str]` | `{}` | 由 `{param}` 路由模板提取的路径参数 |
| `context` | `dict[str, Any]` | `{}` | 调度器注入的请求上下文（如 `"registry"` 键下的 `CommandRegistry`） |

#### `ServerResponse`

普通（非流式）handler 的返回类型。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `status` | `int` | — | HTTP 状态码（如 `200`、`404`） |
| `body` | `dict[str, Any]` | `{}` | JSON 可序列化的响应体 |
| `headers` | `dict[str, str]` | `{}` | 额外响应头 |

工厂方法：

| 方法 | 返回 | 说明 |
|------|------|------|
| `ServerResponse.ok(data)` | `ServerResponse(200, data)` | 成功响应 |
| `ServerResponse.error(status, message, error_type="ValueError")` | `ServerResponse(status, {"error": message, "type": error_type})` | 错误响应 |

#### `SSEResponse`

SSE 流式 handler（`streaming=True` 路由）的返回类型。

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `status` | `int` | `200` | HTTP 状态码 |
| `headers` | `dict[str, str]` | `{"Content-Type": "text/event-stream"}` | 响应头 |
| `event_iterator` | `Any` | `None` | 维生成 SSE 事件负载（`str` 或 `bytes`）的迭代器，逐条 flush 给客户端 |

---

## 4. 端点参考

响应体统一为 JSON。成功一般为 `200`；错误体统一形如
`{"error": "<message>", "type": "<ExceptionName>"}`（见
[`ServerResponse.error`](../../../server-sdk/src/agent_sandbox/server/types.py#L70-L88)）。

### 4.1 CORE（3）

#### `GET /health`

健康检查，始终返回 `200`，免认证。

响应：

```json
{"status": "ok"}
```

```bash
curl http://localhost:9000/health
```

#### `GET /capabilities`

列出全部能力组及其启用状态（配置了 token 时需要认证）。运行了策略（或任何 v2 服务端）会在该文档中额外返回 `api_version`、`server_version`、`identity`、`policy` 与 `endpoints`，见 10.4 节；`groups` 对象不变。

响应（`groups` 为 `{枚举值: bool}`）：

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

### 4.2 COMMANDS（2）

#### `GET /commands`

列出注册表中**可见**（非 `hidden`）的命令及其参数定义。

响应：

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

参数字段来自
[`handle_list_commands`](../../../server-sdk/src/agent_sandbox/server/routes.py#L96-L119)：
`name` / `type` / `required` / `default` / `description`。

#### `POST /commands/{name}`

执行一个已注册命令。请求体为该命令的关键字参数（kwargs）。

请求体示例：

```json
{"name": "Qoder"}
```

处理流程（见
[`handle_run_command`](../../../server-sdk/src/agent_sandbox/server/routes.py#L229-L269)）：

1. 命令不存在 → `404 {"error": "Unknown command '<name>'; available: ...", "type": "ValueError"}`。
2. 参数校验/类型转换失败 → `400`（缺少必填参数、传入未声明参数、类型无法转换）。
3. 命令函数抛异常 → `500 {"error": "...", "type": "<ExceptionName>"}`。
4. 成功 → `200 {"result": <返回值>}`。

类型强制转换支持 `string` / `integer` / `float` / `boolean`；布尔可接受
`true/false/yes/no/1/0`（见
[`_parse_boolean`](../../../server-sdk/src/agent_sandbox/server/routes.py#L130-L152)）。

```bash
curl -X POST http://localhost:9000/commands/hello \
  -H "Content-Type: application/json" \
  -d '{"name": "Qoder"}'
# -> {"result": "Hello, Qoder!"}
```

---

### 4.3 FILE_OPS（12）

包含 2 个「传统」上传/下载端点（`/upload`、`/download`，注册于
[`routes.py`](../../../server-sdk/src/agent_sandbox/server/routes.py#L454-L461)）与 9 个扩展文件操作端点（注册于
[`routes_files.py`](../../../server-sdk/src/agent_sandbox/server/routes_files.py#L528-L565)）。所有路径都会经过
路径 guard 的防护（见 §8.1）。

#### `POST /upload`

写入 base64 编码内容到本地文件。

请求体：

```json
{"path": "/home/user/file.txt", "content_base64": "<base64>"}
```

响应：`{"path": "<解析后的绝对路径>", "bytes": <字节数>}`。

错误：缺失/非法 `path` 或 `content_base64` → `400`；base64 非法 → `400`；写入失败 → `500`；
路径在允许的目录之外 → `403 {"code": "path_not_allowed", ...}`。

#### `GET /download?path=...`

读取文件，返回 base64 内容。

响应：

```json
{"path": "/home/user/file.txt", "content_base64": "<base64>"}
```

错误：缺失 `path` → `400`；文件不存在 → `404 {"type": "FileNotFoundError"}`；读取失败 → `500`。

#### `GET /files/list?path=...`

列出目录内容。查询参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `path` | （必填） | 目录路径 |
| `recursive` | `false` | `true/yes/1` 递归；递归最大深度 `3`（`_DEFAULT_MAX_DEPTH`） |
| `max_entries` | `1000` | 上限被裁剪至 `1000`（`_DEFAULT_MAX_ENTRIES`） |

响应：

```json
{
  "entries": [
    {"name": "a.txt", "type": "file", "size": 12, "modified": "2026-09-21T00:00:00+00:00"}
  ]
}
```

`type` 为 `file` 或 `directory`；`modified` 为 ISO 8601 UTC。指向 base 目录外的符号链接会被跳过。
目录不存在 → `404`。

#### `GET /files/stat?path=...`

返回单个文件/目录的元信息。文件不存在时仍返回 `200`，`exists=false`：

```json
{"name": "x", "path": "/home/user/x", "type": "unknown", "size": 0, "permissions": "", "modified": "", "exists": false}
```

存在时：`type` 为 `file`/`directory`/`symlink`，`permissions` 为八进制后三位（如 `"644"`），
`modified` 为 ISO 8601 UTC，`exists=true`。

#### `POST /files/mkdir`

创建目录（含父目录，`exist_ok=True`）。请求体 `{"path": "..."}`；成功
`{"path": "...", "created": true}`。

#### `DELETE /files?path=...`

删除文件或目录（目录用 `shutil.rmtree`）。成功 `{"path": "...", "deleted": true}`；
不存在 → `404`。

#### `POST /files/move`

移动/重命名。请求体：

```json
{"source": "/home/user/a.txt", "destination": "/home/user/b.txt"}
```

响应 `{"source": "...", "destination": "..."}`；源不存在 → `404`；`source`/`destination`
路径逃逸时错误前缀分别为 `source: ` / `destination: `。

#### `POST /files/search`

按 glob 模式（`fnmatch`）搜索文件。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `path` | （必填） | 搜索根目录 |
| `pattern` | （必填） | glob 模式，如 `*.py` |
| `max_depth` | `5`（`_SEARCH_MAX_DEPTH`） | 最大递归深度 |
| `max_results` | `100`（`_SEARCH_MAX_RESULTS`） | 最大结果数 |

超时上限 `10` 秒（`_SEARCH_TIMEOUT_SECONDS`，由定时器线程实现）。响应：

```json
{"results": [{"name": "app.py", "path": "/home/user/app.py"}], "timed_out": false}
```

#### `POST /files/upload-stream`

分块（64 KB）写入的 base64 上传，带大小上限。请求体
`{"path": "...", "content_base64": "..."}`。超过上限（默认 100 MB，可由
`ABX_MAX_UPLOAD_SIZE` 覆盖）→ `413`。成功 `{"path": "...", "bytes": N}`。

#### `GET /files/download-stream?path=...`

分块读取后返回 base64，额外带 `bytes` 字段：

```json
{"path": "...", "content_base64": "<base64>", "bytes": 1024}
```

文件不存在 → `404`。

#### `POST /files/archive`

将多个路径打包为归档并返回 base64。请求体：

```json
{"paths": ["/home/user/dir", "/home/user/a.txt"], "format": "tar.gz"}
```

`format` 支持 `tar.gz`（默认）或 `zip`；其他值 → `400`。限制：文件总数
`10000`（`_ARCHIVE_MAX_FILES`）、归档大小 `100 MB`（`_ARCHIVE_MAX_SIZE`，超出 → `413`）。
路径不存在 → `404`。响应：

```json
{"content_base64": "<base64>", "format": "tar.gz", "bytes": 2048}
```

---

### 4.4 PROCESS（8）

包含 `/shell`（注册于 [routes.py](../../../server-sdk/src/agent_sandbox/server/routes.py#L462-L465)）以及 SSE 流式 shell 与后台进程管理（注册于
[routes_process.py](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L268-L288)）。

#### `POST /shell`

同步执行 shell 命令（`shlex.split` + `shell=False`），300 秒超时。请求体：

```json
{"command": "ls -la /tmp"}
```

响应：

```json
{"stdout": "...", "stderr": "...", "exit_code": 0}
```

缺失/非法 `command` → `400`；超时 → `500 {"type": "TimeoutError"}`。

#### `POST /shell/stream`

执行命令并通过 **SSE** 流式返回输出（`streaming=True`）。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `command` | （必填） | 命令字符串 |
| `timeout` | `300` | 秒；`<=0` 或非法回退为 `300` |
| `cwd` | （空） | 工作目录，空则为 `None` |

SSE 事件格式见 §6。缺失/非法 `command` 或 `shlex` 解析失败 → `400`（普通 JSON 响应）。

#### `POST /process/start`

启动后台进程（`subprocess.Popen`）。请求体 `{"command": "...", "cwd": "..."}`。
进程数上限 `100`（`_MAX_PROCESSES`，超出 → `429 {"type": "ResourceError"}`）。成功：

```json
{"pid": 12345, "command": "sleep 60"}
```

#### `GET /process/list`

列出受管后台进程（列举前会清理已退出进程）。响应：

```json
{"processes": [{"pid": 12345, "command": "sleep 60", "state": "running", "started_at": 1758412800.0}]}
```

`state` 为 `running` 或 `exited`。

#### `GET /process/{pid}`

单进程详情。`pid` 非整数 → `400`；未受管 → `404 {"type": "NotFoundError"}`。响应：

```json
{"pid": 12345, "command": "sleep 60", "state": "exited", "started_at": 1758412800.0, "exit_code": 0}
```

`state=running` 时 `exit_code` 为 `null`。

#### `POST /process/{pid}/signal`

向受管进程发送信号。请求体 `{"signal": 15}`。

- 允许的信号白名单 `_ALLOWED_SIGNALS = {2, 9, 15, 18, 20}`（SIGINT/SIGKILL/SIGTERM/SIGCONT/SIGTSTP）；
  其他 → `400`。
- 拒绝对 `pid == 1` 或 Server 自身进程发信号 → `403 {"type": "PermissionError"}`。
- `pid` 非整数或缺失 `signal` → `400`；未受管 → `404`。

成功 `{"pid": 12345, "signal": 15}`。

---

### 4.5 TERMINAL（5 REST + WebSocket）

PTY 会话管理端点（注册于
[routes_pty.py](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L398-L410)）。WebSocket 交互协议见 §5。

> PTY 依赖 Unix `pty` 模块；非 Unix 平台上创建会话会抛 `OSError`（→ `500`）。会话上限
> `MAX_SESSIONS = 10`，空闲超时 `IDLE_TIMEOUT = 1800` 秒。

#### `POST /pty/sessions`

创建 PTY 会话。请求体（全部可选）：

| 字段 | 默认 | 说明 |
|------|------|------|
| `shell` | `/bin/bash` | shell 可执行文件 |
| `cols` | `80` | 终端列数 |
| `rows` | `24` | 终端行数 |
| `env` | `null` | 追加的环境变量映射 |

响应：

```json
{"session_id": "a1b2c3d4e5f6", "ws_url": "ws://localhost:9001/pty?session_id=a1b2c3d4e5f6", "pid": 4321}
```

`cols`/`rows` 非整数 → `400`；达到会话上限 → `429 {"type": "RuntimeError"}`；PTY 创建失败 →
`500 {"type": "OSError"}`。`ws_url` 中端口来自 `ABX_PTY_PORT`（默认 `9001`）。

#### `GET /pty/sessions`

列出活动会话（会先回收已死会话）。响应：

```json
{
  "sessions": [
    {"id": "a1b2c3d4e5f6", "pid": 4321, "created_at": 1758412800.0, "cols": 80, "rows": 24, "alive": true}
  ]
}
```

#### `DELETE /pty/sessions/{id}`

关闭并销毁会话。成功 `{"status": "closed", "session_id": "<id>"}`；缺失 id → `400`；
不存在 → `404`。

---

### 4.6 SYSTEM（6）

系统信息端点（注册于
[routes_system.py](../../../server-sdk/src/agent_sandbox/server/routes_system.py#L416-L440)）。全部仅用标准库实现（无 `psutil`）。

#### `GET /system/info`

OS / CPU / 内存 / 磁盘 / Python 版本：

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

内存优先解析 `/proc/meminfo`，非 Linux 回退到 `resource` 模块（较粗略）。

#### `GET /env`

列出环境变量。查询参数 `filter` 为逗号分隔白名单（仅返回其中的变量）。**名称包含
敏感 token（`TOKEN`/`SECRET`/`KEY`/`PASSWORD`/`CREDENTIAL`）的变量始终被排除**（见 §8.3）。

```json
{"variables": {"LANG": "C.UTF-8", "PWD": "/home/user"}}
```

#### `POST /env`

设置环境变量。请求体 `{"vars": {"KEY": "value"}}`。**受保护变量**
（`PATH`/`HOME`/`USER`/`SHELL`/`ABX_SERVER_TOKEN`）不可覆盖 → `403 {"type": "PermissionError"}`；
`vars` 非对象 → `400`。成功 `{"updated": ["KEY1", "KEY2"]}`（已排序）。

#### `GET /ports`

列出监听中的 TCP 端口。优先解析 `/proc/net/tcp` 与 `/proc/net/tcp6`（状态 `0A` = LISTEN），
为空时回退 `ss -tlnp`。响应：

```json
{"listening": [{"port": 8080, "protocol": "tcp", "address": "0.0.0.0", "pid": null}]}
```

> `pid` 在无 root 权限时通常为 `null`。

#### `GET /packages`

列出已安装包。查询参数 `manager` 为 `pip`（默认）或 `npm`；其他值 → `400`。
命令不存在（`FileNotFoundError`）时返回空列表而非报错；超时 → `500 {"type": "TimeoutError"}`。

```json
{"manager": "pip", "packages": [{"name": "requests", "version": "2.32.0"}]}
```

#### `GET /system/metrics`

实时资源指标：

```json
{
  "cpu_load_1m": 0.15, "cpu_load_5m": 0.10, "cpu_load_15m": 0.05,
  "memory_used_mb": 2048, "memory_total_mb": 8192, "memory_percent": 25.0,
  "disk_used_gb": 14.5, "disk_total_gb": 40.0, "disk_percent": 36.3,
  "uptime_seconds": 123.4
}
```

`uptime_seconds` 相对进程导入时刻（`_BOOT_TIME`）。

---

### 4.7 DEV_TOOLS（3）— 可选

代码执行与 Git 检查（注册于
[routes_devtools.py](../../../server-sdk/src/agent_sandbox/server/routes_devtools.py#L385-L397)）。使用前需
`default_table().enable_group(CapabilityGroup.DEV_TOOLS)`，否则请求返回 `404`（组被禁用）。

#### `POST /code/run`

在子进程中执行代码。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `code` | （必填） | 源代码字符串 |
| `language` | `python` | `python` / `node` / `bash`；其他 → `400` |
| `timeout` | `30` | 秒；上限 `300`（`_MAX_TIMEOUT`），`<=0` 回退 `30` |

语言映射：`python`→`python3 -c`，`node`→`node -e`，`bash`→`bash -c`。响应：

```json
{"stdout": "hello\n", "stderr": "", "exit_code": 0, "language": "python", "execution_time_ms": 42.5}
```

超时 → `408 {"type": "TimeoutError"}`；运行时缺失 → `500 {"type": "FileNotFoundError"}`。

#### `GET /git/status?path=...`

解析 `git status --porcelain -b`。查询参数 `path`（默认 `.`）。路径含 `..` 段 → `400`。
git 未安装 → `500`；超时 → `408`；git 返回非零 → `400 {"type": "GitError"}`。响应：

```json
{"branch": "main", "clean": false, "files": [{"path": "app.py", "status": "modified"}]}
```

`status` 取值：`modified`/`added`/`deleted`/`renamed`/`untracked`/`copied`/`unmerged`。

#### `GET /git/diff?path=...`

返回 `git diff` 文本与统计。查询参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `path` | `.` | 工作目录（含 `..` → `400`） |
| `staged` | `false` | `true` 时使用 `--staged` |
| `file` | （空） | 限定单个文件（含 `..` → `400`） |

diff 文本超过 1 MB（`_MAX_DIFF_BYTES`）会被截断并追加 `... (truncated at 1MB)`。响应：

```json
{"diff": "diff --git ...", "stats": {"files_changed": 3, "insertions": 10, "deletions": 2}}
```

---

### 4.8 BROWSER（8）— 可选

Playwright 无头浏览器控制（注册于
[routes_browser.py](../../../server-sdk/src/agent_sandbox/server/routes_browser.py#L484-L516)）。使用前需
`default_table().enable_group(CapabilityGroup.BROWSER)`。

> **Playwright 懒加载与 503 降级**：Playwright 在首次使用时才导入并启动
> （[`_get_playwright`](../../../server-sdk/src/agent_sandbox/server/routes_browser.py#L60-L96)）。
> 若未安装 `playwright`，所有浏览器端点返回
> `503 {"error": "Playwright is not installed. ...", "type": "RuntimeError"}`。
> 页面为进程内共享单例（同一 `page`），操作受 `_browser_lock` 串行化。

#### `POST /browser/navigate`

导航到 URL。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `url` | （必填） | 目标 URL |
| `wait_until` | `networkidle` | Playwright 等待条件 |
| `timeout` | `30000` | 毫秒；`<=0` 回退 `30000` |

响应 `{"url": "...", "title": "...", "status": 200}`。

#### `POST /browser/screenshot`

截图。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `selector` | `null` | 指定则截该元素；元素不存在 → `404` |
| `full_page` | `true` | 整页截图（无 selector 时） |
| `format` | `png` | `png` 或 `jpeg`（其他回退 `png`） |

响应 `{"image_base64": "...", "width": 1280, "height": 720}`。

#### `GET /browser/content?type=...`

获取页面内容。查询参数 `type`：`html`（默认，`page.content()`）或 `text`
（`page.inner_text("body")`）。响应 `{"content": "...", "url": "...", "title": "..."}`。

#### `POST /browser/click`

点击元素。请求体 `{"selector": "#btn", "timeout": 5000}`（`timeout` 毫秒，`<=0` 回退 `5000`）。
响应 `{"clicked": true, "selector": "#btn"}`。

#### `POST /browser/type`

向元素输入文本。请求体：

| 字段 | 默认 | 说明 |
|------|------|------|
| `selector` | （必填） | 目标选择器 |
| `text` | （必填） | 输入文本 |
| `delay` | `50` | 每字符延迟（毫秒），`<0` 回退 `50` |
| `clear` | `false` | 输入前是否先清空（`page.fill("")`） |

响应 `{"typed": true, "selector": "...", "text": "..."}`。

#### `POST /browser/evaluate`

执行 JavaScript。请求体 `{"script": "document.title", "timeout": 10000}`
（`timeout` 毫秒，作为默认超时，`<=0` 回退 `10000`）。响应 `{"result": <JS 返回值>}`。

#### `POST /browser/pdf`

生成 PDF。请求体 `{"format": "A4", "landscape": false}`。响应
`{"pdf_base64": "...", "pages": 1}`（`pages` 依据 `/Type /Page` 出现次数粗略统计，至少 `1`）。

#### `GET /browser/console`

返回已收集的 console 日志并**清空缓冲**。响应：

```json
{"logs": [{"type": "log", "text": "hello", "timestamp": 1758412800.0}]}
```

日志缓冲上限 `1000` 条（`_MAX_CONSOLE_LOGS`）。

---

## 5. WebSocket PTY 终端协议

实现见
[`pty_ws_handler`](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L426-L503)
与 [`start_pty_server`](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L546-L571)。
WebSocket 服务依赖 `websockets` 库，运行在独立端口（默认 `9001`）。

### 5.1 连接 URL

```
ws://<host>:<pty_port>/pty?session_id=<session_id>
```

`session_id` 必须来自先前的 `POST /pty/sessions`。缺失 `session_id` → 服务端以关闭码
`1008` 关闭并附 `"Missing session_id parameter"`；未知会话 → `1008` + `"Unknown session: <id>"`。

### 5.2 客户端 → 服务端消息（JSON 文本帧）

| `type` | 字段 | 说明 |
|--------|------|------|
| `input` | `data`（字符串） | 向 shell 写入的输入（会 UTF-8 编码） |
| `resize` | `cols`、`rows`（整数） | 调整终端尺寸；非整数则忽略该消息 |
| `signal` | `signal`（字符串） | 向 shell 进程组发送信号 |

`signal` 取值映射（`_SIGNAL_MAP`）：`SIGINT` / `SIGTERM` / `SIGKILL` / `SIGHUP` / `SIGQUIT`；
未识别的信号名会被忽略。非法 JSON 帧被静默丢弃。

```json
{"type": "input",  "data": "ls -la\n"}
{"type": "resize", "cols": 120, "rows": 40}
{"type": "signal", "signal": "SIGINT"}
```

### 5.3 服务端 → 客户端消息（JSON 文本帧）

| `type` | 字段 | 说明 |
|--------|------|------|
| `output` | `data`（字符串） | PTY 输出（UTF-8，`errors="replace"`） |
| `event` | `event`、`session_id`、`pid`? | 生命周期事件 |

`event` 取值：

- `started`：连接建立后立即发送，附 `session_id` 与 `pid`。
- `exited`：shell 进程结束后发送，附 `session_id`。

```json
{"type": "output", "data": "total 0\n"}
{"type": "event",  "event": "started", "session_id": "a1b2c3d4e5f6", "pid": 4321}
{"type": "event",  "event": "exited",  "session_id": "a1b2c3d4e5f6"}
```

### 5.4 会话生命周期

1. `POST /pty/sessions` 创建会话，取得 `session_id` 与 `ws_url`。
2. 连接 `ws_url`；服务端推送 `started` 事件后，后台读循环持续转发 `output`。
3. 客户端发送 `input`/`resize`/`signal` 消息。
4. shell 退出时推送 `exited`；或调用 `DELETE /pty/sessions/{id}` 主动销毁。

---

## 6. SSE 流式 Shell

端点：`POST /shell/stream`（PROCESS 组）。实现见
[`_handle_shell_stream`](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L64-L121)。
响应 `Content-Type: text/event-stream`（[`SSEResponse`](../../../server-sdk/src/agent_sandbox/server/types.py#L91-L107)），
事件以标准 SSE 帧 `event: <name>\ndata: <json>\n\n` 逐条 flush。

### 6.1 事件类型（来自代码确认）

| `event` | `data` 结构 | 触发时机 |
|---------|-------------|----------|
| `stdout` | `{"data": "<行文本>"}` | 每读到一行标准输出（已去除结尾 `\n`） |
| `stderr` | `{"data": "<行文本>"}` | stdout 读完后，逐行读取标准错误 |
| `error` | `{"error": "<message>"}` | 进程启动失败，或超时（`{"error": "timeout"}`） |
| `exit` | `{"exit_code": <int>}` | 进程结束（超时后也会补发一条 `exit`） |

> 实现说明：stdout 与 stderr 是**先读完 stdout 全部行，再读 stderr**，而非实时交错。
> 超时判断基于 stdout 读取循环内的 `time.monotonic()`。

### 6.2 示例

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

## 7. 扩展性（模板作者指南）

Server 的路由与命令均可由模板 `commands.py` 扩展，无需修改 SDK 源码。完整示例见
[`examples/templates/python-hello/commands.py`](../../../examples/templates/python-hello/commands.py)。

### 7.1 注册自定义 HTTP 路由

使用 [`RouteTable.route()`](../../../server-sdk/src/agent_sandbox/server/router.py#L175-L204) 装饰器（或 `register()`）。
路径模板支持 `{param}` 占位符，编译为命名捕获组 `(?P<param>[^/]+)`，通过
`request.path_params` 取用：

```python
from agent_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request) -> ServerResponse:
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})
```

`route()` / `register()` 关键字参数：`group`（必填）、`auth_required`（默认 `True`）、
`streaming`（默认 `False`）、`name`（默认 `"<METHOD> <path>"`）。路由按注册顺序匹配。

#### 自定义 SSE 流式端点

当路由注册时指定 `streaming=True`，handler 应返回
[`SSEResponse`](../../../server-sdk/src/agent_sandbox/server/types.py#L91-L107)，其
`event_iterator` 维生成标准 SSE 帧格式的字符串（参考
[`routes_process.py`](../../../server-sdk/src/agent_sandbox/server/routes_process.py#L64-L121) 的实现）：

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

客户端将收到 `Content-Type: text/event-stream` 响应，事件逐条 flush。

#### 免认证端点

设置 `auth_required=False` 可使端点在配置了 `ABX_SERVER_TOKEN` 时也无需认证（内置的
`GET /health` 即使用此模式）：

```python
from agent_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/public/status", group=CapabilityGroup.COMMANDS, auth_required=False)
def public_status(request) -> ServerResponse:
    return ServerResponse.ok({"status": "running", "public": True})
```

> 注意：免认证端点仍受能力组门禁约束，若其所属能力组被禁用则返回 `404`。

### 7.2 注册自定义命令

命名命令只有一种机制：用模块级的 [`command`](../../../server-sdk/src/agent_sandbox/server/registry.py) 装饰器注册函数。`GET /commands` 列出它，`POST /commands/{name}` 运行它。未显式提供 `args` 时，参数类型**由函数签名推断**（`int`→`integer`、`float`→`float`、`bool`→`boolean`、其他→`string`），是否必填也由此推断（无默认值即必填）：

```python
from agent_sandbox.server import command, start

@command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"

@command(hidden=True)                    # 可执行，但不出现在 GET /commands
def _debug_info() -> dict:
    import platform
    return {"python": platform.python_version()}

start(9000)
```

- `hidden=True`：命令仍可通过 `POST /commands/{name}` 执行，但不出现在 `GET /commands` 列表里。
- `scopes=(...)`：调用方必须具备的 scope；不具备的调用方既看不到也运行不了该命令。
- 注册表在服务启动时冻结；请在导入时注册。
- 测试可以把私有的 `CommandRegistry()` 传给 `SandboxServer(registry=...)`。

`CommandArg` 的 `type` 必须是 `string`/`integer`/`float`/`boolean` 之一，否则构造函数抛出 `ValueError`。

---

## 8. 安全模型

### 8.1 路径遍历防护

每个接收路径的端点（文件路由、`/shell` 和 `/process/start` 的 `cwd`、git 的 `path`）都通过同一个 `PathGuard`（[`guard.py`](../../../server-sdk/src/agent_sandbox/server/guard.py)）解析路径，guard 由端点的 `paths` 规则构造。默认边界是 `ABX_SERVER_BASE_DIR`（默认 `/home/user`）；策略可以设置 `base_dir`，或按端点设置 `paths.allow`、`paths.deny`、`paths.read_only`、`paths.symlinks`。guard 对路径做 `realpath`，总是拒绝 `/proc`、`/sys`、`/dev`，拒绝把 `/` 当作根，并用 `O_NOFOLLOW` 打开最后一段。违规是 `403 {"code": "path_not_allowed"}`（或 `path_denied`、`read_only`、`symlink_denied`）；没有存在性探测口。

- `/files/list`、搜索和归档会跳过 guard 拒绝的条目，以及指向边界之外的符号链接。

### 8.2 信号白名单

- `POST /process/{pid}/signal` 仅允许 `_ALLOWED_SIGNALS = {2, 9, 15, 18, 20}`；
  并拒绝对 `pid == 1` 或 Server 自身进程发信号（`403`）。
- WebSocket PTY 的 `signal` 消息仅接受 `_SIGNAL_MAP` 中的
  `SIGINT`/`SIGTERM`/`SIGKILL`/`SIGHUP`/`SIGQUIT`，且作用于 shell 进程组。

### 8.3 环境变量保护与脱敏

- **脱敏（`GET /env`）**：名称包含 `_ENV_BLACKLIST_TOKENS`
  （`TOKEN`/`SECRET`/`KEY`/`PASSWORD`/`CREDENTIAL`，大小写不敏感）的变量始终不返回。
- **保护（`POST /env`）**：`_PROTECTED_ENV_VARS`
  （`PATH`/`HOME`/`USER`/`SHELL`/`ABX_SERVER_TOKEN`）不可覆盖，命中即 `403`。
- **策略模式**：服务端自身的密钥（`ABX_SERVER_*` 以及所有已配置的 `token_env` 名称）还会从子进程（`shell`、`process_start`、`code_run`、git、PTY）的环境中移除，并被 `POST /env` 拒绝。

### 8.4 其他限制

| 限制项 | 值 | 位置 |
|--------|-----|------|
| shell / code / git 命令 | `shell=False` + 参数向量执行 | 各 handler |
| `/shell` 超时 | 300s | routes.py |
| `/code/run` 超时 | 默认 30s，上限 300s | routes_devtools.py |
| 上传大小上限 | 100 MB（`ABX_MAX_UPLOAD_SIZE` 可调） | routes_files.py |
| 归档文件数/大小 | 10000 / 100 MB | routes_files.py |
| 后台进程上限 | 100 | routes_process.py |
| PTY 会话上限 / 空闲超时 | 10 / 1800s | routes_pty.py |
| 认证比较 | `hmac.compare_digest`（恒定时间） | app.py |

---

## 9. 配置参考（环境变量总表）

| 环境变量 | 默认值 | 作用 | 读取位置 |
|----------|--------|------|----------|
| `ABX_SERVER_TOKEN` | （未设置 = 免认证） | 认证 token；设置后需 `X-Access-Token` 头匹配 | [app.py#L43](../../../server-sdk/src/agent_sandbox/server/app.py#L43) |
| `ABX_SERVER_BASE_DIR` | `/home/user` | 文件端点路径安全根目录 | [routes.py#L54-L55](../../../server-sdk/src/agent_sandbox/server/routes.py#L54-L55) |
| `ABX_SERVER_ENABLED_GROUPS` | （空） | 逗号分隔，要打开的能力组（`agents,dev_tools`）；唯一的组环境变量 | [policy.py](../../../server-sdk/src/agent_sandbox/server/policy.py) |
| `ABX_PTY_PORT` | `9001` | PTY WebSocket 端口，并写入 `ws_url` | [app.py#L247](../../../server-sdk/src/agent_sandbox/server/app.py#L247) / [routes_pty.py#L362](../../../server-sdk/src/agent_sandbox/server/routes_pty.py#L362) |
| `ABX_MAX_UPLOAD_SIZE` | `104857600`（100 MB） | `/files/upload-stream` 上传字节上限 | [routes_files.py#L39](../../../server-sdk/src/agent_sandbox/server/routes_files.py#L39) |

> HTTP 端口不由环境变量控制，而是 `start(port=...)` / `SandboxServer.serve(port=...)` 参数（默认 `9000`）。

---

---

## 10. 细粒度能力管理（v2）

设计与理由：[细粒度能力管理](fine-grained-capabilities.md)；评审记录：
[fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md)。未配置策略的服务端用默认策略运行同一个引擎（可选组关闭，路径限制在基目录之下）。

### 10.1 配置来源

先匹配者生效：`SandboxServer(policy=...)` / `serve --policy FILE --preset NAME` -> `ABX_SERVER_POLICY`（内联 JSON）-> `ABX_SERVER_POLICY_FILE` ->
`/etc/agent-sandbox/server-policy.json` -> 无（空策略；引擎仍然运行）。`template.yaml` 的 `server:` 块是同一份文档，由工具链编译为 JSON。未知键和未知端点 id
会在启动时报错并给出拼写建议。用 `agent-sandbox-server check-config --policy FILE [--strict] [--json] [--explain ENDPOINT --path P --scopes S --op read]` 校验。

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

每个端点（或 `defaults`）的规则键：`enabled`、`scopes`、`paths{allow, deny, read_only, symlinks}`、
`limits{max_bytes, max_request_bytes, max_entries, max_duration_seconds, max_output_bytes, timeout_seconds, rate_per_minute, max_concurrency}`、
`params{overwrite, allow_extensions, deny_extensions, allow_commands, deny_commands, languages, allowed_signals, url_allow, url_deny, block_private_networks, shells, env_deny, allow_vars, deny_vars}`、
`audit`（`off|deny|all`）。大小支持 `5MB`、`1GiB` 写法。

### 10.2 Scope

身份持有 scope（`files:read`、`files:write`、`files:delete`、`process:run`、`process:manage`、`terminal:use`、`system:read`、`system:write`、
`devtools:run`、`browser:use`、`commands:run`、`commands:run:<name>`、`core:read`（隐含）、`*`）。每个端点需要一个有文档的 scope
（`files_move` 同时需要 `files:write` **和** `files:delete`）；规则中的 `scopes` 会覆盖它。旧的 `ABX_SERVER_TOKEN` 对应身份 `legacy`，scope 为 `*`。

### 10.3 错误码

响应体保留 `{"error", "type"}`，并新增 `code`（以及 `endpoint`、`scope`、`limit`、`retry_after`）：

| HTTP | `type` | `code` |
|------|--------|--------|
| 400 | `ValueError` | `ambiguous_credentials`、`duplicate_parameter`、`unsupported_encoding`（`Content-Length` 格式错误是不带 `code` 的普通 400） |
| 401 | `AuthError` | `unauthorized` |
| 403 | `PolicyDenied` | `missing_scope`、`path_not_allowed`、`path_denied`、`read_only`、`symlink_denied`、`command_not_allowed`、`language_not_allowed`、`signal_not_allowed`、`shell_not_allowed`、`url_denied`、`extension_not_allowed`、`env_var_not_allowed`、`env_var_denied`、`process_denied` |
| 404 | `ValueError` | `endpoint_disabled`（对无发现权限的调用方与"路由不存在"无法区分） |
| 409 | `FileExistsError` | `file_exists`（`overwrite: false` 的上传） |
| 413 | `ValueError` | `payload_too_large`（附 `limit`） |
| 429 | `RateLimited` | `rate_limited`、`concurrency_limited`（附 `Retry-After`） |

被关闭的端点无论有没有加载策略文件，都带 `code: endpoint_disabled` 和 `rule`。

### 10.4 发现

`GET /capabilities`（v2 字段）：`api_version: 2`、`server_version`、`identity {id, scopes}`、`policy {preset, revision}`、
`groups` 和 `group_summary`（推导得出）、`endpoints{name -> {method, path, group, summary, streaming, enabled, allowed, reason, rule, scopes, limits, paths, params}}`、`warnings`。
`POST /capabilities/check`，请求体 `{"endpoint", "path"?, "op"?, "paths"?}`，返回对一次假设调用的策略判定；它只做策略计算，从不触碰文件系统（没有存在性探测口）。

### 10.5 新增与扩展的端点（客户端/服务端对齐）

| 端点 | 能力组 | 说明 |
|------|--------|------|
| `GET /files/watch?path=&recursive=&interval=&timeout=` | FILE_OPS | SSE：`ready`、`change{type: created\|modified\|deleted, path, is_dir}`、`end`；轮询实现，受 `limits.max_duration_seconds` 限制 |
| `POST /process/{pid}/stdin` | PROCESS | 请求体 `{data \| data_base64, eof}`；进程必须以 `stdin: true` 启动（否则 409） |
| `GET /process/{pid}/output?since=&wait=` | PROCESS | 基于游标的事件 `{seq, stream, data}`、`next`、`state`、`exit_code`、`dropped`；需要 `capture_output: true` |
| `GET /pty/sessions/{id}` | TERMINAL | 会话元数据 |
| `POST /pty/sessions/{id}/resize` | TERMINAL | `{cols, rows}`（1..1000） |
| `POST /capabilities/check` | CORE | 见 10.4 |
| `POST /shell`、`/shell/stream` | PROCESS | 增量参数 `cwd`、`env`、`timeout` |
| `POST /process/start` | PROCESS | 增量参数 `env`、`capture_output`、`stdin` |

完整列表（含 70 条 Agents 路由）在附录里。

### 10.6 容器入口

`agent-sandbox-server serve [--host --port --pty-port --commands FILE|MODULE --policy FILE --preset NAME --base-dir DIR]`、
`healthcheck [--host --port --timeout]`（退出码 0/1，用于 `ready_cmd` 与 Docker `HEALTHCHECK`）、`check-config`、`version`。基础镜像契约见
[base-image-and-server-sdk.md](base-image-and-server-sdk.md)。

---

## 附录：端点数量核对

声明表 `endpoints.py` 共 118 个端点：117 条 HTTP 路由，加 PTY WebSocket（`pty_connect`，`ws://host:9001/pty?session_id=...`）。

| 能力组 | 端点数 | 端点 |
|--------|:------:|------|
| CORE | 3 | `GET /health`, `GET /capabilities`, `POST /capabilities/check` |
| COMMANDS | 2 | `GET /commands`, `POST /commands/{name}` |
| FILE_OPS | 12 | `POST /upload`, `GET /download`, `GET /files/list`, `GET /files/stat`, `POST /files/mkdir`, `DELETE /files`, `POST /files/move`, `POST /files/search`, `POST /files/upload-stream`, `GET /files/download-stream`, `POST /files/archive`, `GET /files/watch` |
| PROCESS | 8 | `POST /shell`, `POST /shell/stream`, `POST /process/start`, `GET /process/list`, `GET /process/{pid}`, `POST /process/{pid}/signal`, `POST /process/{pid}/stdin`, `GET /process/{pid}/output` |
| TERMINAL | 6 | `POST /pty/sessions`, `GET /pty/sessions`, `GET /pty/sessions/{id}`, `POST /pty/sessions/{id}/resize`, `DELETE /pty/sessions/{id}`, `WS /pty` |
| SYSTEM | 6 | `GET /system/info`, `GET /env`, `POST /env`, `GET /ports`, `GET /packages`, `GET /system/metrics` |
| DEV_TOOLS | 3 | `POST /code/run`, `GET /git/status`, `GET /git/diff` |
| BROWSER | 8 | `POST /browser/navigate`, `POST /browser/screenshot`, `GET /browser/content`, `POST /browser/click`, `POST /browser/type`, `POST /browser/evaluate`, `POST /browser/pdf`, `GET /browser/console` |
| AGENTS | 70 | 70 条路由，在 `/v1/agents/...`、`/v1/vaults`、`/v1/responses`、`/v1/models`、`/v1/files`、`/v1/webhook_endpoints` 下；见 [Agents API 参考](../reference/agents-api.md) |
