# 沙箱环境变量指南

本指南描述异步 `ProviderSandbox` 扩展；根级 `Sandbox` 和 `AsyncSandbox` 遵循固定版本的标准迁移契约，详见[从 E2B 迁移](migrate-from-e2b.md)。

当前 SDK 安装使用[安装指南](install-python.md)。

> **说明：** 本页出现的 `abx` 命令由 `agent-sandbox` 仓库中的 CLI 提供（[CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

本指南区分创建时的环境输入、单次进程覆盖和已启动应用的环境。示例使用异步 `ProviderSandbox`；首个完整示例之后的代码片段假定处于异步函数中，并持有仍存活的 `sandbox`。

## 变量在哪里生效

| 输入 | 生效范围 |
|------|----------|
| `ProviderSandbox.create(envs=...)` | 由所选提供方和运行时处理的创建输入。普通变量可以传给后续进程，但运行时可能仍采用平台的 `PATH`。 |
| `sandbox.commands.run(..., env=...)` | 该次进程及其子进程，不修改其他已运行进程。 |
| 应用的 `POST /env` | 已运行应用的 `os.environ` 及其后续创建的子进程，不修改父进程或兄弟进程。 |

应用可以是经由 envd 启动的子进程。每个进程持有自己的环境，后续修改不会改写已有父进程或兄弟进程。SDK 没有全局 `sandbox.set_env()` 接口。进程需要特定 `PATH` 时，显式使用单次调用的 `env`，不要假设创建时一定能覆盖平台默认值。

---

## 创建与单次进程环境

### 创建时注入

通过创建参数 `envs` 传入普通应用变量。

**SDK：**

```python
import asyncio
from agent_sandbox import ProviderSandbox

async def main():
    sandbox = await ProviderSandbox.create(
        template="base", envs={"APP_ENV": "staging"}, timeout=300,
    )
    try:
        result = await sandbox.commands.run("printenv APP_ENV")
        print(result.stdout.strip())
    finally:
        await sandbox.kill()  # 本函数拥有该实例。

asyncio.run(main())
```

默认 Express CLI 路径中，`abx create base --env KEY=value` 设置的是新交互终端的环境，不是实例生命周期内的创建环境接口；使用 `--detach` 时也没有终端可配置。上面的创建环境输入使用 `ProviderSandbox.create(envs=...)`。应用模板应声明运行环境默认值，并在 `abx template launch` 前配置所需值。详见 [CLI 指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/cli-tutorial.md)。

连接不属于自己的实例时，用 `await sandbox.close()` 释放本地连接，不要删除该实例。

**`@sandbox` 装饰器：**

```python
from agent_sandbox import sandbox as sandboxed

@sandboxed(template="base", envs={"APP_ENV": "staging"})
def my_task():
    import os
    return os.environ["APP_ENV"]
```

### 按调用覆盖

每次执行调用可传入额外的环境变量，**仅对该次调用生效**：

```python
# commands.run — 使用 `env=`（单数，dict）
result = await sandbox.commands.run(
    "printenv MY_VAR",
    env={"MY_VAR": "hello"},
)

# run_code — 使用 `envs=`（复数，dict）
result = await sandbox.run_code(
    "import os; print(os.environ['MY_VAR'])",
    envs={"MY_VAR": "hello"},
)
```

`run_code()` 是真实的解释器接口，本模式要求所选提供方声明 `code.execute`；普通 Express `base` 实例不代表支持该接口。解释器环境行为由对应提供方负责，不能统一归为 envd 进程环境。

> **注意参数命名差异：** `commands.run()` 使用 `env=`（单数）；`run_code()` 使用 `envs=`（复数）。这沿用 E2B 的命名约定。

---

## 直接执行语义

通过 envd 发送的命令默认以 **直接 `exec`** 方式执行。但 `commands.run()`、`commands.stream()` 和 `commands.start()` 会**自动检测未加引号的 shell 运算符**（`|`、`;`、`&&`、`||`、`>`、`<`、`(...)`、`$(...)`）并透明地将命令包裹在 `sh -c` 中。

### 自动 Shell 运算符包裹

管道、重定向、分号和逻辑运算符现在**无需**手动使用 `sh -c` 即可工作：

```python
# ✅ 可用 — 管道被自动检测并包裹
result = await sandbox.commands.run("ls /tmp | grep log")

# ✅ 可用 — 重定向被自动检测并包裹
result = await sandbox.commands.run("echo hello > /tmp/hello.txt")

# ✅ 可用 — && 被自动检测并包裹
result = await sandbox.commands.run("cd /app && python main.py")

# ✅ 可用 — 分号被自动检测并包裹
result = await sandbox.commands.run("mkdir -p /tmp/out; cp file.txt /tmp/out/")
```

### 变量展开仍需手动包裹

Shell 变量展开（`$VAR`、`${VAR}`）**不会**被自动检测，因为 `$` 不是 shell 运算符字符。需要显式使用 `sh -c`：

```python
# ❌ 错误 — $HOME 作为字面字符串传递（不会触发自动包裹）
result = await sandbox.commands.run("echo $HOME")
# stdout: "$HOME"（字面值）

# ✅ 正确 — 使用 sh -c 进行变量展开
result = await sandbox.commands.run("sh -c 'echo $HOME'")
# stdout: 所选进程用户的主目录

# ✅ 正确 — 使用 printenv 读取单个变量
result = await sandbox.commands.run("printenv HOME")
# stdout: 所选进程用户的主目录
```

### 通配符展开仍需手动包裹

```python
# ❌ 错误 — * 作为字面字符传递（不会触发自动包裹）
result = await sandbox.commands.run("ls *.py")

# ✅ 正确
result = await sandbox.commands.run("sh -c 'ls *.py'")
```

### 经验法则

**自动包裹**（无需手动使用 `sh -c`）：
- 管道（`|`）
- 重定向（`>`、`>>`、`<`）
- 逻辑运算符（`&&`、`||`）
- 命令分隔符（`;`）
- 子 shell（`(...)`）
- 命令替换（`$(...)`）

**仍需显式使用 `sh -c '...'`**：
- 变量展开（`$VAR`、`${VAR}`）
- 反引号替换（`` `cmd` ``）
- 通配符（`*`、`?`、`[...]`）

如果只需**读取**单个环境变量的值，推荐使用 `printenv VAR`——更简单且避免 shell 引号问题。

---

## Server 作用域 — `GET/POST /env`

当沙箱内运行了 `SandboxServer`（通常监听端口 9000）时，`/env` 端点管理的是 **Server 进程的** `os.environ`：

### 读取与设置变量

应用策略需要启用环境端点，并允许当前身份访问。通过显式令牌绑定应用；提供方网关访问凭据与应用令牌是不同的凭据。

```python
import os

async with await sandbox.application_client(
    9000, token=os.environ["ABX_SERVER_TOKEN"]
) as application:
    print(await application.system.env(["APP_ENV"]))
    print(await application.system.set_env({"FEATURE_FLAG_X": "enabled"}))
    print(await application.system.env(["FEATURE_FLAG_X"]))
```

这些现有方法调用 `GET /env` 和 `POST /env`，保留提供方 URL 前缀、签名查询参数与认证。直接调用 HTTP 时可以使用 `application.auth_headers()`；`network.get_url()` 和 `get_access_headers()` 都是真实提供方接口，但只有网关头不代表已经提供应用令牌。详见[应用绑定指南](template-workflows.md)。

修改影响应用进程及其后续子进程，不会修改 envd 或兄弟进程。已经在启动时读取并缓存的配置（包括模型配置）不会因为 `POST /env` 自动重新初始化。

### 受保护变量

Server 拒绝覆写以下变量：

- 系统变量：`PATH`、`HOME`、`USER`、`SHELL`
- SDK 内部变量：任何以 `ABX_` 开头的变量（包括 `ABX_SERVER_TOKEN`）

---

## 推荐模式

### 模式 1：创建时注入（最常用）

适用于需要在整个沙箱生命周期内可用的变量：

```python
async with await ProviderSandbox.create(
    template="base",
    envs={"DATABASE_URL": db_url, "APP_ENV": "production"},
) as sandbox:
    result = await sandbox.commands.run("printenv APP_ENV")
```

### 模式 2：按调用传 env Dict（局部覆盖）

适用于每次调用不同的变量：

```python
env = {"BATCH_ID": "batch-001", "DRY_RUN": "true"}

result = await sandbox.commands.run("sh -c 'python process.py'", env=env)
```

### 模式 3：复用 env Dict 对象

维护一个共享 dict 并传给每次调用：

```python
shared_env = {"DATABASE_URL": db_url, "LOG_LEVEL": "DEBUG"}

await sandbox.commands.run("sh -c 'python migrate.py'", env=shared_env)
await sandbox.commands.run("sh -c 'python seed.py'", env=shared_env)
await sandbox.run_code("import os; print(os.environ['LOG_LEVEL'])", envs=shared_env)
```

### 模式 4：应用进程配置

运行中的应用按上文使用带认证的应用绑定。只在启动时读取的配置应在启动应用前设置。

---

## 客户端配置变量不是沙箱变量

在**你的机器上**配置 SDK 和 CLI 的变量（`ABX_SANDBOX_API_KEY`、`ABX_PROVIDER`、`ALIBABA_CLOUD_REGION_ID` 等）由客户端读取，不会自动复制进沙箱。要让某个值在沙箱内可见，请通过对应的创建或单次进程接口显式传入。每项客户端设置只有一个变量。名字和优先级见[配置参考](../reference/configuration.md#环境变量)。

由此有两点：

- 在 Server 内部，所有以 `ABX_` 开头的名字都受保护（见上文）。不要把 `ABX_*` 用作你自己的沙箱变量。
- [`exec` 提供方插件](providers.md) 使用允许列表中的环境变量，以及显式声明的 `env_passthrough` 名称；解析后的配置通过现有 `initialize` 请求传入。`node` 提供方使用 CLI 本机引擎，SDK 随请求传递解析后的选项。

---

## 安全注意事项

1. **envs 中的密钥**：通过 `envs=` 在创建时传入的环境变量会传输到平台 API。确保传输使用 HTTPS（默认值）。避免在日志中输出包含密钥的 env dict。

2. **`GET /env` 脱敏**：Server 的 `GET /env` 端点自动隐藏名称中包含 `TOKEN`、`SECRET`、`KEY`、`PASSWORD` 或 `CREDENTIAL` 的变量。

3. **受保护的 Server 变量**：`POST /env` 禁止写入 `PATH`、`HOME`、`USER`、`SHELL` 及所有 `ABX_*` 变量，防止意外破坏。

4. **进程继承**：`POST /env` 不会改写父进程或兄弟进程的环境；不要把普通进程边界当成安全隔离保证。

5. **推荐 `printenv`** 而非 `echo $VAR`：由于 envd 使用直接执行，`echo $VAR` 会输出字面字符串 `$VAR`。请使用 `printenv VAR` 或 `sh -c 'echo $VAR'`。

---

## 速查表

| 方法 | 参数 | 作用域 | 生命周期 |
|------|------|--------|---------|
| `ProviderSandbox.create(envs=)` | `envs` | 实例创建输入 | 沙箱生命周期 |
| `commands.run(env=)` | `env` | envd | 单次命令 |
| `run_code(envs=)` | `envs` | 支持该操作的提供方解释器 | 单次执行 |
| `@sandbox(envs=)` | `envs` | 提供方创建输入 | 装饰器管理的沙箱 |
| `POST /env` | `vars` | Server | Server 进程生命周期 |

---

## 参见

- [SDK 使用指南](sdk-usage.md) — `commands.run()` 与 `run_code()` 用法
- [声明式用法](declarative-usage.md) — `@sandbox(envs=)` 装饰器
- [CLI 教程](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/cli-tutorial.md) — CLI 终端环境
- [配置参考](../reference/configuration.md) — SDK/CLI 环境变量（每个键一个名字）
- [提供方](providers.md) — 选择和安装沙箱提供方
