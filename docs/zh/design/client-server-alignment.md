# 客户端 / 服务端对齐：差距矩阵

> 状态：**v2（已评审，见 fine-grained-capabilities-review.md）**。对 `easy-sandbox-server` 的每一条路由与 `easy-sandbox`（`api/`、`protocol/`）
> 以及客户端另外使用的 envd（E2B）协议所做的审计。「状态」列在工作落地时更新（最终统计见文末）。
> 英文版为准：[../../en/design/client-server-alignment.md](../../en/design/client-server-alignment.md)。
> 相关：[fine-grained-capabilities.md](fine-grained-capabilities.md)。

## 1. 两个数据通道

| 通道 | 进程 | 端口 | 谁访问它 | 协议 |
|------|------|------|----------|------|
| **envd**（平台注入，位于官方基础镜像中） | `/.fce2b/envd` | 49983 | `Sandbox.commands/files/code/get_terminal` | Connect RPC + `GET/POST /files` |
| **SandboxServer**（`easy-sandbox-server`，由模板作者提供） | `easy_sandbox.server` | 9000（+ PTY WS 9001） | 目前只有 `Sandbox.custom()` / `list_commands()` | 普通 HTTP/JSON、SSE、WS |

在这项工作之前，客户端只触达约 45 条服务端路由中的**两条**（`GET /commands`、`POST /commands/{name}`），其余都是只存在于服务端、SDK 够不到的。
反过来，客户端面向 envd 的接口也有服务端不提供的功能。

决定：服务端**不是** envd 的克隆。相反，客户端获得一个覆盖每条服务端路由的类型化 `ServerClient`（`Sandbox.server`），
服务端则增加少量端点（watch、后台进程 IO、PTY 控制），使其接口在合理处成为*面向 envd 的客户端模块的功能超集*。有意的不对称在第 4 节说明。

## 2. 服务端路由 -> 客户端覆盖

图例：状态 **NEW** = 本次工作新增，**OK** = 已经对齐，**N/A** = 有意单边（第 4 节）。

### 2.1 核心 / 命令

| 服务端路由 | 端点 ID | scope | 客户端（之前） | 客户端（之后） | 状态 |
|------------|---------|-------|----------------|----------------|------|
| `GET /health` | `health` | — | — | `ServerClient.health()` | NEW |
| `GET /capabilities` | `capabilities` | core:read | — | `ServerClient.discover()` -> `ServerCapabilities` | NEW |
| `POST /capabilities/check` | `capabilities_check` | core:read | — | `ServerClient.check()` / `caps.check_path()` | NEW（服务端+客户端） |
| `GET /commands` | `list_commands` | commands:list | `Sandbox._fetch_server_commands`（无类型） | `server.commands.list()` -> `ServerCommand[]`；`Sandbox.list_commands` 不变 | NEW 类型化 |
| `POST /commands/{name}` | `run_command` | commands:run | `Sandbox.custom` / `_call_server_command` | `server.commands.run(name, **kw)`；`Sandbox.custom` 不变 | NEW 类型化 + 错误 |

### 2.2 文件

| 服务端路由 | 端点 ID | envd/客户端对应物 | 客户端（之后） | 状态 |
|------------|---------|-------------------|----------------|------|
| `GET /files/list` | `files_list` | `files.list`（ListDir） | `server.files.list(path, recursive, max_entries)` | NEW |
| `GET /files/stat` | `files_stat` | `files.get_info`、`files.exists` | `server.files.stat(path)`、`.exists(path)` | NEW |
| `POST /files/mkdir` | `files_mkdir` | `files.make_dir` | `server.files.mkdir(path)` | NEW |
| `DELETE /files` | `files_delete` | `files.remove` | `server.files.delete(path)` | NEW |
| `POST /files/move` | `files_move` | `files.move/rename` | `server.files.move(src, dst)` | NEW |
| `POST /files/search` | `files_search` | —（envd 无对应物） | `server.files.search(path, pattern, ...)` | NEW |
| `POST /files/upload-stream` | `files_upload_stream` | `files.write/upload` | `server.files.upload(path, data)`、`.upload_file(local, remote)` | NEW |
| `GET /files/download-stream` | `files_download_stream` | `files.read/download` | `server.files.download(path)`、`.read_text`、`.download_file` | NEW |
| `POST /files/archive` | `files_archive` | — | `server.files.archive(paths, format)` | NEW |
| `GET /files/watch` | `files_watch` | `files.watch`（WatchDir） | `server.files.watch(path)` -> `ServerWatchEvent` 异步迭代器（`WatchEvent` 子类，带 `is_dir`） | NEW 服务端 + 客户端 |
| `POST /upload`（旧版） | `upload` | — | `server.files.upload_legacy(path, data)` | NEW（文档化的旧版） |
| `GET /download`（旧版） | `download` | — | `server.files.download_legacy(path)` | NEW（文档化的旧版） |

### 2.3 进程

| 服务端路由 | 端点 ID | envd/客户端对应物 | 客户端（之后） | 状态 |
|------------|---------|-------------------|----------------|------|
| `POST /shell` | `shell` | `commands.run` | `server.process.shell(command, cwd, env, timeout)` | NEW；服务端增加 `cwd`、`env`、`timeout`（增量） |
| `POST /shell/stream`（SSE） | `shell_stream` | `commands.stream` | `server.process.shell_stream(...)` 返回 `ShellEvent` 异步迭代器；`.run_stream(on_stdout=...)` | NEW；服务端增加 `env`（增量） |
| `POST /process/start` | `process_start` | `commands.start`（后台） | `server.process.start(command, cwd, env, capture_output, stdin)` | NEW；服务端增加 `env`、`capture_output`、`stdin`（默认关闭 = 今天的行为） |
| `GET /process/list` | `process_list` | `commands.list` | `server.process.list()` | NEW |
| `GET /process/{pid}` | `process_detail` | `commands.connect`（状态部分） | `server.process.get(pid)` | NEW |
| `POST /process/{pid}/signal` | `process_signal` | `commands.send_signal/kill` | `server.process.signal(pid, sig)`、`.kill(pid)` | NEW |
| `POST /process/{pid}/stdin` | `process_stdin` | `commands.send_stdin` | `server.process.send_stdin(pid, data)` | NEW 服务端 + 客户端 |
| `GET /process/{pid}/output` | `process_output` | `commands.connect`（输出部分） | `server.process.output(pid, since, wait)` | NEW 服务端 + 客户端 |

### 2.4 终端

| 服务端路由 | 端点 ID | 客户端对应物 | 客户端（之后） | 状态 |
|------------|---------|--------------|----------------|------|
| `POST /pty/sessions` | `pty_create_session` | `Sandbox.get_terminal` | `server.pty.create(...)` | NEW |
| `GET /pty/sessions` | `pty_list_sessions` | — | `server.pty.list()` | NEW |
| `GET /pty/sessions/{id}` | `pty_detail` | — | `server.pty.get(id)` | NEW 服务端 + 客户端 |
| `POST /pty/sessions/{id}/resize` | `pty_resize` | `TerminalSession.resize` | `server.pty.resize(id, cols, rows)` | NEW 服务端 + 客户端 |
| `DELETE /pty/sessions/{id}` | `pty_delete_session` | `TerminalSession.close` | `server.pty.delete(id)` | NEW |
| WS `:9001/pty?session_id=` | （scope terminal:use） | `TerminalSession` 使用的是 *envd* 的 `/terminal` 路径 | `server.pty.connect(id)` -> `PtyConnection`（说服务端 JSON 协议的异步上下文管理器：`send`、`resize`、`signal`、`recv`、`expect`、消息迭代） | NEW |

### 2.5 系统

| 服务端路由 | 端点 ID | envd 对应物 | 客户端（之后） | 状态 |
|------------|---------|-------------|----------------|------|
| `GET /system/info` | `system_info` | — | `server.system.info()` | NEW |
| `GET /system/metrics` | `system_metrics` | envd `GET /metrics` | `server.system.metrics()` | NEW |
| `GET /env` | `env_get` | envd `GET /envs` | `server.system.env(names)` | NEW |
| `POST /env` | `env_set` | — | `server.system.set_env(vars)` | NEW |
| `GET /ports` | `ports` | —（`Sandbox.network` 在本地计算 URL） | `server.system.ports()` | NEW |
| `GET /packages` | `packages` | — | `server.system.packages(manager)` | NEW |

### 2.6 开发者工具与浏览器（可选能力组）

| 服务端路由 | 端点 ID | 客户端对应物 | 客户端（之后） | 状态 |
|------------|---------|--------------|----------------|------|
| `POST /code/run` | `code_run` | `sandbox.code.run`（envd 代码解释器，有状态） | `server.devtools.run_code(code, language, timeout)` | NEW（无状态；见 N/A-2） |
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

## 3. 客户端/envd 功能 -> 服务端覆盖（反方向）

| 客户端能力（envd） | 服务端对应物 | 动作 |
|--------------------|--------------|------|
| `files.list/exists/get_info/make_dir/remove/move/rename` | `files_*` | 已覆盖（通过 `ServerClient.files` 对齐） |
| `files.read/read_bytes/write/upload/download` | `files_download_stream` / `files_upload_stream`（base64 JSON） | 已覆盖 |
| `files.watch`（WatchDir 流） | **缺失** | **新增** `files_watch`（SSE、轮询、有界） |
| `files.upload_url/download_url` | 无（预签名 URL 概念仅属于平台） | N/A-4 |
| `commands.run/stream` | `shell`、`shell_stream` | 已覆盖；补齐 `cwd/env/timeout` |
| `commands.start`（后台） | `process_start` | 已覆盖；新增 `env`、`capture_output`、`stdin` |
| `commands.list` | `process_list` | 已覆盖 |
| `commands.connect(pid)` | **缺失输出附着** | **新增** `process_output`（+ `?wait`） |
| `commands.send_stdin` | **缺失** | **新增** `process_stdin` |
| `commands.send_signal/kill` | `process_signal` | 已覆盖 |
| `ProcessProtocol.update`（经进程的 pty 缩放） | `pty_resize` | **新增**（仅 PTY） |
| `get_terminal`（envd WS `/terminal`） | 9001 上的 PTY WS + REST 会话创建 | 客户端 `server.pty` 实现服务端协议；envd 路径不变 |
| `code.run` / 上下文（CodeInterpreter RPC） | 仅 `code_run`（无状态） | N/A-2 |
| `network.get_url/get_host` | `ports`（监听端口） | 已覆盖；两个独立的概念 |
| `sandbox.custom` 机制 B | `commands` | 已覆盖 |

## 4. 有意的单边项

* **N/A-1 envd Connect RPC / `/files` multipart 不在服务端重新实现。** 基础镜像已经在 49983 上自带 envd；在 9000 上重复实现会让同一批操作出现两个事实来源，
  也多出一个需要加固的地方。`ServerClient` 只覆盖服务端自己的协议。
* **N/A-2 有状态的代码解释器上下文**（创建/列出/重启/移除）需要内核（`ipykernel`/Jupyter），这是沉重的非标准库依赖。官方 `code-interpreter-v1` 镜像在自己的端口上提供它；
  服务端提供的是无状态的 `code_run`。已文档化，不构建。
* **N/A-3 `Sandbox.pause/resume/set_timeout/kill`** 是平台控制面操作，不在容器内。
* **N/A-4 `files.upload_url/download_url`** 是 envd 的 URL 便利方法；服务端需要签名 URL（令牌处理），超出范围。
* **N/A-5 模板/构建 API** 属于控制面。
* **N/A-6 大文件下载的原始 octet-stream 响应体**：当前 `ServerResponse` 的设计是服务端响应为 JSON（base64）；`max_bytes` 限制可约束成本。后续候选项。
* **N/A-7 `agents` 能力组（OpenAI 兼容 Agents API）路由。** 它们归 Agents API 工作流（[agents-api.md](../../en/design/agents-api.md)）所有，拥有自己的客户端接口；
  它们按名称（`group == agents`）被排除在 `ServerClient.ENDPOINT_METHODS` 和矩阵完整性测试之外，因此新增 agents 路由不会破坏此守卫，而新增任何*其他*路由却没有客户端方法则会被它抓住。

## 5. 横切对齐

| 关注点 | 服务端 | 客户端 |
|--------|--------|--------|
| 错误 | `{error,type,code,...}`、状态码 | 映射为类型化异常（细粒度文档第 7 节） |
| 认证 | `X-Access-Token` / `Authorization: Bearer` | `ServerClient(token=...)` 发送 Bearer；网关头来自 `Sandbox.network` |
| 发现 | `GET /capabilities` v2 | `ServerCapabilities` |
| 流式 | SSE（`shell_stream`、`files_watch`）；`process_output` 为游标轮询（`process.follow()`） | 带确定性关闭的异步迭代器 |
| 同步 | — | 每个公共协程都有 `*_sync` 孪生，沿用同样的 `make_sync` 风格 |
| 限制 | 逐端点 | `caps.limit(endpoint, key)`；上传在 `max_bytes` 上快速失败 |

## 6. 测试策略

* 服务端：每个新端点和每个变更的请求参数都有单元测试；未变更默认行为有兼容测试。
* 客户端：`tests/test_api/server_e2e/test_server_client_*.py` 针对**空闲端口上的真实进程内 `SandboxServer`**（夹具位于 `tests/test_api/server_e2e/conftest.py`）运行矩阵中的每个方法；
  矩阵完整性测试通过声明的映射 `ServerClient.ENDPOINT_METHODS` 断言服务端路由表中的每条路由都有客户端方法，因此将来的路由不会悄悄丢掉客户端。

## 7. 评审后的变更（草案 v1 -> v2）

见 [fine-grained-capabilities-review.md](fine-grained-capabilities-review.md) 第 3 节。

* `process_output` 由有界环形缓冲支撑（`limits.max_output_bytes`，默认每进程 1 MiB），基于游标读取（`since=<offset>`）；`process_start(capture_output=false)` 保持今天的行为（输出被丢弃）。
* `ServerClient` 与基于 envd 的模块的决策表：代码必须在任何沙箱上都能工作时使用 `Sandbox.files/commands`；模板作者自带服务端、需要受策略限定且受 scope 检查的访问
  （或需要 envd 没有的端点：`files_search`、`files_archive`、`process_output`、浏览器、git）时使用 `Sandbox.server`。
* 流式方法在生成器 `aclose()` 时关闭 HTTP 响应；同步孪生返回支持 `close()` 的迭代器。
* 客户端把旧版服务端（`/capabilities` 中没有 `endpoints`）视为 `legacy=True`，并把*新*端点上的 404 映射为 `EndpointNotAvailableError`，绝不暴露原始 HTTP 错误。

## 8. 最终统计（按实际实现）

* 已审计的服务端路由：默认路由表中的 47 条 HTTP 路由（core 3、file_ops 12、process 8、terminal 5、system 6、dev_tools 3、browser 8、commands 2）加 PTY WebSocket（`pty_connect`）：
  **48 个端点 ID 全部已映射**，在 `ServerClient.ENDPOINT_METHODS` 中对应 59 个客户端方法（异步协程各带 `*_sync` 孪生；流式生成器没有同步孪生，改用收集型协程 `watch_for` / `run_stream`）。
* 已补齐的客户端到服务端差距：`files_watch`、`process_output`、`process_stdin`、`pty_resize` / 会话详情、`shell*` 的 `cwd`/`env`/`timeout`、`process_start` 的 `env`/`capture_output`/`stdin`。
* 有意的单边项：N/A-1 .. N/A-7。
* 类型化模型位于 `easy_sandbox.models.server`；错误位于 `easy_sandbox.models.errors`（E9xxx）；全部由 `tests/test_api/server_e2e/` 针对真实进程内 `SandboxServer` 验证。
