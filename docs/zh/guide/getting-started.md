# 快速入门

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

这是 **Client SDK**：在你的机器上安装、创建并使用沙箱。要写进镜像、在沙箱里启动的服务见 [Server SDK](server-sdk.md)。

本教程覆盖从安装到销毁的完整生命周期。

---

## 前置条件

- Python 3.10 或更高版本
- 默认提供方是 `alicloud-express`。API Key 从[智能体沙箱产品文档](https://help.aliyun.com/zh/functioncompute/product-overview-of-fc-agent-sandbox)获取。变量名是 `E2B_API_KEY`。标准 SDK 读取 `E2B_API_KEY`、`E2B_API_URL`、`E2B_DOMAIN`。
- 网络可访问阿里云杭州区域（默认 `cn-hangzhou`）

## 1. 安装

```bash
# 安装 SDK
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/3aa5e5ae6bd9c843f62c6689e549437f460b382d.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/3aa5e5ae6bd9c843f62c6689e549437f460b382d.tar.gz#subdirectory=client-sdk"

# 安装全部额外依赖（推荐）
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/3aa5e5ae6bd9c843f62c6689e549437f460b382d.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/3aa5e5ae6bd9c843f62c6689e549437f460b382d.tar.gz#subdirectory=client-sdk"
```

不要执行 `pip install agent-sandbox`。PyPI 上的 `agent-sandbox` 是另一个无关项目。

`abx` CLI 不属于 Python 包（没有 `[cli]` extra），它是独立的 Node.js 项目，见[相关：abx CLI](#相关abx-cli)。容器侧运行时（`agent_sandbox.server`）是独立的
`agent-sandbox-server` 包（[配套源码安装指南](install-python.md)）；`agent-sandbox-client` 依赖它，安装客户端时会一并安装。

### 从源码检出目录开发

在仓库根目录激活虚拟环境后，安装两个本地分发包及开发工具：

```bash
uv pip install -e ./server-sdk -e "./client-sdk[dev]"
```

根目录的 uv workspace 会将客户端的运行时依赖解析为 `server-sdk/`，无需
`--no-sources` 临时绕过。普通 `pip install` 也接受相同的 editable 参数；
发布包仍保留服务端同版本的精确依赖。

## 2. 配置 API Key

有三种方式配置认证凭证。真正生效时按下面的优先级（从高到低）。完整的凭证表见 [配置参考 — 凭证解析](../reference/configuration.md#凭证解析)。

### 方式一：代码参数（只影响这一次调用）

```python
from agent_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.create(sandbox_api_key="your-api-key-here")
```

### 方式二：环境变量（推荐用于 CI/CD）

```bash
export E2B_API_KEY="your-api-key-here"
```

### 选项 3：持久化文件（`~/.abx/.env`）

环境变量和项目 `.env` 都没写这个键时，才用这里保存的值。该文件由 `abx` CLI 写入（`abx config set sandbox_api_key your-api-key`，权限 600；见[相关：abx CLI](#相关abx-cli)），也可以手工编辑：`E2B_API_KEY=your-api-key`。

## 3. 创建第一个 Sandbox

### 使用 SDK（异步）

```python
import asyncio
from agent_sandbox.api.sandbox import Sandbox

async def main():
    # 创建沙箱（默认模板: base，超时: 300 秒）
    sandbox = await Sandbox.create(template="base", timeout=300)
    print(f"Sandbox 已创建: {sandbox.id}")
    print(f"状态: {sandbox.status.value}")

asyncio.run(main())
```

`base` 是默认模板（`Sandbox.create()` 不传 template 时就是它）。仓库 README 使用 `python-base`，因为那张镜像注册了 README 里的 `hello` 命令。

### 使用 SDK（同步）

```python
from agent_sandbox.api.sandbox import Sandbox

sandbox = Sandbox.create_sync(template="base")
print(f"Sandbox ID: {sandbox.id}")
```

## 4. 执行代码

### SDK

```python
result = await sandbox.run_code("print('Hello, Agent Sandbox!')")
print(result.text)     # "Hello, Agent Sandbox!"
print(result.stdout)   # "Hello, Agent Sandbox!\n"
print(result.exit_code)  # 0
```

## 5. 运行 Shell 命令

### SDK

```python
result = await sandbox.commands.run("ls -la /home/user")
print(result.stdout)
print(f"退出码: {result.exit_code}")
```

在 Express 的 `ProviderSandbox` 上，`commands.run`、`start` 和 `stream`
接受 `user="root"` 或其他已存在的操作系统账号。从 0.3.1a2 开始，原生 envd
适配器会为当前请求选择该账号：

```python
result = await sandbox.commands.run("id -u", user="root")
assert result.exit_code == 0 and result.stdout.strip() == "0"
```

省略 `user` 或传入 `""` 会保留提供方默认账号；显式选择不会影响后续或并发请求。
账号不存在时抛出 envd 错误，不会悄悄改用默认账号。账号名不允许冒号、NUL 或换行。
这个参数选择进程的操作系统身份，不是应用服务 token，也不增加提供方权限。
早期原生客户端（包括 0.3.1a1 和历史固定源码方案）会忽略该参数；标准
`AsyncSandbox` 入口此前已支持它。

## 6. 文件操作

### 上传文件到沙箱

```python
# 写入文本文件
await sandbox.files.write("/home/user/hello.py", "print('hello world')")

# 上传本地文件
await sandbox.files.upload("./local_script.py", "/home/user/script.py")
```

### 从沙箱下载文件

```python
# 读取文本
content = await sandbox.files.read("/home/user/hello.py")
print(content)

# 下载到本地
await sandbox.files.download("/home/user/output.csv", "./output.csv")
```

## 7. 列出目录内容

```python
files = await sandbox.files.list("/home/user")
for f in files:
    print(f"{f.name} ({f.type.value}, {f.size} bytes)")
```

## 8. 销毁 Sandbox

### SDK

```python
await sandbox.kill()
```

### 使用 Context Manager（推荐）

```python
async with await Sandbox.create(template="base") as sandbox:
    result = await sandbox.run_code("print('auto cleanup')")
    print(result.text)
# 退出 with 块后自动销毁
```

## 9. 完整示例

```python
import asyncio
from agent_sandbox.api.sandbox import Sandbox

async def main():
    async with await Sandbox.create(template="base") as sandbox:
        # 安装依赖
        await sandbox.commands.run("pip install requests")

        # 执行代码
        result = await sandbox.run_code("""
import requests
resp = requests.get('https://httpbin.org/get')
print(resp.status_code)
""")
        print(f"状态码: {result.text}")

        # 写入和读取文件
        await sandbox.files.write("/home/user/note.txt", "Hello!")
        content = await sandbox.files.read("/home/user/note.txt")
        print(f"文件内容: {content}")

asyncio.run(main())
```

---

沙箱服务端也可以托管编程代理 CLI。目前支持 Codex（`codex`，npm 包 `@openai/codex`）和 Qwen Code（`qwen`，npm 包 `@qwen-code/qwen-code`）。路径是 `/v1/agents/sessions`，需要 `ABX_SERVER_ENABLED_GROUPS` 包含 `agents`。见[托管代理](hosted-agents.md)。

## 下一步

- [认证详解](authentication.md) — 多种认证方式与配置优先级
- [SDK 使用指南](sdk-usage.md) — 完整的 API 使用方法
- [错误码参考](../reference/error-codes.md) — 错误排查
- [故障排查](troubleshooting.md) — 常见问题与解决方案

---

## 相关：abx CLI

上述步骤对应的命令行用法（用 npm 或独立二进制安装 `abx`、`abx config set`、`abx create`、`abx exec`、`abx upload` / `download`、`abx kill`）见 CLI 仓库：[快速开始（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/getting-started.md)、[二进制安装](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/binary-installation.md)、[CLI 教程](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/cli-tutorial.md)与[模板使用](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md)。
