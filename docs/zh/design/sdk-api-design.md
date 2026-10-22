> 标准公开 API 现在使用同步 Sandbox 与异步 AsyncSandbox。下文 Provider/Server 扩展及原生 `_sync` 包装器对应 ProviderSandbox，不定义标准客户端 API；`ABX_PROVIDER` 不切换标准客户端协议。见[迁移指南](../guide/migrate-from-e2b.md)。

# SDK API 设计

> `agent-sandbox-client` 包是**运行时**客户端：创建沙箱、使用沙箱、销毁沙箱。它提供两种写法（命令式和声明式）。模板的构建与部署归 `abx` CLI，运行 Agent 归 Agents API。

---

## 目录

1. [设计原则](#设计原则)
2. [范式一：命令式](#范式一命令式)
3. [范式二：声明式装饰器](#范式二声明式装饰器)
4. [三种叫「命令」的东西](#三种叫命令的东西)
5. [运行 Agent](#运行-agent)
6. [配置](#配置)
7. [Sandbox 核心 API](#sandbox-核心-api)
8. [错误](#错误)
9. [SDK 不提供的能力](#sdk-不提供的能力)

---

## 设计原则

- **只做运行时。** SDK 没有镜像构建器、Dockerfile 生成和镜像仓库推送。这条流水线由 `abx template build|deploy` 负责，所以构建路径只有一条，只需要写一份文档、测一遍。
- **命名命令只有一种调用方式。** 命名命令是注册在沙箱内 SandboxServer 上的函数。客户端用 `sandbox.run("name", **kwargs)` 调用，也就是 `POST /commands/name`。`template.yaml` 没有 `custom_commands` 键。
- **运行 Agent 只有一个入口。** SandboxServer 上的 Agents API（`/v1/agents/**`）。SDK 没有 `sb.agent.*` 辅助方法。
- **显式、带类型的接口。** 不用 `__getattr__` 分发；每个方法都有 mypy 检查的签名（`py.typed`）。
- **异步优先，同步孪生。** 每个协程都有 `_sync` 版本，由它替你管理事件循环。
- **明确标准与扩展契约。** 本文描述原生 ProviderSandbox 的协议、配置和错误模型。`agent_sandbox` 导出标准 `Sandbox`／`AsyncSandbox`；标准客户端及 `code_interpreter` 遵循固定的阿里云 E2B 契约。见[从 E2B 迁移](../guide/migrate-from-e2b.md)。

---

## 范式一：命令式

```python
from agent_sandbox import ProviderSandbox as Sandbox

sb = await Sandbox.create(template="code-interpreter")

result = await sb.run_code("print('Hello, AliCloud!')")
print(result.text)

result = await sb.commands.run("ls -la /app")
print(result.stdout)

await sb.files.write("/app/data.csv", "name,age\nAlice,30\nBob,25")
content = await sb.files.read("/app/data.csv")
files = await sb.files.list("/app")

await sb.kill()
```

同步模式：

```python
sb = Sandbox.create_sync(template="code-interpreter")
result = sb.run_code_sync("print(1+1)")
sb.kill_sync()
```

上下文管理器（退出时销毁沙箱）：

```python
async with await Sandbox.create(template="code-interpreter") as sb:
    result = await sb.run_code("import sys; print(sys.version)")
```

流式输出：

```python
async for chunk in sb.commands.stream("pip install pandas && python train.py"):
    if chunk.type == "stdout":
        print(chunk.data, end="")
    elif chunk.type == "stderr":
        print(f"[ERR] {chunk.data}", end="")
    elif chunk.type == "exit":
        print(f"\nExit code: {chunk.exit_code}")
```

---

## 范式二：声明式装饰器

灵感来自 Modal。装饰器把本地函数放到远程沙箱里运行。全部参数见[声明式用法](../guide/declarative-usage.md)。

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter-v1", packages=["pandas"])
def analyze(data):
    import pandas as pd
    return pd.DataFrame(data).describe().to_dict()

# 创建沙箱 -> 上传函数 -> 执行 -> 返回结果 -> 销毁沙箱
result = analyze({"col1": [1, 2, 3], "col2": [4, 5, 6]})
```

- `keep_alive=True` 在调用后保留沙箱；`sandbox_id="..."` 复用已有沙箱。
- 支持 `async def` 函数，因此可以用 `asyncio.gather` 并发多次调用。
- `@sandbox.register`（在沙箱内使用）把命名命令注册到 SandboxServer，见下一节。

---

## 三种叫「命令」的东西

| 是什么 | 调用 | 线协议 |
|--------|------|--------|
| 裸 shell 命令 | `sandbox.commands.run("ls -la")` | envd 进程 API |
| 命名命令 | `sandbox.run("name", x=1)` | SandboxServer 的 `POST /commands/name` |
| 命名命令目录 | `sandbox.list_commands()` | SandboxServer 的 `GET /commands` |

`sandbox.run()` 不会执行 shell 字符串。名称未注册时抛 `CommandNotFoundError`，其他 server 错误抛 `ServerAPIError`。没有 HTTP 数据面的 provider（`epp://`）抛 `ProviderFeatureNotSupportedError`（E8004）。

```python
sb = await Sandbox.create(template="python-hello")

for c in await sb.list_commands():      # list[ServerCommand]
    print(c.name, c.description, c.args)

value = await sb.run("hello", name="Alice")
```

命名命令注册在模板的 `commands.py` 里（或用 `@sandbox.register`）。见[编写模板](../guide/authoring-templates.md)和[模板 server API](../guide/template-server-api.md)。

**能力（capabilities）。** `template.yaml` 声明 `capabilities`（`shell`、`files`、`code`、`terminal`、`ports`），用于发现与文档。客户端只有 `code` 是运行时闸门：缺少 `code` 时 `run_code()` 抛 `CapabilityNotSupportedError`（E3004）。`sandbox.capabilities` 返回生效的集合。

---

## 运行 Agent

只有一个入口：Agents API，即沙箱内 server 上的 HTTP 会话 API（`/v1/agents/**`），驱动 Codex 和 Qwen Code。在模板镜像里安装 Agent CLI，然后调用该 API。指南和完整案例见 [Agents API](../guide/agents-api.md)。

---

## 配置

解析顺序，优先级从高到低：

```
代码参数 > 环境变量 > .env 文件 > ~/.abx/config.toml > 默认值
```

```bash
export ABX_SANDBOX_API_KEY=your-api-key        # 主凭证
export ALICLOUD_ACCESS_KEY_ID=your-ak          # 可选的 AK/SK
export ALICLOUD_ACCESS_KEY_SECRET=your-sk
```

单次调用的覆盖项是 `Sandbox.create()` 的关键字参数（`api_key`、`api_url`、`domain`、`access_key_id`、`access_key_secret`）。完整键列表见[配置参考](../reference/configuration.md)和[环境变量](../guide/environment-variables.md)。

---

## Sandbox 核心 API

完整签名见 [API 参考](../reference/api-reference.md)。整体结构：

| 分组 | 成员 |
|------|------|
| 生命周期 | `create`、`connect`、`list`、`kill`、`kill_by_id`、`set_timeout`、`is_running`、`pause`、`resume`、`refresh_info` |
| 属性 | `id`、`provider`、`status`、`url`、`info`、`capabilities` |
| 代码 | `run_code`（需要 `code` 能力） |
| 命令 | `commands.run` / `stream` / `start` / `list` / `kill`（裸 shell 与进程）、`run(name, **kwargs)`、`list_commands()` |
| 文件 | `files.read` / `read_bytes` / `write` / `list` / `remove` / `exists` / `make_dir` / `move` / `upload` / `download` / `watch` |
| 网络 | `network.get_host`、`network.get_url`、`network.get_access_headers`、`network.resolve` |
| 终端 | `get_terminal`（WebSocket 上的 PTY） |
| 沙箱内 server | `server`、`server_at(port)`、`start_server(...)` 返回带类型的 `ServerClient` |

返回值是 Pydantic 模型：`CodeResult`、`ProcessResult`、`ProcessChunk`、`FileInfo`、`SandboxInfo`。沙箱的 `metadata` 在 `sandbox.info` 上。

---

## 错误

所有异常都派生自 `SandboxError`，携带 `code`、`message`、`suggestion` 和 `docs_url`。

```python
from agent_sandbox import ProviderSandbox as Sandbox, SandboxError
from agent_sandbox.models.errors import TemplateNotFoundError, TimeoutError

try:
    sb = await Sandbox.create(template="code-interpreter")
    result = await sb.run_code("import time; time.sleep(100)", timeout=5)
except TemplateNotFoundError as e:
    print(f"[{e.code}] {e.message}")
except TimeoutError as e:
    print(f"[{e.code}] {e.message}")
except SandboxError as e:
    print(f"[{e.code}] {e.message}")
    print(f"修复建议: {e.suggestion}")
```

完整错误码见[错误码](../reference/error-codes.md)。

---

## SDK 不提供的能力

| 不提供 | 替代方案 |
|--------|----------|
| 模板构建、推送、部署（`Image`、`DockerBuilder`、`Sandbox.deploy`） | `abx template build` 与 `abx template deploy` |
| 自然语言创建沙箱、`Sandbox.plan()` | CLI 的 `abx create --prompt "DESCRIPTION"` 与 `abx template scaffold "DESCRIPTION"` |
| `sb.agent.*` 辅助方法、`Agent(...)` | [Agents API](../guide/agents-api.md) |
| `Sandbox.custom()`、`run_command()`、`template.yaml` 中的 `custom_commands` | `sandbox.run(name, **kwargs)` 调用 server 注册的命令 |
| `SandboxPool` | 不计划提供；按任务创建沙箱 |
| 单沙箱级的 VPC、OSS 挂载、自定义域名（`agent_sandbox.extensions`） | 平台没有对应的单沙箱 API：VPC 是模板的 `vpcConfig`，存储卷是控制面资源，自定义域名是账号级配置 |
