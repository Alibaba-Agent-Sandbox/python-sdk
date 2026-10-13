# 模板服务器 HTTP API

生成的模板包含 `Dockerfile`、`commands.py` 和 `template.yaml`。沙箱启动后，调用方通过 HTTP 访问它。`commands.py` 是容器的主进程：它建立路由表、注册命令，并调用 `SandboxServer.serve(port=9000)`。

Dockerfile 里的 `FROM` 镜像随模板而变。本 HTTP API 不变。凡是启动 `easy_sandbox.server` 的模板，都提供下面这些路由。服务器只用 Python 标准库（`ThreadingHTTPServer`）。它接受 `GET`、`POST` 和 `DELETE`。匹配前会去掉末尾斜杠（`/health/` 即 `/health`）。

已经在跑的服务器可以用 [`examples/templates/python-hello/call_api.py`](../../examples/templates/python-hello/call_api.py) 这种短客户端来调用。

---

## 如何访问沙箱

容器内服务器绑定 `0.0.0.0:9000`（`serve` 的默认端口）。从外面访问时，向 SDK 要该端口的公网地址：

```python
url = sandbox.network.get_url(9000)
# https://{port}-{sandbox_id}.{domain}
host = sandbox.network.get_host(9000)
```

`{domain}` 来自创建该沙箱的提供方。终端组开启时，对 `9001` 做同样的调用就是 PTY WebSocket 端口（`EBX_PTY_PORT`，默认 `9001`）。

如果你是在本机自己执行 `python3 commands.py`，基址就是 `http://127.0.0.1:9000`。

`template.yaml` 的 `ports` 必须包含 `9000`（使用终端时还要包含 `9001`），平台才会发布该端口。`sandbox.network.get_url` 只拼出主机名；容器里必须有进程在监听。

安全模式下，平台网关会要求它自己的访问头：

```python
headers = sandbox.network.get_access_headers()  # 可能包含 X-Access-Token
```

这个网关头和容器内进程校验的令牌是两回事。两者都使用头名称 `X-Access-Token`。下一节是容器内的校验。

---

## 认证

`SandboxServer` 在启动时读取一次 `EBX_SERVER_TOKEN`。

- 未设置或为空：所有路由都接受请求。这是本地模式。
- 已设置：以 `auth_required=True` 注册的路由（默认如此）要求头 `X-Access-Token` 与该变量一致，比较方式是 `hmac.compare_digest`。缺少或错误的令牌返回 `401`：

```json
{"error": "unauthorized", "type": "AuthError"}
```

`GET /health` 是唯一以 `auth_required=False` 注册的内置路由。设置了令牌时它仍然开放。

`GET /capabilities` 和 `POST /capabilities/check` 以 `auth_required=True` 注册。只有在 `EBX_SERVER_TOKEN` 未设置时，它们才不带头也能应答。设置了令牌时，请发送 `X-Access-Token`。

`agents` 组的 `/v1/agents/...` 路由同时接受 `Authorization: Bearer <token>`。其余路由只读取 `X-Access-Token`。这些 `/v1/` 处理函数的错误使用 OpenAI 信封 `{"error": {"message", "type", "param", "code"}}`。

不要把令牌写进 `commands.py`。用环境变量传入。`POST /env` 拒绝覆盖 `EBX_SERVER_TOKEN`，以及任何大写形式以 `EBX_` 开头的名字。

PTY WebSocket（端口 9001，路径 `/pty`）使用同一个变量。没有策略引擎时，它要求 `?token=` 等于 `EBX_SERVER_TOKEN`。有策略引擎时，它接受 `Authorization: Bearer`、`X-Access-Token` 或 `?token=`。

---

## 能力组

每条路由属于一个组。被关闭的组返回 `404`：

```json
{"error": "Built-in route '<name>' is disabled", "type": "ValueError"}
```

`core` 始终开启。`RouteTable.disable_group(CapabilityGroup.CORE)` 会抛出 `ValueError`。其他组的初始状态来自 `_DEFAULT_DISABLED`：

| 组 | 默认 | 开启的路由 |
|----|------|------------|
| `core` | 开启，不能关闭 | `GET /health`、`GET /capabilities`、`POST /capabilities/check` |
| `commands` | 开启 | `GET /commands`、`POST /commands/{name}` |
| `file_ops` | 开启 | `POST /upload`、`GET /download`，以及 `/files/*` |
| `process` | 开启 | `POST /shell`、`POST /shell/stream`、`/process/*` |
| `terminal` | 开启 | `/pty/sessions*`，以及端口 9001 上的 WebSocket |
| `system` | 开启 | `/system/info`、`/system/metrics`、`/env`、`/ports`、`/packages` |
| `dev_tools` | 关闭 | `POST /code/run`、`GET /git/status`、`GET /git/diff` |
| `browser` | 关闭 | `/browser/*`（Playwright；未安装时返回 `503`） |
| `agents` | 关闭 | `/v1/agents/...`、`/v1/vaults`、`/v1/responses`、`/v1/models`、`/v1/files` 和 `/v1/webhook_endpoints`，作为 Codex 与 Qwen Code 上的本地操作。`EBX_SERVER_ENABLED_GROUPS` 包含 `agents` 之前保持关闭 |

`commands.py` 用 `default_table().enable_group(CapabilityGroup.FILE_OPS)` 打开需要的组。`EBX_SERVER_DISABLED_GROUPS` 是逗号分隔的组名，在创建路由表时生效（`core` 会被忽略）。`EBX_SERVER_ENABLED_GROUPS` 在 `SandboxServer` 启动时生效，可以把默认关闭的组重新打开。

`template.yaml` 的 `capabilities`（`shell`、`files`、`code`、`terminal`、`ports`）是模板元数据。它们不会切换这些路由。生成的模板按下面的方式对齐：`files` ↔ `file_ops`，`shell` ↔ `process`，`code` ↔ `dev_tools`，`terminal` ↔ `terminal`，`ports` ↔ `system`。

---

## 通用响应规则

成功和错误体都是 JSON（`Content-Type: application/json; charset=utf-8`）。处理函数的错误形如：

```json
{"error": "<message>", "type": "<ExceptionName>"}
```

未知路径是 `404` `{"error": "Not found: <path>", "type": "ValueError"}`。处理函数里未捕获的异常是 `500`，带 `error` 和 `type`。策略拒绝（仅在加载了 `ServerPolicy` 时）会额外带上 `code`，有时还有 `endpoint`。

`POST` 和 `DELETE` 读取 JSON 对象正文。原始正文上限是 10 MiB（`413`，`code` 为 `payload_too_large`）。空正文变成 `{}`。非法 JSON 是 `400`。

流式路由（`streaming=True`）返回 `text/event-stream`。每个片段是 `event: <name>\ndata: <json>\n\n`。

文件路由把路径解析到 `EBX_SERVER_BASE_DIR` 之下（默认 `/home/user`）。逃出该目录的路径是 `400` `Path escapes base directory`。解码后的上传大小默认 100 MiB（`EBX_MAX_UPLOAD_SIZE`）。10 MiB 的 JSON 正文上限先生效，因此 base64 正文实际上到不了 100 MiB。

`POST /shell` 和进程启动用 `shlex.split` 拆分命令，并以 `shell=False` 执行。管道、重定向和 `$VAR` 不会被解释。需要 shell 时请使用 `bash -c '...'`。

---

## 内置路由

### `core`

#### `GET /health`

无需认证。始终 `200`。

```json
{"status": "ok"}
```

#### `GET /capabilities`

发现文档。没有加载策略时，`policy.configured` 为 `false`，`identity` 为 `{"id": "anonymous", "scopes": ["*"]}`。

```json
{
  "api_version": 2,
  "server_version": "<package version>",
  "groups": {"core": true, "commands": true, "file_ops": true, "process": true, "terminal": true, "system": true, "dev_tools": false, "browser": false, "agents": false},
  "identity": {"id": "anonymous", "scopes": ["*"]},
  "policy": {"preset": "default", "revision": "<16 hex chars>", "configured": false},
  "endpoints": {
    "health": {
      "method": "GET",
      "path": "/health",
      "group": "core",
      "streaming": false,
      "enabled": true,
      "allowed": true,
      "reason": null,
      "scopes": [],
      "limits": {},
      "params": {}
    }
  },
  "warnings": []
}
```

`groups` 是每一个 `CapabilityGroup` 取值及其是否启用。`endpoints` 以路由名为键，并且包含 `pty_connect`（`method` 为 `WS`，路径 `/pty`），那是 9001 端口上的 WebSocket，不是 9000 端口上的 HTTP 路由。调用方不被允许时，`reason` 为 `group_disabled`、`endpoint_disabled` 或 `missing_scope`，并且省略 `limits` / `params`。没有策略文件、也没有 `EBX_SERVER_POLICY` 时，`preset` 为 `default`，`revision` 是空策略的哈希，`configured` 为 `false`。加载了策略时 `configured` 为 `true`，`preset` / `revision` 来自该文档。

#### `POST /capabilities/check`

正文：

| 字段 | 必填 | 含义 |
|------|------|------|
| `endpoint` | 是 | 路由名，例如 `upload` 或 `shell` |
| `path` | 否 | 要检查的一个路径 |
| `paths` | 否 | 路径列表 |
| `op` | 否 | `read`、`write`、`delete` 或 `exec` |

不会报告路径是否存在。`200`：

```json
{"endpoint": "upload", "allowed": true, "code": null, "reason": null}
```

拒绝时 `allowed` 为 `false`，并填上 `code`（`unknown_endpoint`、`endpoint_disabled` 或路径策略码）。错误的正文是 `400`。

### `commands`

#### `GET /commands`

来自传给 `SandboxServer` 的 `CommandRegistry` 的可见命令（隐藏命令不列出）。`200`：

```json
{
  "commands": [
    {
      "name": "hello",
      "description": "Say hello.",
      "args": [
        {"name": "name", "type": "string", "required": false, "default": "World", "description": ""}
      ]
    }
  ]
}
```

`type` 为 `string`、`integer`、`float` 或 `boolean`。

#### `POST /commands/{name}`

正文是参数的 JSON 对象。`200`：

```json
{"result": "Hello, World!"}
```

`result` 是函数的返回值（必须能 JSON 序列化；不能序列化的值会被编码器转成字符串）。

| 状态 | 正文 |
|------|------|
| `400` | 缺少必填参数、出现未声明参数，或值无法转换。`type` 为 `ValueError` 或 `TypeError` |
| `404` | `Unknown command '<name>'; available: <按名排序>` — available 列表包含隐藏命令 |
| `500` | 函数抛出异常。`error` 是 `str(exc)`，`type` 是异常类名 |

转换规则：`integer` 用 `int`，`float` 用 `float`，`boolean` 接受 `true`/`false`/`yes`/`no`/`1`/`0`（不区分大小写）。其余类型变成 `str`。仅当省略该字段且注册的默认值不是 `None` 时才套用默认值。

### `file_ops`

路径来自查询参数或正文，见各条说明。时间戳是 ISO 8601 UTC。

#### `POST /upload`

```json
{"path": "/home/user/note.txt", "content_base64": "<standard base64>"}
```

`200`：`{"path": "<resolved>", "bytes": <int>}`。

| 状态 | 条件 |
|------|------|
| `400` | 缺少 `path` 或 `content_base64`、base64 非法，或路径逃出基目录 |
| `413` | 解码后大小超过 `EBX_MAX_UPLOAD_SIZE`（默认 104857600）。有策略时正文还带 `code: "payload_too_large"` 和 `limit` |
| `500` | 写入失败 |

会创建父目录。有策略时，`allow_extensions` / `deny_extensions` 可以拒绝后缀（`extension_not_allowed`），`overwrite: false` 在文件已存在时返回 `409`。

#### `GET /download?path=`

`200`：

```json
{"path": "<resolved>", "content_base64": "<standard base64>"}
```

路径缺失或逃逸是 `400`，不是普通文件是 `404`，超过同一字节上限是 `413`，读失败是 `500`。

#### `GET /files/list?path=`

| 查询 | 默认 | 含义 |
|------|------|------|
| `path` | — | 目录（必填） |
| `recursive` | `false` | `true` / `yes` / `1` 时递归子目录 |
| `max_entries` | `1000` | 上限，也会被策略的 `max_entries` 再限制 |

`200`：`{"entries": [{"name", "type", "size", "modified"}]}`。`type` 为 `directory` 或 `file`（`follow_symlinks=False`，因此符号链接记为 `file`）。递归深度停在 3（策略设置了 `max_depth` 时用该值）。路径不是目录时为 `404`。

#### `GET /files/stat?path=`

路径不存在时也是 `200`：

```json
{
  "name": "note.txt",
  "path": "/home/user/note.txt",
  "type": "file",
  "size": 12,
  "permissions": "644",
  "modified": "2026-10-12T00:00:00+00:00",
  "accessed": "2026-10-12T00:00:00+00:00",
  "created": "2026-10-12T00:00:00+00:00",
  "exists": true
}
```

`type` 为 `file`、`directory`、`symlink`；什么都没有时为 `unknown`（时间为空字符串，`exists: false`）。`permissions` 是 `st_mode` 的末三位八进制。

#### `POST /files/mkdir`

`{"path": "/home/user/out"}`。`200`：`{"path": "<resolved>", "created": true}`。使用 `exist_ok`。错误路径是 `400`，`OSError` 是 `500`。

#### `DELETE /files?path=`

删除文件或整个目录树。`200`：`{"path": "<resolved>", "deleted": true}`。不存在是 `404`。有策略时，删除基目录本身，或删除含有被拒绝路径的目录树，会被拒绝。

#### `POST /files/move`

`{"source": "/home/user/a", "destination": "/home/user/b"}`。`200`：`{"source": "<resolved>", "destination": "<resolved>"}`。任一字段缺失是 `400`（消息以 `source:` 或 `destination:` 开头），源不存在是 `404`。会创建目标的父目录。

#### `POST /files/search`

```json
{"path": "/home/user", "pattern": "*.py", "max_depth": 5, "max_results": 100}
```

`pattern` 是对文件名的 `fnmatch`。默认深度 5、最多 100 条、遍历 10 秒。`200`：

```json
{"results": [{"name": "a.py", "path": "/home/user/a.py"}], "timed_out": false}
```

`path` 不是目录时为 `404`。非整数的限制是 `400`。

#### `POST /files/upload-stream`

正文和成功形状与 `POST /upload` 相同（`path`、`bytes`）。处理函数仍然接收一整份 JSON 正文；它按 64 KiB 分块写入解码后的字节。

#### `GET /files/download-stream?path=`

与 `GET /download` 相同，并多一个 `bytes`：

```json
{"path": "<resolved>", "content_base64": "...", "bytes": 12}
```

#### `POST /files/archive`

```json
{"paths": ["/home/user/proj"], "format": "tar.gz"}
```

`format` 为 `tar.gz`（默认）或 `zip`。`200`：

```json
{"content_base64": "...", "format": "tar.gz", "bytes": 1200}
```

限制：10000 个文件、归档字节 100 MiB（策略的 `max_files` / `max_bytes` 可以再降低）。文件过多是 `400`。归档过大是 `413`。输入路径不存在是 `404`。指向基目录之外的符号链接会被跳过。

#### `GET /files/watch?path=`

SSE。查询参数：`recursive`（`false`），`interval` 秒（默认 `0.5`，夹在 `0.1`–`5`），`timeout` 秒（默认 `300`，最小 `0.1`，并受策略 `max_duration_seconds` 限制）。

| 事件 | 数据 |
|------|------|
| `ready` | `{"path": "<resolved>"}` |
| `change` | `{"type": "created"\|"modified"\|"deleted", "path": "...", "is_dir": false}` |
| `end` | `{"reason": "timeout"}` |

非法的 interval 或 timeout 是 `400`，`path` 不是目录是 `404`。这是轮询，不是 inotify 流。最多跟踪 5000 个条目。

### `process`

shell 和进程启动正文里的 `cwd`、`env`、`timeout` 都可选。`cwd` 必须是字符串，且是已存在的目录（加载了策略时会解析到基目录之下）。`env` 必须是值为字符串的对象。`timeout` 默认 300 秒；非正数或非数字会换回 300。策略可以降低超时（`timeout_seconds`）并限制输出（`max_output_bytes`，这会让 `/shell` 带上 `"truncated": true`）。

#### `POST /shell`

```json
{"command": "ls -la /tmp", "cwd": "/tmp", "env": {"A": "1"}, "timeout": 30}
```

`200`：

```json
{"stdout": "...", "stderr": "", "exit_code": 0}
```

`exit_code` 是进程返回码，包括非零。`command` 缺失或 `cwd`/`env` 类型不对是 `400`。`shlex` 失败是 `500`。超时是 `500` `{"error": "Command timed out after <n>s", "type": "TimeoutError"}`。

#### `POST /shell/stream`

正文相同。SSE 按行输出（去掉行尾换行）：

| 事件 | 数据 |
|------|------|
| `stdout` | `{"data": "<line>"}` |
| `stderr` | `{"data": "<line>"}` |
| `error` | `{"error": "timeout"}` 或 `{"error": "output_limit"}` 或 `{"error": "<message>"}` |
| `exit` | `{"exit_code": 0}` |

这里的 `shlex` 失败是 `400`，不是 `500`。

#### `POST /process/start`

```json
{"command": "sleep 30", "cwd": "/tmp", "env": {}, "capture_output": false, "stdin": false}
```

`200`：`{"pid": 123, "command": "sleep 30"}`。服务器最多保留 100 个存活进程（已满时 `429` `ResourceError`；已退出的记录会先被丢掉）。`capture_output: true` 保存 stdout 和 stderr（默认上限 1 MiB；更早的片段会被丢弃）。`stdin: true` 保持 stdin 打开，供 `/process/{pid}/stdin` 写入。错误的命令或 `shlex` 错误是 `400`，`Popen` 失败是 `500`。

#### `GET /process/list`

`200`：`{"processes": [{"pid", "command", "state", "started_at"}]}`。`state` 为 `running`（这次调用会移除已退出的进程）。`started_at` 是 Unix 时间戳（`time.time()`）。

#### `GET /process/{pid}`

`200`：

```json
{"pid": 123, "command": "sleep 30", "state": "running", "started_at": 1700000000.0, "exit_code": null}
```

`state` 为 `running` 或 `exited`。退出前 `exit_code` 为 `null`。`pid` 不是整数是 `400`，不是本服务器启动的 pid 是 `404`。

#### `POST /process/{pid}/signal`

`{"signal": 15}`。允许的信号：`2`（SIGINT）、`9`（SIGKILL）、`15`（SIGTERM）、`18`（SIGCONT）、`20`（SIGTSTP）。`200`：`{"pid": 123, "signal": 15}`。其他信号是 `400`。pid 1 和服务器自己的 pid 是 `403`。未知 pid 是 `404`。

#### `POST /process/{pid}/stdin`

仅用于以 `stdin: true` 启动的进程。

```json
{"data": "hello\n", "eof": false}
```

`data` 是 UTF-8 文本。也可以用 `data_base64`。`eof: true` 关闭 stdin。`data`、`data_base64`、`eof` 至少要有一个。`200`：`{"pid": 123, "written": 6, "closed": false}`。未启用 stdin 或已经关闭是 `409`。非法 base64 或非字符串 `data` 是 `400`。

#### `GET /process/{pid}/output?since=0&wait=0`

仅当启动时 `capture_output` 为 true（否则 `409`）。`since` 是序号（默认 `0`）。`wait` 秒（默认 `0`，最大 `30`）会阻塞到有新数据或进程结束。`200`：

```json
{
  "pid": 123,
  "events": [{"seq": 0, "stream": "stdout", "data": "hi"}],
  "next": 1,
  "state": "running",
  "exit_code": null,
  "dropped": false
}
```

`dropped: true` 表示捕获缓冲区丢掉了更早的事件。

### `terminal`

HTTP 路由管理会话。按键走 `EBX_PTY_PORT`（默认 `9001`）上的 WebSocket，仅在本组启用时才会启动。创建时允许的 shell：`/bin/bash`、`/bin/sh`、`/bin/zsh`、`/usr/bin/bash`、`/usr/bin/zsh`。最多 10 个会话。空闲 1800 秒的会话会在下次创建或列出时被回收。

#### `POST /pty/sessions`

```json
{"shell": "/bin/bash", "cols": 80, "rows": 24, "env": {"LANG": "C.UTF-8"}}
```

`200`：

```json
{"session_id": "<12 hex chars>", "ws_url": "ws://localhost:9001/pty?session_id=<id>", "pid": 123}
```

`ws_url` 使用 `localhost` 拼出；当设置了 `EBX_SERVER_TOKEN` 且服务器没有按身份区分令牌时，还会带上 `&token=<经过 URL 编码的令牌>`。从沙箱外连接时，在 `sandbox.network.get_url(9001)` 的路径 `/pty` 上打开 WebSocket，查询参数相同。达到会话上限是 `429`。shell 不在名单里或尺寸不是整数是 `400`。`env` 里的 `LD_PRELOAD`、`LD_LIBRARY_PATH` 和 `DYLD_INSERT_LIBRARIES` 会被去掉。

#### `GET /pty/sessions`

`200`：`{"sessions": [{"id", "pid", "created_at", "cols", "rows", "alive"}]}`。

#### `GET /pty/sessions/{id}`

`200`：一个会话对象（`id`、`pid`、`created_at`、`cols`、`rows`、`alive`）。已经不在了是 `404`。

#### `POST /pty/sessions/{id}/resize`

`{"cols": 120, "rows": 40}`。两者都是必填整数，范围 1 到 1000。`200` 返回会话对象。

#### `DELETE /pty/sessions/{id}`

`200`：`{"status": "closed", "session_id": "<id>"}`。不存在是 `404`。

#### WebSocket `/pty?session_id=`

客户端 → 服务器：

```json
{"type": "input", "data": "ls\n"}
{"type": "resize", "cols": 120, "rows": 40}
{"type": "signal", "signal": "SIGINT"}
```

`signal` 接受 `SIGINT`、`SIGTERM`、`SIGKILL`、`SIGHUP`、`SIGQUIT`。

服务器 → 客户端：

```json
{"type": "output", "data": "..."}
{"type": "event", "event": "started", "session_id": "<id>", "pid": 123}
{"type": "event", "event": "exited", "session_id": "<id>"}
```

认证失败以关闭码 `4001` 断开。终端被关闭时关闭码为 `4003`。

### `system`

#### `GET /system/info`

`200`：

```json
{
  "os": "Linux",
  "arch": "x86_64",
  "cpu_count": 2,
  "memory_total_mb": 2048,
  "memory_available_mb": 1024,
  "disk_total_gb": 20.0,
  "disk_free_gb": 10.0,
  "python_version": "3.11.0",
  "hostname": "sandbox"
}
```

有 `/proc/meminfo` 时内存从那里读取。磁盘是 `shutil.disk_usage("/")`。

#### `GET /system/metrics`

`200`：`cpu_load_1m`、`cpu_load_5m`、`cpu_load_15m`、`memory_used_mb`、`memory_total_mb`、`memory_percent`、`disk_used_gb`、`disk_total_gb`、`disk_percent`、`uptime_seconds`。uptime 是自本模块被导入以来的秒数。

#### `GET /env`

`200`：`{"variables": {"HOME": "/home/user"}}`。名字中含有 `TOKEN`、`SECRET`、`KEY`、`PASSWORD` 或 `CREDENTIAL`（任意大小写）的变量会被省略。查询参数 `filter` 是逗号分隔的名字白名单。策略可以再加上 `allow_vars` / `deny_vars` 通配。

#### `POST /env`

`{"vars": {"LANG": "C.UTF-8"}}`。`200`：`{"updated": ["LANG"]}`。任一键是 `PATH`、`HOME`、`USER`、`SHELL`，或大写后以 `EBX_` 开头，则 `403`。`vars` 不是对象是 `400`。值以 `str()` 存入。

#### `GET /ports`

`200`：`{"listening": [{"port": 9000, "protocol": "tcp", "address": "0.0.0.0", "pid": null}]}`。从 `/proc/net/tcp` 和 `/proc/net/tcp6` 读取（只看 LISTEN）。两者都空时，处理函数运行 `ss -tlnp`。只有 `ss` 回退路径才会填 `pid`。

#### `GET /packages?manager=pip`

`manager` 为 `pip`（默认）或 `npm`。`pip` 运行 `python -m pip list --format json`。`npm` 运行 `npm list --json --depth=0`。`200`：`{"manager": "pip", "packages": [{"name": "pip", "version": "24.0"}]}`。未知的管理器是 `400`。找不到可执行文件时 `packages` 为空列表。超时 10 秒（`500` `TimeoutError`）。

### `dev_tools`（启用前关闭）

#### `POST /code/run`

```json
{"code": "print('hello')", "language": "python", "timeout": 30}
```

`language` 为 `python`（`python3 -c`）、`node`（`node -e`）或 `bash`（`bash -c`）。默认超时 30 秒，最大 300。`200`：

```json
{
  "stdout": "hello\n",
  "stderr": "",
  "exit_code": 0,
  "language": "python",
  "execution_time_ms": 12.34,
  "_security_note": "Security relies on container isolation, not application-level restrictions"
}
```

超时是 `408`。运行时二进制不存在是 `500`。策略的 `languages` 列表可以拒绝某种语言。

#### `GET /git/status?path=.`

`200`：`{"branch": "main", "clean": true, "files": [{"path": "a.py", "status": "modified"}]}`。`status` 为 `modified`、`added`、`deleted`、`renamed`、`untracked`、`copied` 或 `unmerged`。git 失败（不是仓库）是 `400` `GitError`。未安装 `git` 是 `500`。30 秒超时是 `408`。设置了 `EBX_SERVER_BASE_DIR` 时，`path` 必须留在该目录内。

#### `GET /git/diff`

查询参数：`path`（默认 `.`），`staged`（`true`/`yes`/`1` 会加上 `--staged`），`file`（可选的 pathspec）。`200`：

```json
{"diff": "<unified diff>", "stats": {"files_changed": 1, "insertions": 2, "deletions": 0}}
```

diff 文本在 1 MiB 处截断，并附上一行截断说明。git 错误与 status 相同。

### `browser`（启用前关闭）

下面这些都需要 Playwright。如果 `import playwright` 失败，处理函数返回 `503` `RuntimeError`，并提示 `pip install playwright && playwright install chromium`。第一次使用时创建一个共享的无头 Chromium 页面。没有按请求区分的浏览器 id。

| 路由 | 正文或查询 | `200` 正文 |
|------|------------|------------|
| `POST /browser/navigate` | `url`（必填），`wait_until` 默认 `networkidle`，`timeout` 毫秒默认 `30000` | `url`、`title`、`status`（导航的 HTTP 状态，或 `0`） |
| `POST /browser/screenshot` | `selector` 可选，`full_page` 默认 `true`，`format` 为 `png` 或 `jpeg` | `image_base64`、`width`、`height` |
| `GET /browser/content` | 查询 `type`：`html`（默认）或 `text` | `content`、`url`、`title` |
| `POST /browser/click` | `selector`（必填），`timeout` 毫秒默认 `5000` | `clicked: true`、`selector` |
| `POST /browser/type` | `selector`、`text`（必填），`delay` 毫秒默认 `50`，`clear` 默认 `false` | `typed: true`、`selector`、`text` |
| `POST /browser/evaluate` | `script`（必填），`timeout` 毫秒默认 `10000` | `result`（`page.evaluate` 返回的 JSON 值） |
| `POST /browser/pdf` | `format` 默认 `A4`，`landscape` 默认 `false` | `pdf_base64`、`pages` |
| `GET /browser/console` | 无 | `logs`：`[{type, text, timestamp}]`，然后清空缓冲区（最多 1000 条） |

screenshot 的 `selector` 匹配不到时是 `404`。策略可以限制 navigate 的 `url`（`url_allow`、`url_deny`、`block_private_networks`）。第一个 URL 之后的重定向不会被过滤。

### `agents`（默认关闭）

用 `EBX_SERVER_ENABLED_GROUPS=agents` 打开（或在 `serve()` 之前调用 `default_table().enable_group(CapabilityGroup.AGENTS)`）。目前支持 Codex CLI（`codex`）和 Qwen Code（`qwen-code`，别名 `qwen`、`qwencode`）。目前未支持的适配器名称返回 `404` `not_found_error`，并带 `x-should-retry: false`。请求没有点名适配器，且没有 `agents.default`（`EBX_AGENTS_DEFAULT`）时，创建类调用使用顺序里的第一个：`codex`。每个 Agents 路由都可以单独放行，端点 id 见[细粒度能力](fine-grained-capabilities.md)，默认 scope 是 `agents:use`。

这里每个路由都是本地操作。每个响应都带 `X-Easy-Sandbox-Local: 1`，每个对象都带 `x_easy_sandbox` 标记（`local`、`compute`、`differences`）。服务端做不到的字段返回带 `param` 的 `400`，绝不先接受再忽略。对象归调用者所有；别人的 id 与不存在的 id 得到相同的应答。

| 路由 | 行为 |
|------|------|
| `POST /v1/agents/sessions` | 用内联 `agent` 或 `agent_id` 创建会话，可带 `environment`（`{"id": "env_..."}`）和 `vault_ids`。字符串 `input` 会排入第一回合。 |
| `GET /v1/agents/sessions` | 列出会话（可按 `agent_id` 过滤）。 |
| `GET`、`POST`、`DELETE /v1/agents/sessions/{id}` | 一个会话。`POST` 只更新 `metadata`。 |
| `POST /v1/agents/sessions/{id}/events` | 排入一个回合。**HTTP 202，空响应体。** 相同的 `Idempotency-Key` 会重放这个 202。 |
| `GET /v1/agents/sessions/{id}/events` | 会话事件的 SSE（`Accept: text/event-stream`）。 |
| `GET .../items`、`.../turns`、`.../turns/{turn_id}`、`.../turns/{turn_id}/items` | 条目和回合。 |
| `GET .../artifacts`、`GET` 和 `DELETE .../artifacts/{id}`、`GET .../artifacts/{id}/content` | CLI 报告的路径的不可变副本。删除只删副本。 |
| `GET .../traces` | 除非 `EBX_AGENTS_TRACES=1`，否则为空（只含时间的 span）。 |
| `GET .../subagents`、`.../subagents/{id}`、`/items`、`/turns`、`/turns/{turn_id}`、`/turns/{turn_id}/items` | 只有 CLI 给出过的 id。 |
| `POST`、`GET /v1/agents`，`GET`、`POST`、`DELETE /v1/agents/{agent_id}` | Agent 定义。只有 `mcp` 工具。 |
| `POST`、`GET /v1/agents/environments`，`GET /v1/agents/environments/{id}` | 目录绑定。 |
| `POST`、`GET /v1/agents/environments/{id}/files` | 在工作目录下写入（绝不覆盖）和列出文件。 |
| `/v1/agents/environments/templates[...]` | 精简模板：`{name, env, 内联文件}`。 |
| `POST /v1/files` | 本地 `user_data` blob，使 `file_id` 可用（JSON 正文，`data` 为 base64）。 |
| `/v1/vaults[...]`、`/v1/vaults/{id}/credentials[...]` | 仅内存的 vault，以及只写的 `static_bearer` / `mcp_oauth` 凭据。 |
| `POST /v1/responses`、`GET`、`DELETE /v1/responses/{id}`、`POST .../cancel`、`GET .../input_items`、`POST /v1/responses/compact` | 带标记的一次性 CLI 回合。 |
| `GET /v1/models`、`GET /v1/models/{id}` | 定义和两个适配器。 |
| `/v1/webhook_endpoints[...]`、`GET /v1/webhook_event_types` | 本地带签名的 webhook 端点。 |
| `GET /v1/agents/runtimes` | 只有 `codex` 和 `qwen-code`。 |

没有本地能力，返回 `404` `not_found_error`（`agents.not_implemented_locally`，`x-should-retry: false`）：`POST /v1/responses/input_tokens`、`DELETE /v1/models/{id}`，以及执行器注册和通道。

对应的 CLI 在会话真正用到时才安装。每条拒绝规则、环境变量和 difference 代码见[托管 Agent](hosted-agents.md)。目前支持的适配器、本地响应头，以及未支持名称和 `input_tokens` 的 404，见[最佳实践](hosted-agents.md#最佳实践)。

---

## 自定义命令与自定义路由

### `@registry.command`

```python
from easy_sandbox.server import CommandRegistry, SandboxServer

registry = CommandRegistry()

@registry.command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"

@registry.command(hidden=True)
def _debug_info() -> dict:
    return {"ok": True}

registry.freeze()
SandboxServer(registry=registry).serve(port=9000)
```

`GET /commands` 列出 `hello`，不列出 `_debug_info`。`POST /commands/hello` 带 `{"name": "Ada"}` 返回 `{"result": "Hello, Ada!"}`。`POST /commands/_debug_info` 带 `{}` 仍然会执行。名字默认取函数名。参数类型来自注解：`int` → `integer`，`float` → `float`，`bool` → `boolean`，其他 → `string`。没有默认值的参数是 `required: true` 且 `default: null`。除非传入显式的 `CommandArg` 列表作为 `args`，否则每个参数的 `description` 保持 `""`。`hidden=True` 使命令不出现在 `GET /commands` 中。抛出异常即返回 `500`。在 `serve` 之前调用 `registry.freeze()`（`serve` 会再冻结一次）。

### `@table.route`

```python
from easy_sandbox.server import CapabilityGroup, ServerResponse, default_table

table = default_table()

@table.route("GET", "/hello/{name}", group=CapabilityGroup.COMMANDS)
def hello_route(request: object) -> ServerResponse:
    name = getattr(request, "path_params", {}).get("name", "World")
    return ServerResponse.ok({"greeting": f"Hello, {name}!"})
```

分发器只调用 `GET`、`POST` 和 `DELETE`。处理函数收到的请求具有：

| 属性 | 内容 |
|------|------|
| `method` | `GET`、`POST` 或 `DELETE` |
| `path` | 去掉末尾斜杠后的路径 |
| `query` | 查询字符串解析成的 `{name: [values]}` |
| `headers` | 头名称 → 单个值 |
| `body` | 解析后的 JSON 对象；该方法没有正文时为 `{}` |
| `path_params` | 从 `{param}` 段提取的 `{param: value}`（一段路径，不含斜杠） |
| `context` | `registry` 和 `route_table` |

返回 `ServerResponse.ok({...})`（`200`，该对象就是正文）或 `ServerResponse.error(status, message)`（`{"error", "type"}`，`type` 默认 `ValueError`）。

`auth_required=False` 使该路由在设置了 `EBX_SERVER_TOKEN` 时仍然开放。默认要求令牌。`streaming=True` 时返回 `SSEResponse(event_iterator=...)`；迭代器产出字符串 `event: <name>\ndata: <json>\n\n`。

该路由不会出现在 `GET /commands` 里。它出现在 `GET /capabilities` 的 `endpoints` 中，键是路由 `name`（默认 `"GET /hello/{name}"`）。只有它所属的组处于启用状态时才会被提供。组被关闭时，与内置路由一样返回 `404`。

---

## curl

设置基址；服务器以令牌启动时再设置令牌。这两个值都不应该写进模板镜像。

```bash
export EBX_TEMPLATE_URL="http://127.0.0.1:9000"   # 或 get_url(9000) 得到的 https 地址
export EBX_SERVER_TOKEN=""                         # 本地模式留空
```

健康检查（设置了令牌时仍然开放）：

```bash
curl -sS "$EBX_TEMPLATE_URL/health"
```

列出命令（只要设置了 `EBX_SERVER_TOKEN` 就带上头）：

```bash
curl -sS -H "X-Access-Token: $EBX_SERVER_TOKEN" "$EBX_TEMPLATE_URL/commands"
```

运行注册名为 `hello` 的命令：

```bash
curl -sS -H "X-Access-Token: $EBX_SERVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Ada"}' \
  "$EBX_TEMPLATE_URL/commands/hello"
```

上传和下载。路径必须留在 `EBX_SERVER_BASE_DIR` 之下（默认 `/home/user`）。`file_ops` 必须启用；除非 `commands.py` 或 `EBX_SERVER_DISABLED_GROUPS` 把它关掉，否则默认是开的。

```bash
B64=$(printf 'hello' | base64)
curl -sS -H "X-Access-Token: $EBX_SERVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"path\":\"/home/user/note.txt\",\"content_base64\":\"$B64\"}" \
  "$EBX_TEMPLATE_URL/upload"

curl -sS -H "X-Access-Token: $EBX_SERVER_TOKEN" \
  "$EBX_TEMPLATE_URL/download?path=/home/user/note.txt"
```
