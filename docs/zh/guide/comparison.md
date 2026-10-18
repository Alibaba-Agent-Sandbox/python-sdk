# 与其他沙箱工具的对比

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（[CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

本文档客观对比 Agent Sandbox (abx) 与其他主流沙箱及远程执行平台：E2B、Modal、Docker Sandbox。

---

## 定位与场景

| 平台 | 核心定位 | 主要使用场景 |
|------|---------|-------------|
| **Agent Sandbox (abx)** | 可切换提供方的沙箱 SDK。默认提供方是阿里云极速版（FC）；还可以安装其他提供方 | AI Agent 代码执行、云端或本地开发环境、模板驱动沙箱 |
| **E2B** | 为 AI 应用构建的云沙箱 | AI Agent 工具调用、代码解释器、LLM 工作流中的数据分析 |
| **Modal** | 面向数据/ML 流水线的 Serverless 计算 | GPU 工作负载、批处理、模型推理、定时任务 |
| **Docker Sandbox** | 基于容器的本地/远程隔离 | 本地开发、CI/CD、可复现环境 |

---

## SDK 对比

| 维度 | Agent Sandbox | E2B | Modal |
|------|-------------|-----|-------|
| **语言** | Python | Python, JS/TS, Kotlin, Go | Python |
| **安装** | [配套源码安装指南](install-python.md) | `pip install e2b` | `pip install modal` |
| **沙箱创建** | `await Sandbox.create()`，或 Modal 风格的 `@sandbox` | `await Sandbox.create()` | `@app.function()` 装饰器 |
| **同步支持** | `Sandbox.create_sync()` | `Sandbox()`（同步类） | N/A（原生异步） |
| **命令执行** | `sandbox.commands.run()` | `sandbox.commands.run()` | 远程函数调用 |
| **文件操作** | `sandbox.files.read/write/list` | `sandbox.files.read/write/list` | `modal.Volume` 挂载 |
| **代码执行** | `sandbox.run_code()` | `sandbox.run_code()` | 远程函数执行 |
| **注册命令** | `sandbox.run(name, **kwargs)` | N/A | N/A |
| **网络访问** | `sandbox.network.get_host()` | `sandbox.get_host()` | 内置 URL 路由 |
| **终端 (PTY)** | `sandbox.get_terminal()` | `sandbox.terminal.start()` | `modal shell` |
| **E2B 迁移辅助** | `from agent_sandbox.compat import Sandbox`（部分对应） | 原生 | N/A |
| **认证方式** | 随提供方变化。默认提供方用 `ABX_SANDBOX_API_KEY`，阿里云极速版另用官方 AK/SK | API Key | Token |

### 代码示例

**Agent Sandbox：**

```python
from agent_sandbox.api.sandbox import Sandbox

async with await Sandbox.create(template="python-hello") as sb:
    result = await sb.run_code("print('hello')")
    print(result.text)
```

**E2B：**

```python
from e2b import Sandbox

sandbox = Sandbox()
result = sandbox.run_code("print('hello')")
print(result.text)
sandbox.kill()
```

**Modal：**

```python
import modal
app = modal.App("example")

@app.function()
def hello():
    print("hello")
```

### 使用风格对比

Agent Sandbox 同时支持 **命令式**（E2B 风格）和 **声明式**（Modal 风格）两种编程范式：

| 维度 | E2B 风格（命令式） | Modal 风格（声明式） |
|------|-------------------|---------------------|
| **创建** | 手动 `Sandbox.create()` | 自动（`@sandbox` 装饰器） |
| **依赖安装** | `sb.commands.run("pip install ...")` | 装饰器参数 `packages=[...]` |
| **数据传输** | `files.write()` + `files.read()` | 函数参数和返回值自动序列化 |
| **执行** | `sb.commands.run()` / `sb.run_code()` | 直接调用函数 |
| **结果获取** | 解析 stdout / 读取文件 | 函数返回值 |
| **生命周期** | 手动 `kill()` 或 `async with` | 自动管理 |
| **适用场景** | 细粒度控制、长时间交互、多步骤流程 | 简单计算任务、批处理、函数即服务 |

**E2B 风格（命令式）— 细粒度控制：**

```python
from agent_sandbox.api.sandbox import Sandbox

async with await Sandbox.create() as sb:
    await sb.commands.run("pip install pandas")
    await sb.files.write("/app/data.csv", csv_content)
    result = await sb.commands.run("python3 /app/analyze.py")
    report = await sb.files.read("/app/report.txt")
```

**Modal 风格（声明式）— 像调本地函数：**

```python
from agent_sandbox.declarative import sandbox

@sandbox(packages=["pandas"])
def analyze(data: list[dict]) -> dict:
    import pandas as pd
    df = pd.DataFrame(data)
    return {"mean": df["value"].mean(), "count": len(df)}

# 调用方式和本地函数一样，自动在远程沙箱中执行
result = analyze(my_data)
```

> 完整示例参见 [`examples/compat-demos/comparison.py`](../../../examples/compat-demos/comparison.py)

---

## CLI 对比

| 维度 | abx | e2b CLI | modal CLI |
|------|-----|---------|-----------|
| **安装** | [CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md) | `npm i -g @e2b/cli` | `pip install modal` |
| **运行时** | Node.js (TypeScript) | Node.js | Python (Typer) |
| **创建沙箱** | `abx create` | `e2b sandbox create` | N/A（代码驱动） |
| **列出沙箱** | `abx sandbox list` | `e2b sandbox list` | `modal container list` |
| **连接沙箱** | `abx connect <id>` | `e2b sandbox connect` | `modal shell` |
| **模板构建** | `abx template build` | `e2b template build` | N/A |
| **模板部署** | `abx template deploy` | `e2b template build --push` | N/A |
| **认证设置** | 通过环境变量（`.env`）| `e2b auth login` | `modal token set` |
| **MCP 集成** | `abx mcp install` | N/A | N/A |
| **密钥管理** | 通过环境变量（`.env`）| N/A | `modal secret create` |

---

## 基础设施

| 维度 | Agent Sandbox | E2B | Modal | Docker Sandbox |
|------|-------------|-----|-------|----------------|
| **隔离技术** | 取决于提供方。默认是阿里云 FC 容器；`local-process` 等插件不提供隔离 | Firecracker MicroVM | 容器（gVisor） | 容器（runc/containerd） |
| **启动时间** | 秒级 | ~150ms（MicroVM） | 秒级（冷启动）/ 毫秒级（热启动） | 秒级 |
| **部署区域** | 默认提供方是阿里云区域（cn-hangzhou 等）。其他提供方用自己的区域 | 美国、欧洲 | 美国（aws-us-east-1 等） | 自托管 |
| **平台类型** | 默认提供方是阿里云托管。插件可以是本机或其他云 | 托管（E2B Cloud） | 托管（Modal Cloud） | 自托管 / Docker Desktop |
| **GPU 支持** | 通过模板配置 | N/A | 原生（A10G, A100, H100） | 通过 NVIDIA Container Toolkit |
| **最大生命周期** | 可配置（最长 86400 秒） | 可配置 | 按调用计 | 无限制 |
| **计费** | 阿里云 FC 计费 | 按沙箱秒计费 | 按秒计费 | 基础设施成本 |

---

## Agent Sandbox 的独特能力

### E2B 风格的 API

Agent Sandbox 使用 E2B 风格的方法名，E2B 代码通常只需少量改动即可迁移。它不是 E2B 的直接替代品：配置、认证和部分行为都不同。

```python
# 迁移的起点：改导入，然后按指南逐项处理
from agent_sandbox.compat import Sandbox
```

完整迁移指南参见[从 E2B 迁移](migrate-from-e2b.md)。

### 阿里云集成

| 功能 | 说明 |
|------|------|
| **AK/SK 认证** | 原生阿里云 AccessKey 认证 |
| **模板构建与部署** | `abx template build` / `abx template deploy` 把镜像推送到阿里云容器镜像服务并注册模板 |

VPC、OSS 卷、自定义域名是平台侧设置（模板运行时配置和账号级资源），Python SDK 没有对应的 API。

### 注册命令

注册在沙箱 server 里的函数（`@sandbox.register`，由容器内 Server SDK 实现）通过一个 API 调用：

```python
result = await sandbox.run("analyze", data="input.csv")
```

此能力在 E2B 和 Modal 中不可用。

### MCP Server 集成

Agent Sandbox 内置 MCP (Model Context Protocol) Server，使 AI IDE（Cursor、Claude Desktop、VS Code）可以直接操作沙箱：

```bash
abx mcp install --target cursor
```

提供 7 个工具：`create_sandbox`、`run_code`、`run_command`、`read_file`、`write_file`、`list_files`、`kill_sandbox`。

### 声明式沙箱装饰器

```python
from agent_sandbox import sandbox

@sandbox(template="python-hello", timeout=60)
async def my_task():
    ...
```

---

## 其他平台（简要）

| 平台 | 说明 |
|------|------|
| **Daytona** | 云开发环境平台。2026 年转为闭源，此前提供开源自托管方案。 |
| **Google Gemini Sandbox** | Google Cloud Gemini Enterprise Agent Platform（原 Vertex AI）中的代码执行沙箱。托管服务，与 Google Cloud 生态紧密耦合。 |
| **Cloudflare Workers** | 使用 V8 Isolates 进行进程内隔离，亚毫秒级冷启动。侧重边缘计算，非通用沙箱。 |
| **Fly.io Machines** | 基于 Firecracker 的临时 VM，支持完整 Linux 环境和快速启动。API 驱动，无专用沙箱 SDK。 |

---

## 总结

| 考量因素 | 推荐平台 |
|---------|---------|
| 从 E2B 迁移到阿里云 | **Agent Sandbox**——E2B 风格的方法名，代码改动较少（不是直接替代） |
| AI Agent 代码执行需求 | **Agent Sandbox** 或 **E2B**——专为沙箱构建的 SDK |
| GPU 密集型 ML/推理工作负载 | **Modal**——原生 GPU 支持和 Serverless 弹性 |
| 本地开发隔离 | **Docker**——行业标准，自托管 |
| 阿里云生态集成 | **Agent Sandbox**——AK/SK 认证、模板构建并部署到 ACR |
| 基于 MCP 的 AI IDE 集成 | **Agent Sandbox**——内置 MCP Server |

---

## 延伸阅读

- [命令与 SDK 对照](command-map.md)
- [从 E2B 迁移](migrate-from-e2b.md)
- [SDK 使用指南](sdk-usage.md)
- [CLI 教程](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/cli-tutorial.md)
- [MCP 集成](mcp-integration.md)
- [认证详解](authentication.md)
