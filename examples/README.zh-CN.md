# Agent Sandbox — 使用示例

[English](README.md) | **中文**

示例按它们用的是哪一个包分开。

**Client SDK** 的脚本跑在你的机器上。它们创建沙箱，或调用一个已经起来的沙箱：`quickstart/`、`compat-demos/`、`agents/`、`scenarios/`，以及 `templates/python-hello/call_api.py`。

**Server SDK** 的代码跑在沙箱镜像里面。就是 `templates/python-hello/` 和 `templates/agents-cli/` 里的 `commands.py`。它们导入 `agent_sandbox.server` 并调用 `start(9000)`。它们不创建云上沙箱。

## 前置条件

### 1. 安装 SDK

```bash
# 完整安装（推荐，包含声明式装饰器、MCP 服务等）
pip install "agent-sandbox-client[all]"

# 或按需安装
pip install "agent-sandbox-client[declarative]"   # 仅 @sandbox 装饰器

# 从源码安装（在 python-sdk 仓库根目录执行）
pip install -e ./server-sdk -e ./client-sdk

# abx CLI 是独立的 Node.js 项目（`cli` 仓库）
npm install -g @agent-sandbox/cli
```

### 2. 配置凭证

```bash
# 方式一：环境变量
export E2B_API_KEY="your-api-key"

# 方式二：CLI 配置（持久化到 ~/.abx/config.toml；需安装 abx CLI）
abx config set sandbox_api_key your-api-key

# 如需运行 Codex Agent 示例，还需配置：
export OPENAI_API_KEY="your-openai-key-here"
```

> **环境变量：** envd 使用直接执行（direct exec）—— Shell 特性（`$VAR` 展开、管道、重定向）需要 `sh -c '...'`。用 `printenv VAR` 读取变量值。详见[环境变量指南（中文）](../docs/zh/guide/environment-variables.md) | [Environment Variables (EN)](../docs/en/guide/environment-variables.md)。

## Client SDK 示例

## 目录结构

```
examples/
├── quickstart/                # Client SDK — 创建并使用沙箱
├── agents/                    # Client SDK — 调用 Agents API 或云上沙箱
├── compat-demos/              # Client SDK — E2B 风格和 Modal 风格的调用
├── scenarios/                 # Client SDK — 本地创建、执行、读取、销毁
└── templates/                 # Server SDK — commands.py 在镜像里启动
    ├── python-hello/commands.py
    ├── python-hello/call_api.py   # Client SDK：对已经在听的服务发 HTTP
    └── agents-cli/commands.py
```

## Server SDK 示例

### templates/ —— Server SDK

[`python-hello/commands.py`](templates/python-hello/commands.py) 和 [`agents-cli/commands.py`](templates/agents-cli/commands.py) 随镜像启动。它们导入 `agent_sandbox.server`。

[`call_api.py`](templates/python-hello/call_api.py) 是 Client SDK。它调用一个已经在运行的模板服务器（`GET /health`、`GET /capabilities`、`GET /commands`、一次上传、一次 shell）。基址来自命令行参数或 `ABX_TEMPLATE_URL`，令牌来自 `ABX_SERVER_TOKEN`。请求和响应形状见[模板服务器 HTTP API](../docs/zh/guide/template-server-api.md)（[English](../docs/en/guide/template-server-api.md)）。

## 示例列表

### quickstart/ —— Client SDK

| 文件 | 说明 | 适用场景 |
|------|------|----------|
| [`01_hello.py`](quickstart/01_hello.py) | **基础沙箱操作** —— 创建、执行命令、生命周期管理 | SDK 入门 |
| [`02_file_ops.py`](quickstart/02_file_ops.py) | **文件操作** —— 读写文件、目录管理、二进制文件 | 数据交换 |
| [`03_web_service.py`](quickstart/03_web_service.py) | **Web 服务** —— 启动 Express 服务、获取公网 URL | Web 开发、API 测试 |
| [`04_data_analysis.py`](quickstart/04_data_analysis.py) | **数据分析** —— 上传 CSV、pandas 分析、run_code | 数据科学 |
| [`05_decorator_usage.py`](quickstart/05_decorator_usage.py) | **@sandbox 装饰器** —— 声明式远程执行 | 简化调用 |

### agents/ —— Client SDK

| 文件 | 说明 | 适用场景 |
|------|------|----------|
| [`codex_agent.py`](agents/codex_agent.py) | **Codex Agent** —— AI 代码生成与执行 | AI 编程 |
| [`browser_automation.py`](agents/browser_automation.py) | **浏览器自动化** —— Playwright 爬取与截图 | 网页爬取 |
| [`complete_case.py`](agents/complete_case.py) | **Agents API 完整案例** —— 本地服务，Codex 与 Qwen Code，不需要模型密钥 | Agents API |
| [`hosted_codex.py`](agents/hosted_codex.py) | **托管 Codex 客户端** —— 对着已经启动的服务开一个会话 | Agents API |
| [`hosted_qwen.py`](agents/hosted_qwen.py) | **托管 Qwen 客户端** —— 对着已经启动的服务开一个会话 | Agents API |
| [`local_files_and_session.py`](agents/local_files_and_session.py) | **文件加一个 Codex 会话** —— 本地服务，`PATH` 上名为 `codex` 的本地程序，无 API key | Agents API |

### compat-demos/ —— Client SDK演示

| 文件 | 说明 | 适用场景 |
|------|------|----------|
| [`e2b_data_analysis.py`](compat-demos/e2b_data_analysis.py) | **E2B 风格数据分析** | E2B 迁移 |
| [`e2b_web_scraper.py`](compat-demos/e2b_web_scraper.py) | **E2B 风格网页爬取** | E2B 迁移 |
| [`modal_compute.py`](compat-demos/modal_compute.py) | **Modal 风格科学计算** | Modal 迁移 |
| [`modal_data_analysis.py`](compat-demos/modal_data_analysis.py) | **Modal 风格数据分析** | Modal 迁移 |
| [`comparison.py`](compat-demos/comparison.py) | **E2B vs Modal 风格对比** | API 风格选型 |

## 运行示例

```bash
# 基础示例
python examples/quickstart/01_hello.py

# 数据分析
python examples/quickstart/04_data_analysis.py

# @sandbox 装饰器
python examples/quickstart/05_decorator_usage.py

# E2B 风格用法
python examples/compat-demos/e2b_data_analysis.py
```

## 核心 API 速览

### 执行方法

```python
from agent_sandbox import ProviderSandbox as Sandbox

async with await Sandbox.create(template="base", api_key="...") as sandbox:

    # 1. 裸 Shell —— sandbox.commands.run(cmd)
    proc = await sandbox.commands.run("echo hello")
    print(proc.stdout, proc.exit_code)

    # 2. 代码解释器 —— sandbox.run_code(code)
    code_result = await sandbox.run_code("print(1 + 1)")
    print(code_result.text)   # "2"

    # 3. 命名命令 —— sandbox.run(name, **kwargs)
    #    对模板 SandboxServer 发 POST /commands/hello
    value = await sandbox.run("hello", name="Alice")
    print(value)              # 命令返回值
```

> **说明：** `sandbox.run(name, **kwargs)` 调用注册在模板 server 里的命令，不会执行 shell 字符串。要执行 shell 请用 `sandbox.commands.run(cmd)`。

### 文件操作

```python
    # 写入和读取文件
    await sandbox.files.write("/app/data.txt", "内容")
    content = await sandbox.files.read("/app/data.txt")
```

### 网络

```python
    # 获取端口的公网 URL
    url = sandbox.network.get_url(3000)
```

### 声明式装饰器

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter", packages=["numpy"])
def compute(n: int) -> float:
    import numpy as np
    return float(np.random.random(n).mean())

result = compute(1000)  # 自动在远程沙箱中执行
```
