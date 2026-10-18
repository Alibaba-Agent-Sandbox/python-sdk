# 系统架构设计 — 五层分层架构

> Agent Sandbox SDK 采用五层分层架构，从底层传输到上层 AI 集成逐层抽象，每层职责单一、边界清晰，用户可在任意层级接入使用。SDK 零 LLM 依赖，不依赖 E2B SDK，直接对接 envd 数据面和平台控制面。它是运行时客户端：模板的构建和部署由 `abx template build|deploy` 完成。

---

## 1. 架构总览图

```mermaid
graph TD
    L5["L5 Agent Integration Layer<br/>AI 集成层 - MCP Server / Agent 工具定义"]
    L4["L4 Declarative API Layer<br/>声明式 API 层 - @sandbox 装饰器 / sandbox.yaml"]
    L3["L3 High-Level API Layer<br/>高层便捷 API - Sandbox / Files / Code / 命名命令"]
    L2["L2 Core Protocol Layer<br/>核心协议层 - envd REST + WebSocket"]
    L1["L1 Transport & Auth Layer<br/>传输与认证层 - HTTP 连接池 / API Key / AK-SK 兑换 Token"]
    GW["阿里云 API 网关"]
    FC["阿里云函数计算 FC 沙箱运行时"]

    L5 --> L4
    L4 --> L3
    L3 --> L2
    L2 --> L1
    L1 --> GW
    L1 --> FC
```

---

## 2. 各层职责详述

### L1 — Transport & Auth Layer（传输与认证层）

| 模块 | 职责 |
|------|------|
| `transport.http` | 基于 httpx 封装 HTTPS 请求，连接池管理，超时/重试策略 |
| `transport.ws` | 基于 websockets 的长连接，心跳保活，自动重连 |
| `auth.api_key` | **API Key 认证（主路径）**：通过 `X-API-KEY` 请求头传递，环境变量 `ABX_SANDBOX_API_KEY` |
| `auth.AkSkAuth` | 应用显式配置的自定义交换适配器；默认运行时需要 API Key |
| `auth.config` | 多环境配置加载（代码参数 → 环境变量 → .env → config.toml → 默认值） |

**双认证模式**：

| 认证方式 | 场景 | 传递方式 | 环境变量 |
|----------|------|----------|----------|
| **API Key（主路径）** | 云沙箱数据面操作 | `X-API-KEY` 请求头 | `ABX_SANDBOX_API_KEY` |
| **AK/SK 控制面** | CLI 官方模板/镜像/ACR 操作 | 官方 SDK | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` |

> **注意**：沙箱 API Key 只有一个环境变量 `ABX_SANDBOX_API_KEY`。AccessKey 对使用 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`。见 [authentication.md](../guide/authentication.md) 与 [configuration.md](../reference/configuration.md)。

**面向用户**：基础设施开发者、需要自定义认证逻辑的高级用户。

### L2 — Core Protocol Layer（核心协议层）

**自行实现协议客户端**，不依赖 E2B SDK，直接基于 httpx + websockets 实现。区分两类 API：

- **Platform API（REST）**：沙箱生命周期管理（创建、列表、销毁），通过 HTTP REST API 与阿里云平台交互
- **Sandbox envd API（Connect 协议）**：沙箱内部操作（进程、文件、终端），通过 HTTP + WebSocket 与沙箱 envd 通信

| 模块 | 职责 |
|------|------|
| `protocol.sandbox` | 沙箱生命周期管理（HTTP REST API） |
| `protocol.process` | 远程进程管理（启动、流式输出、信号、退出码），HTTP + WebSocket 流式 |
| `protocol.filesystem` | 远程文件系统操作（读、写、列目录、监听变更），HTTP REST |
| `protocol.terminal` | 虚拟终端（PTY）复用，WebSocket 双向通信 |
| `protocol.port` | 端口转发与映射管理（HTTP REST） |

**面向用户**：协议层开发者、需要细粒度控制的用户。

### L3 — High-Level API Layer（高层便捷 API）

| 模块 | 职责 |
|------|------|
| `api.sandbox` | Sandbox 类 — 创建、管理、执行、销毁的统一入口；`run(name, **kwargs)` 调用服务端注册命令 |
| `api.server_client` | `ServerClient` — 沙箱内 SandboxServer 全部路由的类型化客户端 |
| `api.files` | 高层文件操作 — 上传/下载/监听 |
| `api.code` | 代码执行引擎 — 多语言支持，Rich Output |

**面向用户**：绝大多数开发者，核心层，方法名参考 E2B。

### L4 — Declarative API Layer（声明式 API 层）

| 模块 | 职责 |
|------|------|
| `declarative.decorator` | `@sandbox` 装饰器 — Modal 风格远程执行 |
| `declarative.config` | `sandbox.yaml` 解析与验证 |
| `declarative.serializer` | 参数/返回值序列化（仅 JSON） |

**面向用户**：追求极简体验的 Python 开发者、ML 工程师。

### L5 — Agent Integration Layer（Agent 集成层）

| 模块 | 职责 |
|------|------|
| `agent.tools` | Agent 工具集 — 沙箱操作封装为 OpenAI function calling 格式 |
| `agent.mcp` | MCP Server 实现 — 暴露沙箱能力为 MCP Tools |

**面向用户**：AI 应用开发者、Agent 框架集成者。

> **注意**：SDK 零 LLM 依赖。在沙箱里运行编码 Agent 只有一种方式：[Agents API](../guide/agents-api.md)（`/v1/agents/**`，由 `agent-sandbox-server` 提供）。SDK 没有 Agent 关键字表，也没有 `sb.agent.*` 语法糖。

### Server 模块（容器内运行时服务）

| 模块 | 职责 |
|------|------|
| `server.app` | `SandboxServer` 主类 — stdlib-only HTTP server，零第三方依赖，容器内常驻运行 |
| `server.router` | `RouteTable` + `CapabilityGroup` — 声明式路由注册与能力组开关 |
| `server.registry` | `CommandRegistry` — 用户自定义命令注册与发现 |
| `server.routes` | 核心内置路由：health、commands、upload、download、shell |
| `server.routes_files` | 文件操作端点：list/stat/mkdir/delete/move/search/archive（9 端点） |
| `server.routes_process` | 进程管理端点：start/list/detail/signal + SSE 流式 shell（5 端点，按文件统计） |
| `server.routes_system` | 系统信息端点：info/env/ports/packages/metrics + capabilities（7 端点，按文件统计；注：server-api.md 按能力组统计口径不同） |
| `server.routes_pty` | PTY WebSocket 终端：会话创建/列表/删除 + WebSocket 交互式终端 |
| `server.routes_browser` | 浏览器自动化端点：navigate/screenshot/content/click/type/evaluate/pdf/console（8 端点） |
| `server.routes_devtools` | 开发工具端点：code/run、git/status、git/diff（3 端点） |
| `server.types` | 请求/响应数据模型：`ServerRequest`、`ServerResponse`、`SSEResponse` |

Server 模块（独立的 `agent-sandbox-server` 分发包，导入路径 `agent_sandbox.server`）运行在沙箱容器内部，与 SDK 主体分层不同，它是用户 opt-in 的容器内常驻 HTTP 服务。完全基于 Python stdlib，零第三方依赖（PTY 终端使用 `agent-sandbox-server` 分发包自身的 `websockets` 依赖）。提供 42 个端点，按 8 个 CapabilityGroup 分组管理：

| 能力组 | 说明 | 默认状态 |
|--------|------|----------|
| `CORE` | health、capabilities | 始终启用，不可禁用 |
| `COMMANDS` | 用户自定义命令注册与发现 | 启用 |
| `FILE_OPS` | 文件系统 CRUD + 归档 | 启用 |
| `PROCESS` | 进程管理 + SSE 流式 shell | 启用 |
| `SYSTEM` | 系统信息、环境变量、端口、包管理、指标 | 启用 |
| `TERMINAL` | PTY WebSocket 交互式终端 | 启用 |
| `DEV_TOOLS` | Code Interpreter + Git 操作 | 禁用（需显式启用） |
| `BROWSER` | Playwright 浏览器自动化 | 禁用（需显式启用） |

**面向用户**：沙箱模板开发者、需要在容器内注册自定义命令的高级用户。

---

## 3. 层间依赖关系

```mermaid
graph TD
    L5[L5 Agent Integration] --> L3[L3 High-Level API]
    L4[L4 Declarative API] --> L3
    L3 --> L2[L2 Core Protocol]
    L2 --> L1[L1 Transport & Auth]
```

**依赖规则**：

1. **严格向下依赖**：每层只能依赖其下方的层，禁止反向依赖或跨层依赖
2. **L4 依赖 L3**：声明式 API 通过 L3 高层 API 实现，不直接依赖 L2
3. **L5 依赖 L3**：Agent 集成通过 L3 高层 API 实现
4. **L1 为基础层**：所有上层最终依赖 L1 完成网络通信和认证

---

## 4. 项目目录结构

```
client-sdk/src/agent_sandbox/
├── __init__.py                    # 顶层导出：Sandbox, sandbox
├── _version.py                    # 版本号
│
├── transport/                     # L1 — 传输与认证层
│   ├── __init__.py
│   ├── http.py                    #   httpx HTTPS 客户端，连接池
│   ├── ws.py                      #   websockets 长连接，心跳保活
│   ├── auth.py                    #   API Key/envd 认证；显式自定义 token 适配
│   └── config.py                  #   配置加载（代码参数→环境变量→.env→config.toml→默认值）
│
├── protocol/                      # L2 — 核心协议层
│   ├── __init__.py
│   ├── sandbox.py                 #   沙箱生命周期 API（HTTP REST）
│   ├── process.py                 #   远程进程管理（HTTP + WebSocket 流式）
│   ├── filesystem.py              #   远程文件系统操作（HTTP REST）
│   ├── terminal.py                #   PTY 终端复用（WebSocket）
│   └── port.py                    #   端口转发管理（HTTP REST）
│
├── api/                           # L3 — 高层便捷 API
│   ├── __init__.py
│   ├── sandbox.py                 #   Sandbox 核心类
│   ├── server_client.py           #   ServerClient — 沙箱内 server 的类型化客户端
│   ├── files.py                   #   高层文件操作
│   └── code.py                    #   代码执行引擎
│
├── declarative/                   # L4 — 声明式 API 层
│   ├── __init__.py
│   ├── decorator.py               #   @sandbox 装饰器
│   ├── config.py                  #   sandbox.yaml 解析
│   └── serializer.py              #   参数序列化
│
├── agent/                         # L5 — AI 集成层
│   ├── __init__.py
│   ├── tools.py                   #   Agent 工具集（OpenAI function calling 格式）
│   └── mcp.py                     #   MCP Server 实现
│
├── models/                        # 数据模型
│   ├── __init__.py
│   ├── sandbox.py                 #   SandboxInfo, SandboxConfig
│   ├── process.py                 #   ProcessResult, ProcessConfig
│   ├── filesystem.py              #   FileInfo, WatchEvent
│   └── errors.py                  #   异常类层次
│
└── utils/                         # 工具函数
    ├── __init__.py
    ├── retry.py                   #   重试策略
    ├── logging.py                 #   日志工具
    └── async_bridge.py            #   同步/异步桥接工具
```

容器内运行时以独立的 `agent-sandbox-server` 分发包发布（共享 `agent_sandbox` 命名空间，自身没有 `agent_sandbox/__init__.py`，与 client 同步发布）：

```
server-sdk/src/agent_sandbox/server/   # 容器内运行时 HTTP Server（opt-in，stdlib-only）
├── __init__.py                #   模块导出：SandboxServer, start, CapabilityGroup, RouteTable
├── app.py                     #   SandboxServer 主类，HTTP 请求分发
├── router.py                  #   RouteTable 声明式路由 + CapabilityGroup 能力组枚举
├── registry.py                #   CommandRegistry 用户自定义命令注册
├── routes.py                  #   核心内置路由（health/commands/upload/download/shell）
├── routes_files.py            #   FILE_OPS 能力组（9 端点）
├── routes_process.py          #   PROCESS 能力组（5 端点）
├── routes_system.py           #   SYSTEM 能力组 + CORE/capabilities（7 端点）
├── routes_pty.py              #   TERMINAL 能力组（REST + WebSocket PTY）
├── routes_browser.py          #   BROWSER 能力组（8 端点，Playwright）
├── routes_devtools.py         #   DEV_TOOLS 能力组（Code Interpreter + Git）
└── types.py                   #   ServerRequest/ServerResponse/SSEResponse
```

CLI（`abx`）原先位于 `src/agent_sandbox/cli/`（`commands/` 下的 Click 子命令、`formatters.py`、`output.py`），现已迁移为 `cli` 仓库中的 Node.js/TypeScript 项目，不再属于本包。

---

## 5. 技术选型

| 领域 | 选型 | 理由 |
|------|------|------|
| HTTP 客户端 | `httpx` | 原生 async 支持，HTTP/2，协议客户端的核心 |
| WebSocket | `websockets` | 成熟稳定，async 原生，用于 PTY/流式场景 |
| CLI 框架 | _（已迁移）_ | CLI 是 `cli` 仓库中独立的 Node.js/TypeScript 项目；原 `click` + `rich` 实现不再属于本包 |
| 序列化 | JSON（`json` 标准库） | `@sandbox` 装饰器的安全跨语言序列化 |
| 配置管理 | `pydantic` | 类型安全的配置验证 |
| 测试 | `pytest` + `pytest-asyncio` | 异步测试标准方案 |
| 包管理 | `hatch` / `pdm` | 现代 Python 项目管理 |

---

## 6. 设计原则

1. **方法名参考 E2B，但不兼容 E2B**：L3 沿用 E2B 风格的方法名，并提供一个小的迁移辅助（`agent_sandbox.compat`）；L2 层自行实现协议，不依赖 E2B SDK
2. **渐进式复杂度**：用户从 L3 开始，按需向下探索或向上使用高级功能
3. **零配置默认**：开箱即用的默认值，设置 `ABX_SANDBOX_API_KEY` 环境变量即可启动
4. **阿里云原生**：为阿里云 FC 沙箱服务而做
5. **AI First**：沙箱内置 AI CLI 工具、MCP Server 是一等公民，SDK 零 LLM 依赖
6. **类型安全**：全面使用 Python Type Hints + Pydantic 验证

- [Provider implementation boundaries](provider-isolation.md)
提供方配置发现由包入口延迟装配。传输配置只消费 `_provider_schema.py` 中的低层 `ProviderSchema` 值与注入的解析器，不导入提供方 registry。内置配置不触发提供方发现；注册、entry-point 和已安装提供方仍遵循原有选择、派生、默认值及继承规则。原 `transport.config.ProviderSchema` 导入保留为同一类的别名。

内置平台/envd HTTP 每次执行一次传输尝试。旧重试字段作为兼容数据保留，边界见[配置说明](../reference/configuration.md#旧重试配置的兼容边界)，引擎恢复另行处理。
