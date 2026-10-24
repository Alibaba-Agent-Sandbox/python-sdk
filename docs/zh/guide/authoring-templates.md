# 编写模板

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（[CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

这是 **Server SDK**：`commands.py` 随镜像启动，在沙箱里面提供 HTTP 服务。在你的机器上创建并调用沙箱见 [Client SDK](client-sdk.md)。

本文档介绍如何创建自定义 Agent Sandbox 模板，包括目录结构、字段参考、显式工作流、注册命令和发布流程。

模板是一个由纯文件组成的目录，可手写也可生成。`abx template scaffold` 命令有三种生成方式（内置脚手架、一句话描述、适配已有源码的项目）；该工作流记录在 CLI 仓库：[模板编写（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md)。

---

## 模板目录结构

一个完整的模板目录结构如下：

```text
my-template/
├── template.yaml      # 必须 — 模板定义
├── Dockerfile         # 可选 — 自定义 Docker 构建（优先于 template.yaml 中的构建步骤）
├── commands.py        # 可选 — 用 @command 注册命名命令
└── README.md          # 可选 — 模板说明
```

`template.yaml` 是唯一必需的文件。

---

## template.yaml 基础示例

```yaml
name: my-python-template
version: "1.0.1"
description: "Scaffold for a new Agent Sandbox template. Not a catalog entry."
author: "alibaba-agent-sandbox"
license: Apache-2.0
spec_version: 4
base: "fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>"
generation: 2
start_cmd: "agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py"
ready_cmd: "agent-sandbox-server healthcheck --port 9000"

resources:
  cpu: 2
  memory: 2048

ports:
  - 9000

tags:
  - example
  - skeleton

priority: P2
wave: other


env:
  ABX_SERVER_TOKEN: ""

smoke:
  - command: hello
    args:
      name: Express
    expect: "Hello, Express!"
workflow_contract_version: 1
provides:
  app:
    protocol: agent-sandbox-server
    version: 2
    port: 9000
    operations:
    - commands.list
    - commands.run
default_workflow: application
workflows:
  application:
    kind: application
    input: source
    service: app
    startup: exec
    binding:
      transport: http
      endpoint: provider-port
      caller: host
      authentication: service-token
    operation: commands.run
    required_operations: []
```

---

## 字段参考

| 字段 | 类型 | 必须 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | ✅ | — | 模板名称 |
| `version` | `str` | ❌ | `"1.0.0"` | 语义版本号 |
| `description` | `str` | ❌ | `""` | 模板描述 |
| `env` | `dict[str, str]` | ❌ | `{}` | 环境变量 |
| `cpu_count` | `int` | ❌ | `None` | 默认 CPU 核数 |
| `memory_mb` | `int` | ❌ | `None` | 默认内存 MB |
| `ports` | `list[int]` | ❌ | `[]` | 暴露的端口列表 |
| `author` | `str` | ❌ | `""` | 作者 |
| `license` | `str` | ❌ | `""` | 许可证 |
| `spec_version` / `workflow_contract_version` | 整数 | ✅ | — | `4` / `1` |
| `provides` / `workflows` / `default_workflow` | 映射 / 标识符 | ✅ | — | 显式工作流契约 |
| `tags` | `list[str]` | ❌ | `[]` | 标签 |

详细的字段定义参见 [template.yaml 规范](../reference/template-yaml-spec.md)。

---

<a id="能力声明"></a>
## 模板工作流

模板的 `provides` 描述软件服务，`workflows` 描述显式调用路径。默认工作流只指向一条声明，不推导其他能力。旧 `capabilities`、`tested_on` 和 Provider 兼容表均拒绝；未知远端引用不授予默认解释器。应用 HTTP 不依赖统一代码解释器。精确操作、T/F/U、上下文及验收范围见[显式模板工作流](template-workflows.md)。

服务端 HTTP 端点策略独立控制九个能力组；`core` 始终开启，`dev_tools`、`browser`、`agents` 默认关闭。`server:` 不是 Provider 操作授权，工作流也不自动打开服务端策略。详见[模板服务器 HTTP API](template-server-api.md)。

---

## 注册命令

命名命令只有一种机制：注册在模板 server 里的函数。`template.yaml` 没有 `custom_commands` 键（客户端会拒绝它）。在 `commands.py` 中用装饰器注册 Python 函数：

```python
from agent_sandbox.server import command, start

@command("demo", description="回显参数。")
def demo(x: int, y: str) -> str:
    return f"{y}={x}"

if __name__ == "__main__":
    start(9000)
```

文件上传和下载是 server 的端点（`/files/*`、`/upload`、`/download`），属于默认开启的 `file_ops` 组，不在 `commands.py` 里注册。部署不会应用 `server:` 块。可选组用 `default_table().enable_group(CapabilityGroup.DEV_TOOLS)`（参数是 `CapabilityGroup`，不是字符串）或 `ABX_SERVER_ENABLED_GROUPS` 打开。`dev_tools`、`browser`、`agents` 默认关闭。

注册的命令由沙箱内 HTTP server 提供（`POST /commands/{name}`）。客户端用 `await sandbox.run("demo", x=1, y="hello")` 或 `abx run <id> demo --arg x=1 --arg y=hello` 调用，用 `sandbox.list_commands()` 或 `abx sandbox command list <id>` 列出。裸 shell 命令是另一个调用：`sandbox.commands.run(cmd)`。

---

## Dockerfile 自定义

目录里有 `Dockerfile` 时，镜像就是这个文件。`template.yaml` 不安装软件包。`base` 是合法来源元数据，但不会替换 Dockerfile 的 `FROM`；已移除的清单软件包安装字段被拒绝，依赖安装写入有效 Dockerfile 及原生依赖文件。

源 Dockerfile 保持原样。含未解析基础镜像占位符时，应修正源输入或显式选择构建配置；不能按 Provider 静默换成另一张镜像。`base` 字段合法，但不替换 Dockerfile 的 `FROM`。

## 提供者模板配置

服务端不选择 Provider。9000 是应用 HTTP 默认监听端口；平台注入的 envd、解释器及保留端口属于各后端，不能据此推导应用服务不可用。`startup: exec`、`entrypoint`、`none` 是不同路径，必须和 Provider 声明一致；不要让原生入口与启动命令重复运行。非空 `ready_cmd` 必须实际检查。构建配置必须明确选择，其有效 Dockerfile 和构建参数进入输入身份。

`commands.py` 只导入 `agent_sandbox.server`，在主入口调用 `start(port)`；镜像显式安装 server SDK。
已发布 0.3.1a1 alpha 中的 Provider 原生应用 API 使用 `from agent_sandbox import ProviderSandbox`，
再通过 `await ProviderSandbox.connect(ID)` 连接。这个实例支持
`async with await sandbox.application_client(9000, token=application_token)`；标准
`Sandbox`/`AsyncSandbox` 是另一套接口。应用端点解析保留代理前缀，并隔离网关和应用凭据。
完整连接与关闭示例见[如何访问沙箱](template-server-api.md#如何访问沙箱)，最终删除由沙箱创建者负责。

---

## 发布与部署模板

Python SDK 是运行时客户端，不构建也不部署模板。构建、推送并注册模板用 CLI：`abx template build` 和 `abx template deploy`（或 `abx deploy`）。见[构建与部署](build-and-deploy.md)。

将模板发布到 GitHub、从本地或 registry 安装模板、适配已有项目（`abx template scaffold --adopt`），或通过命令行构建并注册模板（`abx deploy`、`abx template deploy|create`），请使用 `abx` CLI；见[相关：abx CLI](#相关abx-cli)。

## 下一步

- [使用模板](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md) — 安装和使用模板
- [template.yaml 规范](../reference/template-yaml-spec.md) — 所有字段精确定义
- [声明式用法](declarative-usage.md) — @sandbox 装饰器

---

## 相关：abx CLI

模板的命令行工作流记录在 CLI 仓库：[模板编写（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md)（`abx template scaffold`、`--adopt`、发布、`template install`）、[部署与构建](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)（`abx deploy`、`abx template deploy|create`）和[模板使用](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/using-templates.md)。
