# Easy Sandbox — 设计文档索引

> **版本**：v2.0 | **最后更新**：2026-09-24
>
> 本文档是 Easy Sandbox 所有设计文档的入口和索引。详细设计位于 [`design/`](design/) 目录下的各专题文档中。

---

## 项目概述

**Easy Sandbox**（PyPI 包名 `easy-sandbox`）是面向阿里云 FC Agent 沙箱服务的 Python SDK。**兼容 E2B 协议**，并扩展了阿里云生态能力（OSS、VPC、自定义域名）。

本仓库包含 Python SDK，以两个版本同步发布的 PyPI 分发包提供——`easy-sandbox`（`client-sdk/`，导入 `easy_sandbox`）与 `easy-sandbox-server`（`server-sdk/`，导入 `easy_sandbox.server`，容器侧运行时）。`ebx` CLI 是 `cli` 仓库中的 Node.js/TypeScript 项目，CLI 自己的设计与指南文档也在该仓库（见[相关：ebx CLI](#相关ebx-cli)）。

### 核心设计原则

1. **E2B 协议兼容** — L2 协议层兼容 E2B 数据面协议；提供迁移辅助层 (`from easy_sandbox.compat import Sandbox`) 方便现有 E2B 用户迁移
2. **AI-First** — 自然语言创建沙箱、MCP Server 是一等公民、内置 Agent 工具
3. **零配置默认** — 开箱即用；从安装到第一个沙箱运行不超过 3 行代码

### 快速上手

```bash
pip install easy-sandbox
export SANDBOX_API_KEY=your-api-key
```

```python
from easy_sandbox import Sandbox

async with await Sandbox.create(template="base") as sb:
    result = await sb.run_code("print('Hello, Easy Sandbox!')")
    print(result.text)
```

---

## 架构概览

SDK 采用严格分层架构 — 低层绝不导入高层：

```mermaid
graph TB
    subgraph Upper["上层"]
        Agent["Agent/MCP — MCP 服务器、内置 Agent、工具定义"]
        Decl["Declarative — @sandbox 装饰器"]
        Compat["Compat — E2B 兼容层"]
        Ext["Extensions — OSS、VPC、域名"]
    end
    subgraph Core["核心层"]
        L3["API — Sandbox、文件、代码、命令、网络、镜像"]
        L2["Protocol — 沙箱生命周期、文件系统、进程、终端、端口"]
        L1["Transport — HTTP、WebSocket、认证、编解码、流式传输"]
        L0["Models + Utils — Pydantic 模型、错误、配置、异步桥接"]
    end

    Agent --> L3
    Decl --> L3
    Compat --> L3
    Ext --> L3
    L3 --> L2 --> L1 --> L0
```

完整架构分解详见[架构设计](design/architecture.md)。

---

## 设计专题索引

每个专题都有独立的设计文档，包含完整规范。

### 核心设计

| 专题 | 文档 | 摘要 |
|------|------|------|
| **系统架构** | [architecture.md](design/architecture.md) | 六层架构、层间依赖、双 API 层（Platform API vs Sandbox envd API） |
| **SDK API 设计** | [sdk-api-design.md](design/sdk-api-design.md) | Sandbox 类、文件操作、代码执行、命令、网络、镜像构建器、会话管理 |
| **沙箱类型体系** | [sandbox-types.md](design/sandbox-types.md) | 临时沙箱（已实现）、持久沙箱（远期）、沙箱生命周期 |
| **提供方与凭证** | [providers-and-credentials.md](design/providers-and-credentials.md) | 每个配置键一个环境变量、优先级、提供方插件（`ebx provider ...`）、安装与信任模型、EPP/1 协议、E8xxx 错误；评审记录见 [providers-and-credentials-review.md](design/providers-and-credentials-review.md) |

### 模板

| 专题 | 文档 | 摘要 |
|------|------|------|
| **模板体系** | [template-system.md](design/template-system.md) | 模板分层、GitHub tarball 分发、`template.yaml` 规范、自定义命令、版本管理、模板市场架构 |

### AI 与 Agent 集成

| 专题 | 文档 | 摘要 |
|------|------|------|
| **MCP Server** | [mcp-server.md](design/mcp-server.md) | 7 个 P0 工具、STDIO 与 Streamable HTTP 传输、FC 部署产物、会话绑定 |
| **内置 Agent** | [built-in-agents.md](design/built-in-agents.md) | 沙箱侧 `AgentModule`（`commands.run()` 语法糖）；Agent 随专用模板分发，基础镜像不预装任何 Agent CLI（CLI 侧指南见 `cli` 仓库的 [自带 Agent（BYO）集成](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/guide/byo-agent-integration.md)） |

### 服务器与基础设施

| 专题 | 文档 | 摘要 |
|------|------|------|
| **Server API** | [server-api.md](design/server-api.md) | Sandbox Server SDK 路由、能力组、Browser 实例架构 |

### 维护者设计文档（仅英文）

provider、capability、server-v2 与 agents-API 工作流的设计文档。它们没有中文对应版本。

| 专题 | 文档 | 摘要 |
|------|------|------|
| **Agents API** | [agents-api.md](../en/design/agents-api.md)、[评审](../en/design/agents-api-review.md) | 在 Easy Sandbox 中托管编码 Agent；CLI 后续工作的规格见 [agents-api-cli-followups.md](../en/design/agents-api-cli-followups.md) |
| **细粒度 capability** | [fine-grained-capabilities.md](design/fine-grained-capabilities.md)、[评审](design/fine-grained-capabilities-review.md) | `easy-sandbox-server` 与 `template.yaml` 中的 capability 范围与权限 |
| **客户端 / 服务端对齐** | [client-server-alignment.md](design/client-server-alignment.md) | 每条服务端路由与客户端的差距矩阵 |
| **基础镜像与 Server SDK** | [base-image-and-server-sdk.md](design/base-image-and-server-sdk.md)、[CLI 跟进项](design/cli-followups.md) | 官方 FC Agent 沙箱基础镜像与 Server SDK；对 `ebx` CLI 的确切修改规格 |
| **Server SDK v2** | [server-sdk-v2/](../en/design/server-sdk-v2/README.md) | Server SDK 的操作模型设计与实施计划 |
| **OpenSandbox provider 调研** | [provider-opensandbox-mapping.md](../en/design/provider-opensandbox-mapping.md) | OpenSandbox provider 的 API 映射、配置键与测试计划 |
| **仓库布局** | [repository-layout.md](../en/design/repository-layout.md) | `python-sdk` 与 `cli` 仓库的布局评审 |

---

## 实现状态

| 功能 | 状态 | 备注 |
|------|------|------|
| SDK 核心（Sandbox、文件、命令、代码） | **已实现** | |
| MCP Server（STDIO） | **已实现** | 7 个 P0 工具 |
| MCP Server（Streamable HTTP） | **已实现** | `mcp_http.py` |
| FC 部署产物应用 | **已实现** | `easy_sandbox.agent.mcp_http:asgi_app`；产物由 CLI 的 `ebx mcp deploy` 生成。见 [mcp-server.md](design/mcp-server.md#7-fc-部署) |
| 模板 build/push/create 流水线 | **已实现** | 通过官方 CreateTemplate API |
| E2B 兼容层 | **已实现** | `easy_sandbox.compat` |
| 每个配置键一个环境变量（SDK） | **已实现** | 见[配置参考](reference/configuration.md)；CLI 规格见 `cli/docs/zh/design/providers-and-credentials-cli.md` |
| 提供方插件（SDK，`python -m easy_sandbox.providers`） | **已实现** | 见[提供方](guide/providers.md)；CLI 的 `ebx provider` 待实现 |
| 持久沙箱 | **远期** | 需底层平台支持 |
| SandboxPool（预热池） | **远期** | 需底层平台支持 |
| NAS 挂载 / SLS 日志集成 | **远期** | 规划中的扩展模块 |

---

## 相关资源

| 资源 | 位置 |
|------|------|
| 架构决策记录 (ADR) | [`.agents/notes/`](../../.agents/notes/README.md) |
| 用户指南 | [`docs/zh/guide/`](guide/) |
| API 参考 | [`docs/zh/reference/`](reference/) |
| English design index | [`docs/en/DESIGN.md`](../en/DESIGN.md) |

## 相关：ebx CLI

`ebx` CLI（Node.js / TypeScript，npm 包 `@easy-sandbox/cli`）的文档位于 [`cli` 仓库](https://github.com/Easy-Sandbox/easy-sandbox)，其设计索引是 [DESIGN.md](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/DESIGN.md)。与 SDK 读者最相关的是：[CLI 架构](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/architecture.md)、[CLI 命令体系](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/cli-design.md)与[模板目录](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/templates-catalog.md)。
