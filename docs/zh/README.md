# Agent Sandbox SDK — 文档中心

Agent Sandbox 是可切换提供方的沙箱 SDK。默认提供方是阿里云极速版（函数计算）。同一套 API 还有 Modal 风格的 `@sandbox` 装饰器，以及沙箱内的 Agents API（Codex 与 Qwen Code，按需安装 CLI）。

> **范围：** 本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。`abx` CLI 是独立的 Node.js 项目，拥有自己的文档集；见[相关：abx CLI](#相关abx-cli)。

## 网站

| 网站 | 地址 |
|---|---|
| 官网 | https://www.agent-sandbox.cn |
| 提供方注册站 | https://registry.agent-sandbox.cn |

安装器拉取的目录索引是 `https://registry.agent-sandbox.cn/providers/index.json`。`ABX_PROVIDER_REGISTRY` 可以改这个地址。

---

## 两部分

| | Client SDK | Server SDK |
|---|---|---|
| 跑在哪里 | 你的机器 | 沙箱镜像里面 |
| 做什么 | 创建沙箱并使用它 | 构建沙箱里一直听着的 HTTP 服务 |
| 包 | `agent-sandbox-client` | `agent-sandbox-server` |
| 导入 | `agent_sandbox` | `agent_sandbox.server` |
| 入口 | [Client SDK](guide/client-sdk.md) | [Server SDK](guide/server-sdk.md) |

## 用户文档

### Client SDK — 使用沙箱

| 文档 | 说明 |
|------|------|
| [Client SDK](guide/client-sdk.md) | 这一侧是什么，以及下面这些文档怎么串起来 |
| [快速开始](guide/getting-started.md) | 安装、配置、第一个沙箱 |
| [Express 快速开始](guide/express-quickstart.md) | 部署 generation-2 模板并调用命名命令 |
| [SDK 使用](guide/sdk-usage.md) | 命令、文件、命名命令、模板作者快速路径 |
| [SDK skill](guide/sdk-skill.md) | 编码 agent 在写客户端或模板之前加载的说明 |
| [云上端到端练习](guide/cloud-examples.md) | 在默认提供方上跑 quickstart 与 compat-demos |
| [认证配置](guide/authentication.md) | API Key / AK-SK |
| [声明式用法](guide/declarative-usage.md) | `@sandbox` 装饰器 |
| [MCP 集成](guide/mcp-integration.md) | 把沙箱操作交给 IDE |
| [会话持久化](guide/session-persistence.md) | 本地会话存储 |
| [E2B 迁移](guide/migrate-from-e2b.md) | 从 E2B 迁移 |
| [提供方](guide/providers.md) | 选择、安装、编写提供方 |
| [环境变量](guide/environment-variables.md) | 注入与沙箱内读取 |
| [故障排查](guide/troubleshooting.md) | 常见问题 |
| [对比](guide/comparison.md) | 与 E2B、Modal、Docker Sandbox |
| [命令与 SDK 对照](guide/command-map.md) | 与 E2B、OpenSandbox 的命令和方法 |

### Server SDK — 构建沙箱里的服务

| 文档 | 说明 |
|------|------|
| [Server SDK](guide/server-sdk.md) | 这一侧是什么，以及 `commands.py` 怎么启动 |
| [模板编写](guide/authoring-templates.md) | `template.yaml`、能力声明、注册命令、Dockerfile |
| [模板服务器 HTTP API](guide/template-server-api.md) | `commands.py` 实际提供的路由 |
| [最佳实践](guide/best-practices.md) | 服务器不携带提供者、按需打开能力组 |
| [细粒度能力](guide/fine-grained-capabilities.md) | 按端点打开路由 |
| [文件与命令控制](guide/file-and-command-controls.md) | 限制路径和命令 |
| [Agents API](guide/agents-api.md) | 沙箱里的 Codex 与 Qwen Code HTTP 会话 |
| [托管代理](guide/hosted-agents.md) | 这些路由的拒绝和响应 |
| [构建与部署](guide/build-and-deploy.md) | `abx template build` 与 `abx template deploy` |

测试如何算完成，见[测试与完成定义](guide/testing-e2e.md)。

### [`reference/`](reference/) — API / 配置参考

| 文档 | 说明 |
|------|------|
| [API 参考](reference/api-reference.md) | Client SDK 公开 API |
| [配置参考](reference/configuration.md) | Client SDK 的环境变量、配置文件、凭证解析 |
| [错误码](reference/error-codes.md) | E1xxx–E8xxx 错误码索引 |
| [template.yaml 规范](reference/template-yaml-spec.md) | Server SDK 模板定义（`template.yaml`） |
| [Server HTTP API](reference/server-http-api.md) | 沙箱内 Server SDK 的 HTTP API |
| [Agents API 参考](reference/agents-api.md) | Server SDK 上每条 Agents 路由的参数与响应 |

### [`explanation/`](explanation/) — 概念解释与架构综述

| 文档 | 说明 |
|------|------|
| [架构综述](explanation/architecture-overview.md) | 六层分层架构概念解释 |
| [E2B 兼容性](explanation/e2b-compatibility.md) | E2B 风格 API 与 E2B 的共同点和差异 |
| [沙箱生命周期](explanation/sandbox-lifecycle.md) | 创建→运行→休眠→销毁 |

## 设计文档

改产品时再看这里。日常使用从上面的用户文档进入。用户向的 Agents API 在 [Agents API](guide/agents-api.md)（Codex 与 Qwen Code，CLI 按需安装）。

| # | 文档 | 说明 |
|---|------|------|
| 1 | [系统架构设计](design/architecture.md) | 六层分层架构总览、各层职责、目录结构 |
| 2 | [SDK API 设计](design/sdk-api-design.md) | 两种使用范式、命令与错误模型、SDK 边界 |
| 3 | [沙箱类型体系](design/sandbox-types.md) | 临时/持久/休眠三种模式、生命周期状态机、计费模型 |
| 4 | [MCP Server](design/mcp-server.md) | 7 个 P0 工具定义、会话绑定、STDIO 与 Streamable HTTP 传输、IDE 配置 |
| 5 | [模板体系](design/template-system.md) | 官方模板、自定义模板、sandbox.yaml 规范、版本管理、模板市场 |
| 6 | [Server API](design/server-api.md) | 容器内 HTTP Server 端点定义 |
| 7 | [Provider 与凭证](design/providers-and-credentials.md) | 规范配置名、provider 插件、EPP/1 |
| 8 | [OpenSandbox 提供方](design/provider-opensandbox-mapping.md) | 现行适配器与真实调用对照 |
| 9 | [容器版](design/provider-alicloud-container.md) | `alicloud-container` |
| 10 | [CubeSandbox 提供方](design/provider-cubesandbox.md) | `cubesandbox` |
| 11 | [E2B 提供方](design/provider-e2b.md) | `e2b` |

其余维护者设计稿在 [DESIGN.md](DESIGN.md) 中索引。

## 归档

这些页面是评审记录或目标设计，不是现行规范。

- [Server SDK v2 目标设计](archive/server-sdk-v2/README.md)
- [Agents API 评审](archive/agents-api-review.md)
- [细粒度能力评审](archive/fine-grained-capabilities-review.md)
- [提供方与凭证评审](archive/providers-and-credentials-review.md)
- [OpenSandbox 调研](../en/archive/provider-opensandbox-research.md)
- [OpenSandbox 端到端记录](archive/opensandbox-e2e-adversarial.md)
- [CLI 跟进项](archive/cli-followups.md)

## 项目规划

| 文档 | 说明 |
|------|------|
| [完整设计文档](DESIGN.md) | 设计专题索引与实现状态 |

---

## 快速导航

### 按角色

- **使用沙箱（Client SDK）**：[Client SDK](guide/client-sdk.md) → [快速开始](guide/getting-started.md) → [SDK 使用](guide/sdk-usage.md)
- **构建沙箱里的服务（Server SDK）**：[Server SDK](guide/server-sdk.md) → [模板编写](guide/authoring-templates.md) → [模板服务器 HTTP API](guide/template-server-api.md)
- **架构师**：[系统架构](design/architecture.md) → [Server API](design/server-api.md)

### 按功能

- **MCP 集成（Cursor/Claude）**：[MCP 集成](guide/mcp-integration.md#配置-ide) | [MCP Server](design/mcp-server.md#5-安装方式与-cli)

### 其他资源

- **模板真源（awesome-templates）**：[alibaba-agent-sandbox/awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates) — 官方与社区模板内容、索引（`awesome-templates.yaml`）与发布的唯一真源
- **English Documentation**：[English docs](../en/README.md)

## 相关：abx CLI

`abx` CLI（npm 包 `@agent-sandbox/cli`）的文档位于 [`cli` 仓库](https://github.com/alibaba-agent-sandbox/agent-sandbox)：[文档中心](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/README.md)、[快速开始](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/getting-started.md)、[CLI 参考](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/cli-reference.md)、[CLI 架构](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/design/architecture.md)、[CLI 命令体系](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/design/cli-design.md)、[模板目录](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/design/templates-catalog.md)、[部署与构建](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)、[Agent Skill 安装与分发](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/agent-skill-installation.md)。

[E2B 迁移契约](guide/migrate-from-e2b.md)定义同步 Sandbox、异步 AsyncSandbox 和解释器接口；Provider/Server 扩展使用 ProviderSandbox。

- [本地暂停与快照验收](guide/conditional-acceptance.md)
