# Server SDK v2：目标设计与实现状态

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

本目录描述 Agent Sandbox 服务端 SDK（`python-sdk/server-sdk`，导入名 `agent_sandbox.server`）的**目标设计**，不是已发布服务端的文档。01-09 提出了一套*操作模型*（点分操作 ID、`@op`、`POST /ops/{id}`、按 ID 写的 allow/deny 规则），**代码没有实现**。现行服务端的行为请读 [server-api.md](../../design/server-api.md)、[fine-grained-capabilities.md](../../design/fine-grained-capabilities.md) 和各指南。

长篇目标设计（01-09）只有英文版。英文 README 有完整的实现状态表：[en/archive/server-sdk-v2/README.md](../../../en/archive/server-sdk-v2/README.md)。本页只用中文写出同样的事实。

## 1. 已实现的部分

| 方面 | 现行形态 |
|---|---|
| 一张声明表 | `server/endpoints.py` 的 `ENDPOINTS`：118 个端点（其中 70 个是 Agents API；PTY WebSocket 是虚拟端点 `pty_connect`），每个都有 id、方法、路径、组、scope 和限额。路由表、策略、审计日志、`/capabilities` 和客户端都使用这些 id。 |
| 一个策略引擎 | `ServerPolicy` + `PolicyEngine`，分层为：默认 < 代码 < 预设 < 策略（`template.yaml` 的 `server:` 或 `ServerPolicy`）< 环境变量（`ABX_SERVER_ENABLED_GROUPS`，只能开启）。组是展开成端点 id 的别名；最具体的选择器（端点 id > 通配符 > 组 > `@defaults`）生效，每次拒绝都会指出命中的规则。 |
| 一条分发管线 | `SandboxRequestHandler`：匹配、鉴权（Bearer 或 `X-Access-Token`）、准入（404 `endpoint_disabled`、403 `missing_scope`、429）、重复查询参数检查、体积限制、处理、审计。v1 HTTP 路径就是这张表的绑定。 |
| 防护 | 路径边界（默认 `/home/user`，可用 `ABX_SERVER_BASE_DIR`、策略 `base_dir`、按端点的 `paths` 调整），覆盖所有带路径的端点，包括 shell 的 `cwd`；命令允许/拒绝参数（`command_not_allowed`）；体积限制；限流和并发上限；审计。 |
| 发现 | `GET /capabilities`（每个端点的状态、命中规则、scope、组摘要）、`POST /capabilities/check`。 |
| 具名命令 | `CommandRegistry`、模块级 `command` 装饰器、`GET /commands`、`POST /commands/{name}`。 |
| Agents API | 70 条路由，全部是真实实现，每条路由有表驱动测试；`codex` 和 `qwen-code` 有本地后端；`claude-code`、`cursor`、`command` 是只声明的适配器，没有本地后端（`GET /v1/agents/runtimes` 中 `implemented: false`）。 |
| 命令行 | `python -m agent_sandbox.server serve | healthcheck | check-config | version`。 |

## 2. 没有实现的部分

| 设计里提出的内容 | 状态 |
|---|---|
| 点分操作 ID（`files.download`）、`@op` 装饰器、`ops` 属性树、`Registry` | 没有实现。唯一的标识是端点 id（`files_download`）。再加一套 id 空间需要在表旁边加映射层，已否决。 |
| `POST /ops/{id}` RPC、`GET /ops`、`core.describe`、`core.check`、`GET /openapi.json` | 没有实现（不存在 `/ops` 路由）。发现接口是 `/capabilities`。 |
| `Policy().allow(...)` / `deny(...)` 构建器、`PathScope`、`CommandScope`、`UrlScope`、`AgentScope` | 没有实现。规则是 `ServerPolicy` 数据：`groups`，以及带 `enabled`、`scopes`、`paths`、`limits`、`params`（含命令和 URL 列表）、`audit` 的 `endpoints` 选择器。 |
| 只能否决的钩子、按主体 `role:` / `id:` 匹配规则 | 没有实现（主体只用于审计和 scope）。 |
| 热重载，`explain`、`describe`、`prepare`、`doctor` 子命令 | 没有实现（只有 `serve`、`healthcheck`、`check-config`、`version`）。 |
| 带校验和的 Agent CLI 延迟安装（06） | 没有实现。 |
| Host/Origin 白名单、套接字超时、一次性 PTY 票据（03 第 15 节） | 没有实现。 |
| 生成式客户端镜像（`ServerClient`、`operations.json`、TypeScript 客户端）（07） | 没有实现。 |
| Agents API 梯队（05）：`claude-code`、`cursor`、`command` 的本地后端 | 没有实现。（`/v1/responses` 路由现行存在，见 `ENDPOINTS`。） |
| LLM 密钥代理（`llm.proxy`） | 没有实现。 |
| `legacy_compat` 预设 | 不会存在：项目未发布，没有兼容层。 |

## 3. 索引

下列文件都是目标设计，每个中文页只是状态页，长文在英文版。与第 1 节冲突时，以第 1 节和现行文档为准。

| 文件 | 内容 |
|---|---|
| [01-principles.md](01-principles.md) | 规则、范围、术语 |
| [02-operation-model.md](02-operation-model.md) | 操作 ID、`@op`、绑定、请求管线、发现、自定义操作 |
| [03-policy-and-permissions.md](03-policy-and-permissions.md) | allow/deny 策略模型、scope、钩子、限额、配置分层、错误、威胁模型 |
| [04-builtin-modules.md](04-builtin-modules.md) | 内置操作目录 |
| [05-agents-api.md](05-agents-api.md) | 由 CLI Agent 适配器提供的 OpenAI Agents API |
| [06-lazy-install.md](06-lazy-install.md) | 授权后安装 Agent CLI |
| [07-client-mirror.md](07-client-mirror.md) | 由同一份目录生成的客户端 |
| [08-template-building-ux.md](08-template-building-ux.md) | `server:` 段、构建注入、作者旅程 |
| [09-ai-codegen-usability.md](09-ai-codegen-usability.md) | 给 AI 写服务端配置用的参考卡 |

## 4. 从设计走到代码时改变的决定

- 端点表是唯一的声明，旁边没有操作注册表。
- 能力开关只有一层（端点策略）。`enable_builtin`、`disable_builtin` 和 `ABX_SERVER_DISABLED_GROUPS` 已删除；组是端点的别名。
- 只有一个分发器。v1 路径是 HTTP 绑定，没有别的东西在分发。
- 服务端声明的端点就是已实现的端点；运行时做不到的事用数据（`implemented`、`installed`）报告，而不是另走一条代码路径。
