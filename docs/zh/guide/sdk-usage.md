# SDK 使用指南

本页介绍异步 **ProviderSandbox** 的 Provider/服务端扩展。仅修改导入迁移 E2B 时，使用根目录 `Sandbox` / `AsyncSandbox` 或 `agent_sandbox.code_interpreter`，见[从 E2B 迁移](migrate-from-e2b.md)。这些入口的同步/异步调用及结果模型遵循固定标准契约。
本文详述 Agent Sandbox Python SDK 的完整使用方法。

---

## 安装

请按[安装指南](install-python.md)安装。公开客户端/服务端 alpha 版本为 0.3.1a5；安装客户端会安装匹配的服务端依赖。宿主机安装不会更新已有沙箱镜像。

不要执行 `pip install agent-sandbox`。PyPI 上的 `agent-sandbox` 是另一个无关项目。

## 导入

```python
from agent_sandbox import ProviderSandbox as Sandbox
```

---

## 当前应用连接

下面的模板作者示例保留其明确部署前提。连接 CLI 返回的已有实例时，优先通过 `await sandbox.application_client(9000, token=application_token, timeout=330)` 获取应用客户端，再调用 `client.commands.run(...)`；见[模板工作流](template-workflows.md)。它保留 Provider 网关头、URL 前缀与签名查询参数。`close()` 只释放连接，`kill()` 删除实例；不要销毁借用的实例。HTTP 等待超时不保证取消远端执行，也不会自动重试命令。

## 模板作者快速路径

2026-10-15 在阿里云 Express（`alicloud-express`）上验证。模板是 generation 2，启动命令运行 `agent-sandbox-server`。`Sandbox.create(template=..., provider="alicloud-express")` 使用 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和 `ABX_SANDBOX_DOMAIN`。`template` 可以是模板 id 或名称。

```python
import asyncio

from agent_sandbox import ProviderSandbox as Sandbox

TEMPLATE = "hello-x"  # generation-2 模板的名称或 id


async def main() -> None:
    async with await Sandbox.create(
        template=TEMPLATE, provider="alicloud-express", timeout=300
    ) as sb:
        assert await sb.run("hello", name="Bob") == "Hello, Bob!"
        echoed = await sb.commands.run("echo hi", on_stdout=lambda text: None)
        assert echoed.stdout == "hi\n" and echoed.exit_code == 0
        await sb.files.write("/home/user/note.txt", "abc")
        assert await sb.files.read("/home/user/note.txt") == "abc"
        url = sb.network.get_url(9000)
        headers = sb.network.get_access_headers()
        # 用 headers 对 {url}/health 发 GET。/health 返回 200。


asyncio.run(main())
```

`sandbox.run` 是调用命名命令的那一次调用，返回函数的值。`timeout=`（秒）是 HTTP 时限，不会传给函数。Shell 输出通过 `commands.run` 的 `on_stdout` / `on_stderr` 流式输出。命名命令不会把自己的 print 流出来；函数返回时调用才结束。

名字不存在抛 `CommandNotFoundError`，消息里带有服务端列出的命令。参数错误抛 `CommandArgumentError`。命令函数抛出的异常是 `CommandExecutionError`（`error_type` 是异常类名）。上下文管理器会调用 `kill()`。

部署：`abx template deploy . -y --generation 2 --start-cmd 'agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py' --ready-cmd 'agent-sandbox-server healthcheck --port 9000'`。完整步骤见 [Express 快速开始](express-quickstart.md)。

---

## 创建与销毁

### 异步创建

```python
sandbox = await Sandbox.create(
    template="base",      # 模板名称（默认 "base"）
    timeout=300,           # 超时秒数（1~86400，默认 300）
    envs={"KEY": "val"},   # 注入的环境变量
    metadata={"team": "x"},# 任意元数据键值对
    cpu=2,                 # CPU 核数（可选）
    memory=4096,           # 内存 MB（可选）
    disk=10240,            # 磁盘 MB（可选）
    gpu="A10",             # GPU 规格（可选）
)
```

### 同步创建

```python
sandbox = Sandbox.create_sync(template="base")
```

### Context Manager（推荐）

退出 `with` 块时自动调用 `kill()` 销毁沙箱：

```python
async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("python3 -c 'print(1+1)'")
    print(result.stdout)  # "2"
# 自动销毁
```

### 连接已有沙箱

```python
sandbox = await Sandbox.connect("sbx-xxxx")

# 同步版
sandbox = Sandbox.connect_sync("sbx-xxxx")
```

### 销毁沙箱

```python
# 实例方法
await sandbox.kill()

# 类方法（按 ID 销毁，不需要先连接）
await Sandbox.kill_by_id("sbx-xxxx")

# 同步版
Sandbox.kill_by_id_sync("sbx-xxxx")
```

### 列出沙箱

```python
sandboxes = await Sandbox.list(status=SandboxStatus.RUNNING, limit=20)
for sb in sandboxes:
    print(f"{sb.sandbox_id} - {sb.template} - {sb.status.value}")
```

---

## 执行代码 — run_code

Provider 解释器要求精确操作，如 `code.execute`、`code.default-context.execute`；详见[模板工作流](template-workflows.md#解释器操作)。极速版项目适配器未实现统一解释器，调用会返回 `E8004`，不会自动回退到执行脚本。`base` 上运行 Python 进程不代表支持持久代码上下文。

若需极速版原生解释器，请使用独立标准 `agent_sandbox.code_interpreter` 客户端和 `code-interpreter-v1`，按[迁移指南](migrate-from-e2b.md)选择同步或异步入口及返回模型。流式回调同样需要对应的实际操作，不能从缓存结果推断实时流支持。

---

## 执行命令 — commands

`sandbox.commands` 子模块提供 Shell 命令执行能力。

### 执行并等待

```python
result = await sandbox.commands.run(
    "ls -la /home/user",
    timeout=60,                # 超时秒数（默认 60）
    env={"MY_VAR": "value"},   # 本次命令的额外环境变量（envd 作用域）
    cwd="/app",                # 工作目录
)

print(result.stdout)
print(result.stderr)
print(result.exit_code)
print(result.execution_time)
print(result.success)  # exit_code == 0
```

`on_stdout` 和 `on_stderr` 在每个输出块到达时调用：

```python
result = await sandbox.commands.run(
    "echo hi",
    on_stdout=lambda text: print(text, end=""),
    on_stderr=lambda text: print(text, end=""),
)
```

### 流式输出

```python
async for chunk in sandbox.commands.stream("pip install flask"):
    if chunk.type.value == "stdout":
        print(chunk.data, end="")
    elif chunk.type.value == "stderr":
        print(chunk.data, end="", file=sys.stderr)
    elif chunk.type.value == "exit":
        print(f"\n退出码: {chunk.exit_code}")
```

### 后台执行

```python
reader = await sandbox.commands.start("python server.py")
# reader 是 StreamReader，可异步迭代消费输出
```

也可使用 `run` 的 `background=True` 参数：

```python
reader = await sandbox.commands.run("sleep 60", background=True)
```

### 进程管理

```python
# 列出进程
processes = await sandbox.commands.list()

# 终止进程
await sandbox.commands.kill(pid=12345)

# 发送信号：envd 只能投递 SIGTERM（15）和 SIGKILL（9），
# 其他数值（例如 2，即 SIGINT）会抛出 ValueError
await sandbox.commands.send_signal(pid=12345, signal=15)  # SIGTERM
await sandbox.commands.send_signal(pid=12345, signal=9)   # SIGKILL

# 发送 stdin 数据
await sandbox.commands.send_input(pid=12345, data="yes\n")
```

### 同步版

所有方法都有 `_sync` 后缀的同步版本：

```python
result = sandbox.commands.run_sync("echo hello")
```

---

## 文件操作 — files

`sandbox.files` 子模块提供文件系统操作。

### 读写

```python
# 写入文本或字节
await sandbox.files.write("/home/user/hello.txt", "Hello World")
await sandbox.files.write("/home/user/data.bin", b"\x00\x01\x02")

# 读取文本
text = await sandbox.files.read("/home/user/hello.txt", encoding="utf-8")

# 读取字节
data = await sandbox.files.read_bytes("/home/user/data.bin")
```

### 上传 / 下载

```python
# 上传本地文件到沙箱
await sandbox.files.upload("./local_file.py", "/home/user/remote.py")

# 下载沙箱文件到本地
await sandbox.files.download("/home/user/output.csv", "./output.csv")
```

### 目录操作

```python
# 列出目录内容
entries = await sandbox.files.list("/home/user")
for entry in entries:
    print(f"{entry.name} - {entry.type.value} - {entry.size}")

# 创建目录（含父目录）
await sandbox.files.make_dir("/home/user/new/nested/dir")

# 检查路径是否存在
exists = await sandbox.files.exists("/home/user/hello.txt")

# 获取文件信息
info = await sandbox.files.get_info("/home/user/hello.txt")
```

### 移动 / 删除

```python
# 移动/重命名
await sandbox.files.move("/home/user/old.txt", "/home/user/new.txt")

# 删除文件或目录
await sandbox.files.remove("/home/user/temp.txt")
```

### 监听文件变更

```python
watcher = await sandbox.files.watch("/home/user")
async for event in watcher:
    print(f"{event.type}: {event.path}")
```

---

## 网络 — network

`sandbox.network` 子模块用于计算端口访问 URL（纯本地计算，不涉及网络请求）。

> **能力要求**：需要 `ports` 能力。默认能力集不含 `ports`，需在模板的 `template.yaml` 中显式声明。

```python
# 获取端口 URL
url = sandbox.network.get_url(8080)
# => "https://8080-sbx-xxxx.cn-hangzhou.e2b.fc.aliyuncs.com"

# 获取 host
host = sandbox.network.get_host(8080)
# => "8080-sbx-xxxx.cn-hangzhou.e2b.fc.aliyuncs.com"

# secure 模式：给平台网关的 X-Access-Token（envd /files）。
# sandbox.run 和 sandbox.server 不会把这个头发到端口 9000。
headers = sandbox.network.get_access_headers()
```

---

## 沙箱生命周期

```python
# 检查是否运行中（发起 API 调用）
running = await sandbox.is_running()

# 刷新沙箱信息
info = await sandbox.refresh_info()

# 设置超时
await sandbox.set_timeout(600)

# 暂停/恢复
await sandbox.pause()
await sandbox.resume()
```

### 属性

```python
sandbox.id           # 沙箱 ID (str)
sandbox.status       # 当前状态 (SandboxStatus)
sandbox.url          # envd URL (str)
sandbox.info         # 完整信息 (SandboxInfo)
sandbox.capabilities # 能力集 (frozenset[str])
```

---

## 同步 vs 异步

SDK 采用 **async-first** 设计，所有核心方法都是异步的。每个异步方法都有对应的同步包装器（通过 `make_sync` 生成）：

| 异步方法 | 同步方法 |
|----------|----------|
| `Sandbox.create()` | `Sandbox.create_sync()` |
| `Sandbox.connect()` | `Sandbox.connect_sync()` |
| `sandbox.kill()` | `sandbox.kill_sync()` |
| `sandbox.run_code()` | `sandbox.run_code_sync()` |
| `sandbox.commands.run()` | `sandbox.commands.run_sync()` |
| `sandbox.files.read()` | `sandbox.files.read_sync()` |
| `sandbox.files.write()` | `sandbox.files.write_sync()` |

同步方法在后台运行事件循环，适用于脚本和非异步环境。

---

## 错误处理

所有 SDK 错误都继承自 `SandboxError`，携带 `code`、`message`、`suggestion` 属性：

```python
from agent_sandbox.models.errors import (
    SandboxError,
    InvalidAPIKeyError,       # E1001
    TemplateNotFoundError,    # E2001
    SandboxNotFoundError,     # E2009
    CapabilityNotSupportedError,  # E3004
    FileNotFoundError_,       # E4001
    ConnectionError_,         # E5001
)

try:
    sandbox = await Sandbox.create(template="nonexistent")
except TemplateNotFoundError as e:
    print(f"[{e.code}] {e.message}")
    print(f"建议: {e.suggestion}")
except SandboxError as e:
    print(f"SDK 错误: {e}")
```

详见 [错误码参考](../reference/error-codes.md)。

---

## 命名命令

命名命令只有一种机制：注册在沙箱 server 里的函数（`@sandbox.register`，或 server 的 `CommandRegistry`）。`sandbox.run(name, **kwargs)` 调用其中一个（`POST /commands/{name}`），`sandbox.list_commands()` 列出它们：

```python
commands = await sandbox.list_commands()
for cmd in commands:
    print(f"{cmd.name}: {cmd.description}")

result = await sandbox.run("dev", port=8080)   # 注册函数的返回值
```

名字不存在抛 `CommandNotFoundError`（消息包含服务端列出的可用命令）。参数错误抛 `CommandArgumentError`。命令函数抛出的异常是 `CommandExecutionError`（同时是 `ServerAPIError`）。调用可能超过 30 秒时传入 `timeout=`。沙箱镜像必须运行 `agent-sandbox-server`（见下文）。裸 shell 命令，包括流式 stdout，用 `sandbox.commands.run(cmd)`，它不经过注册表。

---

## 模板服务端 — server

自带 `agent-sandbox-server` 的模板会暴露第二条由模板作者定义的数据通道（端口 9000），`sandbox.server` 是它的类型化客户端。
当模板按端点策略限制了可访问范围，或你需要 envd 没有的端点（搜索、打包、文件监听、进程输出/标准输入、git、浏览器）时使用它。

```python
async with await Sandbox.create(template="my-server-template") as sandbox:
    server = sandbox.server                        # 或 sandbox.server_at(9000, token="...")
    caps = await server.discover()                 # 显式调用；启用快速失败的预检查
    if caps.can("files_download_stream"):
        data = await server.files.download("/home/user/out/report.csv")
    await server.files.upload("/home/user/in/data.json", b"{}")

    result = await server.process.shell("ls -la", cwd="/home/user")
    async for event in server.process.shell_stream("make test"):
        print(event.event, event.data)

    print(server.files.list_sync("/home/user"))    # 每个协程都有 *_sync 孪生方法
```

在运行中的沙箱里启动服务端（镜像中需要有 `agent-sandbox-server`）：

```python
server = await sandbox.start_server(policy="read-only", token="s3cret", commands="/home/user/app/commands.py")
```

### 限制端点（模板作者）

```python
from agent_sandbox.server import SandboxServer

policy = {
    "preset": "transfer-only",                      # 仅保留上传/下载端点，并限制大小
    "endpoints": {
        "files_download_stream": {"paths": {"allow": ["/home/user/out"], "deny": ["**/.env"]},
                                  "limits": {"max_bytes": "5MB"}},
        "files_upload_stream":   {"paths": {"allow": ["/home/user/in"]}, "params": {"overwrite": False}},
    },
}
SandboxServer(policy=policy).serve(9000)   # a dict or a ServerPolicy
```

也可以在 `template.yaml` 中声明（`server:` 块，见[模板规范](../reference/template-yaml-spec.md)），或使用
`agent-sandbox-server serve --policy server-policy.json`。用 `agent-sandbox-server check-config` 校验。

### 处理拒绝

```python
from agent_sandbox.models.errors import (
    EndpointNotAvailableError, FilePolicyDeniedError, PayloadTooLargeError, RateLimitedError, ServerAPIError,
)

try:
    await server.files.download("/etc/passwd")
except FilePolicyDeniedError as exc:            # 同时是 PermissionDeniedError
    print(exc.error_code, exc.endpoint)         # path_not_allowed files_download_stream
except EndpointNotAvailableError:               # 被策略禁用（或旧版服务端不认识）
    ...
except RateLimitedError as exc:
    await asyncio.sleep(exc.retry_after or 1)
except ServerAPIError as exc:                   # 基类：status_code、error_type、error_code、endpoint
    ...
```

服务端始终是权威：`discover()` 之后客户端只是免去一次往返，直接抛出相同的异常。策略变更后调用
`server.forget_discovery()` 并重新 `discover()`。

---

## 环境变量

环境变量可在创建时注入（`envs=`）或按调用传入（`env=`/`envs=`）。包含未加引号 shell 运算符（管道 `|`、分号 `;`、逻辑运算符 `&&`/`||`、重定向 `>`/`<`、子 shell `(...)`、命令替换 `$(...)`)的命令会被 `commands.run()`、`commands.stream()` 和 `commands.start()` **自动包裹**在 `sh -c` 中。变量展开（`$VAR`）、反引号替换（`` `cmd` ``）和通配符（`*`、`?`）仍需显式使用 `sh -c '...'` 包裹，读取单个变量可用 `printenv VAR`。

关于作用域（envd vs SandboxServer）、注入模式和安全注意事项的完整详情，请参阅[环境变量指南](environment-variables.md)。

---

## Agent 工作流模式

这是 AI Agent 场景的典型模式——创建沙箱执行任务代码，获取结果后销毁：

```python
import asyncio
from agent_sandbox import ProviderSandbox as Sandbox

async def agent_workflow(task_code: str) -> str:
    """Agent → 创建沙箱 → 执行代码 → 读取结果 → 销毁沙箱"""
    async with await Sandbox.create(template="my-app") as sandbox:
        # 写入任务代码
        await sandbox.files.write("/app/task.py", task_code)

        # 执行
        result = await sandbox.commands.run("python3 /app/task.py")

        # 读取输出
        if result.exit_code == 0:
            try:
                output = await sandbox.files.read("/app/output.txt")
                return output
            except Exception:
                return result.stdout
        else:
            return f"Error (exit {result.exit_code}): {result.stderr}"

# 使用
result = asyncio.run(agent_workflow("""
import json
data = {"status": "done", "items": [1, 2, 3]}
with open("/app/output.txt", "w") as f:
    json.dump(data, f)
print("Task completed")
"""))
print(result)
```

---
