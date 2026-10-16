# 系统架构设计 — 标准客户端与 Provider 扩展

> Python SDK 有两套公开客户端入口。根目录的 `Sandbox`／`AsyncSandbox` 与 `code_interpreter` 使用由本项目维护、固定版本的 MIT 源码移植，实现阿里云支持的 E2B 行为；`ProviderSandbox` 提供异步 Provider／Server／声明式扩展，下文介绍其原生分层。两条路径运行时均不安装上游 E2B 分发包。见[从 E2B 迁移](../guide/migrate-from-e2b.md)。

`ABX_PROVIDER` 为 `ProviderSandbox` 选择适配器，不会切换标准客户端的协议。标准客户端使用显式连接参数与 `E2B_API_KEY`／`E2B_API_URL`／`E2B_DOMAIN`。原生实现和源码移植仍然分开维护，本文不表示它们已经统一为一套协议实现。

---

## 1. 架构总览图

```mermaid
graph TD
    L5["L5 Agent Integration Layer<br/>AI 集成层 - MCP Server / Agent 工具定义"]
    L4["L4 Declarative API Layer<br/>声明式 API 层 - @sandbox 装饰器 / sandbox.yaml"]
    STD["标准客户端 — Sandbox / AsyncSandbox / code_interpreter"]
    PORT["维护的源码移植 — _standard / 解释器协议"]
    L3["L3 Provider 扩展<br/>ProviderSandbox / Files / Code / 命名命令"]
    L2["L2 Core Protocol Layer<br/>核心协议层 - envd REST + WebSocket"]
    L1["L1 Transport & Auth Layer<br/>传输与认证层 - HTTP 连接池 / API Key / AK-SK 兑换 Token"]
    GW["阿里云 API 网关"]
    FC["阿里云函数计算 FC 沙箱运行时"]

    STD --> PORT
    PORT --> GW
    PORT --> FC
    L5 --> L3
    L4 --> L3
    PRV["Provider adapters / local CLI engine"]
    L3 --> PRV
    PRV -->|内置适配器| L2
    L2 --> L1
    L1 --> GW
    L1 --> FC
```

---

## 2. 原生 Provider 扩展的各层职责

### L1 — Transport & Auth Layer（传输与认证层）

| 模块 | 职责 |
|------|------|
| `transport.http` | 基于 httpx 封装 HTTPS 请求，连接池管理，超时/重试策略 |
| `transport.ws` | 基于 websockets 的长连接，心跳保活，自动重连 |
| `auth.api_key` | **API Key 认证（主路径）**：通过 `X-API-KEY` 请求头传递，环境变量 `E2B_API_KEY` |
| `auth.ak_sk` | **AK/SK 认证（扩展）**：通过阿里云 AK/SK 兑换临时 API Key，或用于控制面 OpenAPI 调用 |
| `auth.config` | 多环境配置加载（代码参数 → 环境变量 → .env → config.toml → 默认值） |

**双认证模式**：

| 认证方式 | 场景 | 传递方式 | 环境变量 |
|----------|------|----------|----------|
| **API Key（主路径）** | 云沙箱数据面操作 | `X-API-KEY` 请求头 | `E2B_API_KEY` |
| **AK/SK（扩展）** | 兑换临时 API Key、控制面 OpenAPI | 阿里云 V4 签名 | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` |

> **注意**：沙箱 API Key 只有一个环境变量 `E2B_API_KEY`。AccessKey 对使用 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`。见 [authentication.md](../guide/authentication.md) 与 [configuration.md](../reference/configuration.md)。

**面向用户**：基础设施开发者、需要自定义认证逻辑的高级用户。

### L2 — Core Protocol Layer（核心协议层）

`protocol/` 中的**原生协议客户端**基于 httpx + websockets，供内置 Provider 路径使用；标准客户端另有 `_standard/` 和 `code_interpreter/` 中维护的源码移植。其他 Provider 使用各自适配器。原生协议模块分为两类 API：

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
| `api.sandbox` | 根包导出为 `ProviderSandbox` 的原生类；经所选 Provider 创建／管理沙箱；`run(name, **kwargs)` 调用服务端注册命令 |
| `api.server_client` | `ServerClient` — 沙箱内 SandboxServer 全部路由的类型化客户端 |
| `api.files` | 高层文件操作 — 上传/下载/监听 |
| `api.code` | 代码执行引擎 — 多语言支持，Rich Output |

**面向用户**：Provider／Server 扩展用户。固定版本的同步／异步 E2B 行为契约使用标准客户端入口。

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
    STD[标准客户端] --> PORT[维护的源码移植]
    L5[L5 Agent Integration] --> L3[L3 Provider 扩展]
    L4[L4 Declarative API] --> L3
    PRV["Provider adapters / local CLI engine"]
    L3 --> PRV
    PRV -->|内置适配器| L2[L2 Core Protocol]
    L2 --> L1[L1 Transport & Auth]
```

**依赖规则**：

1. **严格向下依赖**：每层只能依赖其下方的层，禁止反向依赖或跨层依赖
2. **L4 依赖 L3**：声明式 API 通过 L3 高层 API 实现，不直接依赖 L2
3. **L5 依赖 L3**：Agent 集成通过 L3 高层 API 实现
4. **原生传输层范围**：内置的原生适配器使用 L1；已安装 Provider 与标准源码移植客户端有各自的协议／传输路径。Provider 声明能力，不代表 CLI 已接入该操作，也不代表账号／运行时已启用。

---

## 4. 项目目录结构

```
client-sdk/src/agent_sandbox/
├── __init__.py                    # 根导出：Sandbox、AsyncSandbox、ProviderSandbox、sandbox
├── _standard/                     # 固定版本标准客户端、生成模型、Connect 运行时
├── code_interpreter/              # 标准同步／异步解释器客户端
├── providers/                     # Provider 适配器、选择与本机引擎桥接
├── _version.py                    # 版本号
│
├── transport/                     # L1 — 传输与认证层
│   ├── __init__.py
│   ├── http.py                    #   httpx HTTPS 客户端，连接池
│   ├── ws.py                      #   websockets 长连接，心跳保活
│   ├── auth.py                    #   API Key 认证 + AK/SK 兑换
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
│   ├── sandbox.py                 #   ProviderSandbox 原生实现
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

1. **固定标准行为，显式扩展入口**：标准 `Sandbox`／`AsyncSandbox` 与解释器客户端遵循阿里云支持的 E2B 基线；`agent_sandbox.compat` 重新导出标准客户端。Provider／Server／声明式扩展使用 `ProviderSandbox`，有条件的后端能力仍需要对应账号、运行时和模板支持。
2. **渐进式复杂度**：用户从 L3 开始，按需向下探索或向上使用高级功能
3. **明确连接配置**：沿用既有阿里云 `E2B_API_KEY`、`E2B_API_URL` 和 `E2B_DOMAIN` 配置；显式客户端参数优先。
4. **阿里云原生**：为阿里云 FC 沙箱服务而做
5. **AI First**：沙箱内置 AI CLI 工具、MCP Server 是一等公民，SDK 零 LLM 依赖
6. **类型安全**：原生维护模块使用 Python 类型检查与 Pydantic 验证。固定版本／生成源码有局部 lint/type 排除和独立契约测试；通过这些测试不代表所有云端能力都可用。
