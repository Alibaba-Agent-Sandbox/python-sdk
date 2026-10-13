# Easy Sandbox SDK — 文档中心

Easy Sandbox 是基于阿里云函数计算的云端沙箱 SDK，提供 E2B 兼容 API、Modal 风格装饰器和内置 AI Agent 三种使用范式。

> **CLI 文档：** 下文标注 *（`cli` 仓库）* 的页面（CLI 设计、教程、参考、模板、部署、Skill 等）位于 `cli` 仓库，该仓库包含 Node.js 实现的 `ebx` CLI。本仓库记录 Python SDK（`easy-sandbox`）与容器侧运行时（`easy-sandbox-server`）。

---

## 设计文档

| # | 文档 | 说明 |
|---|------|------|
| 1 | [系统架构设计](design/architecture.md) | 六层分层架构总览、各层职责、目录结构 |
| 2 | [SDK API 设计](design/sdk-api-design.md) | **核心文档** — 三种使用范式、自然语言创建、完整 API 定义 |
| 3 | [CLI 命令体系](../../../cli/docs/zh/design/cli-design.md) *（`cli` 仓库）* | 命令树、自然语言创建、项目直接部署、AI Friendly 原则 |
| 4 | [沙箱类型体系](design/sandbox-types.md) | 临时/持久/休眠三种模式、生命周期状态机、计费模型 |
| 5 | [MCP Server](design/mcp-server.md) | 7 个 P0 工具定义、会话绑定、STDIO 与 Streamable HTTP 传输、IDE 配置 |
| 6 | [模板体系](design/template-system.md) | 官方模板、自定义模板、sandbox.yaml 规范、模板市场 |
| 7 | [内置 Agent](design/built-in-agents.md) | Agent 模块（`commands.run()` 语法糖）与按 Agent 划分的专用模板（BYO） |
| 8 | [Server API](design/server-api.md) | 容器内 HTTP Server 端点定义、42 端点、8 个能力组 |
| 9 | [模板目录](../../../cli/docs/zh/design/templates-catalog.md) *（`cli` 仓库）* | 官方模板集合形态契约、发布流程、离线校验 |

## 用户文档

### [`guide/`](guide/) — 使用教程与 How-to 指南

| 文档 | 说明 |
|------|------|
| [Agents API](guide/agents-api.md) | Codex 与 Qwen Code 的 HTTP 会话。不是内置 Agent。CLI 按需安装。含完整案例 |
| [快速开始](guide/getting-started.md) | 安装、配置、第一个沙箱 |
| [云上端到端练习](guide/cloud-examples.md) | 在默认提供方上跑 quickstart 与 compat-demos。Agents API 案例见专页 |
| [认证配置](guide/authentication.md) | API Key / AK-SK 双认证模式 |
| [SDK 使用](guide/sdk-usage.md) | Python SDK 完整用法 |
| [CLI 教程](../../../cli/docs/zh/guide/cli-tutorial.md) *（`cli` 仓库）* | 命令行快速上手 |
| [模板使用](../../../cli/docs/zh/guide/using-templates.md) *（`cli` 仓库）* | 官方与社区模板使用 |
| [模板编写](guide/authoring-templates.md) | 自定义模板；已有项目用 `ebx template init --adopt` |
| [部署与构建](../../../cli/docs/zh/guide/deploy-and-build.md) *（`cli` 仓库）* | 模板生命周期（`template init` / `--adopt` → `deploy` → `create`） |
| [声明式用法](guide/declarative-usage.md) | `@sandbox` 装饰器 |
| [MCP 集成](guide/mcp-integration.md) | Cursor / Claude Desktop 集成 |
| [会话持久化](guide/session-persistence.md) | 本地 / OSS 会话存储 |
| [E2B 迁移](guide/migrate-from-e2b.md) | 从 E2B 迁移指南 |
| [提供方](guide/providers.md) | 选择沙箱提供方、安装提供方插件（`ebx provider ...`）、编写自己的提供方 |
| [环境变量](guide/environment-variables.md) | 沙箱环境变量作用域、注入方式与直接执行语义 |
| [故障排查](guide/troubleshooting.md) | 常见问题与解决方案 |
| [测试与完成定义](guide/testing-e2e.md) | 真实云 E2E 套件(`make e2e`)与完成定义 |
| [从 0.2.x 迁移](guide/migrating-from-0.2.md) | 升级到 0.3.0：客户端/服务端拆分、`easy-sandbox-server`、原地升级修复 |
| [端到端模板工作流](../../../cli/docs/zh/guide/e2e-template-workflow.md) *（`cli` 仓库）* | 从零构建模板到沙箱使用完整指南 |
| [Agent Skill 安装与分发](../../../cli/docs/zh/guide/agent-skill-installation.md) *（`cli` 仓库）* | 把静态 SKILL.md 指南安装到 Qoder / Claude Code / Cursor / Qwen Code / Codex |
| [自带 Agent（BYO）集成](../../../cli/docs/zh/guide/byo-agent-integration.md) *（`cli` 仓库）* | 在沙箱内运行自带 Agent CLI：职责边界、custom_commands 契约、凭证白名单、版本锁定与许可边界 |

### [`reference/`](reference/) — CLI / API / 配置参考

| 文档 | 说明 |
|------|------|
| [API 参考](reference/api-reference.md) | SDK 公开 API 完整文档 |
| [CLI 参考](../../../cli/docs/zh/reference/cli-reference.md) *（`cli` 仓库）* | 所有 CLI 命令速查 |
| [配置参考](reference/configuration.md) | 环境变量、配置文件、优先级 |
| [错误码](reference/error-codes.md) | E1xxx–E8xxx 错误码索引 |
| [template.yaml 规范](reference/template-yaml-spec.md) | 模板定义格式 |

### [`explanation/`](explanation/) — 概念解释与架构综述

| 文档 | 说明 |
|------|------|
| [架构综述](explanation/architecture-overview.md) | 六层分层架构概念解释 |
| [E2B 兼容性](explanation/e2b-compatibility.md) | 协议兼容原理与差异 |
| [沙箱生命周期](explanation/sandbox-lifecycle.md) | 创建→运行→休眠→销毁 |

## 项目规划

| 文档 | 说明 |
|------|------|
| [完整设计文档](DESIGN.md) | 所有设计决策汇总 |

---

## 快速导航

### 按角色

- **SDK 用户**：[SDK API 设计](design/sdk-api-design.md) → [沙箱类型](design/sandbox-types.md) → [模板体系](design/template-system.md)
- **CLI 用户**：[CLI 命令体系](../../../cli/docs/zh/design/cli-design.md) *（`cli` 仓库）* → [模板体系](design/template-system.md) → [MCP 集成](guide/mcp-integration.md)
- **AI Agent 开发者**：[内置 Agent](design/built-in-agents.md) → [自带 Agent（BYO）集成](../../../cli/docs/zh/guide/byo-agent-integration.md) *（`cli` 仓库）* → [MCP Server](design/mcp-server.md)
- **架构师**：[系统架构](design/architecture.md) → [Server API](design/server-api.md)

### 按功能

- **自然语言创建沙箱**：[SDK API](design/sdk-api-design.md#核心设计理念自然语言优先) | [CLI](../../../cli/docs/zh/design/cli-design.md#3-自然语言创建) *（`cli` 仓库）* | [InferAgent](design/built-in-agents.md#2-配置推断-agentinferagent)
- **项目直接部署**：[CLI 部署命令](../../../cli/docs/zh/design/cli-design.md#sbox-deploy) *（`cli` 仓库）*（`ebx deploy` 为固定的 build+push+创建模板流水线；模板由 `ebx template init` 编写，可用脚手架、一句描述或 `--adopt`）
- **MCP 集成（Cursor/Claude）**：[MCP Server](design/mcp-server.md#5-安装方式)

### 其他资源

- **模板真源（awesome-templates）**：[Easy-Sandbox/awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) — 官方与社区模板内容、索引（`awesome-templates.yaml`）与发布的唯一真源，通过 `ebx template search` / `ebx template install` 使用
- **English Documentation**：[English docs](../en/README.md)
