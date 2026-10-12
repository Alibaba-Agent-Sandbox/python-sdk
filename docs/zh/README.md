# Easy Sandbox SDK — 文档中心

Easy Sandbox 是基于阿里云函数计算的云端沙箱 SDK，提供 E2B 兼容 API、Modal 风格装饰器和内置 AI Agent 三种使用范式。

> **范围：** 本仓库记录 Python SDK（`easy-sandbox`）与容器侧运行时（`easy-sandbox-server`）。`ebx` CLI 是独立的 Node.js 项目，拥有自己的文档集；见[相关：ebx CLI](#相关ebx-cli)。

---

## 设计文档

| # | 文档 | 说明 |
|---|------|------|
| 1 | [系统架构设计](design/architecture.md) | 六层分层架构总览、各层职责、目录结构 |
| 2 | [SDK API 设计](design/sdk-api-design.md) | **核心文档** — 三种使用范式、自然语言创建、完整 API 定义 |
| 3 | [沙箱类型体系](design/sandbox-types.md) | 临时/持久/休眠三种模式、生命周期状态机、计费模型 |
| 4 | [MCP Server](design/mcp-server.md) | 7 个 P0 工具定义、会话绑定、STDIO 与 Streamable HTTP 传输、IDE 配置 |
| 5 | [模板体系](design/template-system.md) | 官方模板、自定义模板、sandbox.yaml 规范、版本管理、模板市场 |
| 6 | [内置 Agent](design/built-in-agents.md) | Agent 模块（`commands.run()` 语法糖）与按 Agent 划分的专用模板（BYO） |
| 7 | [Server API](design/server-api.md) | 容器内 HTTP Server 端点定义、42 端点、8 个能力组 |
| 8 | [Provider 与凭证](design/providers-and-credentials.md) | 规范配置名、provider 插件、EPP/1 |

仅有英文的维护者文档（agents API、细粒度 capability、客户端/服务端对齐、基础镜像、server SDK v2、OpenSandbox 调研、仓库布局）在 [DESIGN.md](DESIGN.md) 中索引。

## 用户文档

### [`guide/`](guide/) — 使用教程与 How-to 指南

| 文档 | 说明 |
|------|------|
| [快速开始](guide/getting-started.md) | 安装、配置、第一个沙箱 |
| [最佳实践](guide/best-practices.md) | 服务器不携带提供者、按需打开能力组、agents 默认关闭、密钥不回显 |
| [文件与命令控制](guide/file-and-command-controls.md) | 模板如何限制路径和命令 |
| [托管代理](guide/hosted-agents.md) | 本地 Agents API 上的 Codex 与 Qwen Code |
| [认证配置](guide/authentication.md) | API Key / AK-SK 双认证模式 |
| [SDK 使用](guide/sdk-usage.md) | Python SDK 完整用法，含 Agent 工作流模式 |
| [模板编写](guide/authoring-templates.md) | `template.yaml`、能力声明、自定义命令、Dockerfile |
| [模板服务器 HTTP API](guide/template-server-api.md) | 模板 `commands.py` 里的服务器实际提供的路由 |
| [构建与部署](guide/build-and-deploy.md) | `Sandbox.deploy`、链式 `Image` API、Docker 构建流程 |
| [声明式用法](guide/declarative-usage.md) | `@sandbox` 装饰器 |
| [MCP 集成](guide/mcp-integration.md) | Python MCP server、IDE 配置、Streamable HTTP、FC 产物 |
| [会话持久化](guide/session-persistence.md) | 本地 / OSS 会话存储 |
| [E2B 迁移](guide/migrate-from-e2b.md) | 从 E2B 迁移指南 |
| [提供方](guide/providers.md) | 选择沙箱提供方、安装提供方插件、编写自己的提供方 |
| [环境变量](guide/environment-variables.md) | 沙箱环境变量作用域、注入方式与直接执行语义 |
| [故障排查](guide/troubleshooting.md) | 常见问题与解决方案 |
| [测试与完成定义](guide/testing-e2e.md) | 真实云 E2E 套件(`make e2e`)与完成定义 |
| [从 0.2.x 迁移](guide/migrating-from-0.2.md) | 升级到 0.3.0：客户端/服务端拆分、`easy-sandbox-server`、原地升级修复 |
| [对比](guide/comparison.md) | Easy Sandbox 与 E2B、Modal、Docker Sandbox 的对比 |

### [`reference/`](reference/) — API / 配置参考

| 文档 | 说明 |
|------|------|
| [API 参考](reference/api-reference.md) | SDK 公开 API 完整文档 |
| [配置参考](reference/configuration.md) | 环境变量、配置文件、凭证解析 |
| [错误码](reference/error-codes.md) | E1xxx–E8xxx 错误码索引 |
| [template.yaml 规范](reference/template-yaml-spec.md) | 模板定义格式（`template.yaml` 契约） |
| [Server HTTP API](reference/server-http-api.md) | 沙箱内 Server HTTP API 参考 |

### [`explanation/`](explanation/) — 概念解释与架构综述

| 文档 | 说明 |
|------|------|
| [架构综述](explanation/architecture-overview.md) | 六层分层架构概念解释 |
| [E2B 兼容性](explanation/e2b-compatibility.md) | 协议兼容原理与差异 |
| [沙箱生命周期](explanation/sandbox-lifecycle.md) | 创建→运行→休眠→销毁 |

## 项目规划

| 文档 | 说明 |
|------|------|
| [完整设计文档](DESIGN.md) | 设计专题索引与实现状态 |

---

## 快速导航

### 按角色

- **SDK 用户**：[最佳实践](guide/best-practices.md) → [SDK 使用](guide/sdk-usage.md) → [API 参考](reference/api-reference.md)
- **AI Agent 开发者**：[托管代理](guide/hosted-agents.md) → [文件与命令控制](guide/file-and-command-controls.md) → [MCP 集成](guide/mcp-integration.md)
- **架构师**：[系统架构](design/architecture.md) → [Server API](design/server-api.md)

### 按功能

- **自然语言创建沙箱**：[SDK API](design/sdk-api-design.md#核心设计理念自然语言优先)
- **MCP 集成（Cursor/Claude）**：[MCP 集成](guide/mcp-integration.md#配置-ide) | [MCP Server](design/mcp-server.md#5-安装方式与-cli)

### 其他资源

- **模板真源（awesome-templates）**：[Easy-Sandbox/awesome-templates](https://github.com/Easy-Sandbox/awesome-templates) — 官方与社区模板内容、索引（`awesome-templates.yaml`）与发布的唯一真源
- **English Documentation**：[English docs](../en/README.md)

## 相关：ebx CLI

`ebx` CLI（npm 包 `@easy-sandbox/cli`）的文档位于 [`cli` 仓库](https://github.com/Easy-Sandbox/easy-sandbox)：[文档中心](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/README.md)、[快速开始](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/guide/getting-started.md)、[CLI 参考](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/reference/cli-reference.md)、[CLI 架构](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/architecture.md)、[CLI 命令体系](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/cli-design.md)、[模板目录](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/design/templates-catalog.md)、[部署与构建](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)、[自带 Agent（BYO）集成](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/guide/byo-agent-integration.md)、[Agent Skill 安装与分发](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/guide/agent-skill-installation.md)。
