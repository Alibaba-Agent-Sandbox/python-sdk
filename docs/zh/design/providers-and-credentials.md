# 提供方与凭证 —— 命名方案与提供方插件架构

> **状态**：已接受（经两轮对抗式评审，见 [providers-and-credentials-review.md](../archive/providers-and-credentials-review.md)） · **范围**：Python SDK（`client-sdk`）与 Node.js `abx` CLI · **面向 CLI 的规格**：`cli/docs/design/providers-and-credentials-cli.md`
>
> **命名规则**：每个配置键只有一个环境变量。读取方只接受这个变量，`abx config set` 也写入这个名字。没有第二个名字，也没有迁移命令。
>
> **关于本译文**：这是英文设计文档的中文版，章节编号一致。表格、协议字段、代码块与英文版逐项对应；两者出现差异时以[英文版](../../en/design/providers-and-credentials.md)为准。

---

## 0. 目标与非目标

**目标**

1. 每个凭证 / 配置键在所有位置使用同一套命名：`config.toml`、`~/.abx/.env`、`abx config set/get`、环境变量、SDK 的 `TransportConfig` 字段与 `Sandbox.*` 关键字参数、CLI 选项。
2. 每个键只有一个环境变量，列在 §3。读取方在第一个设置了该变量的层停止。
3. 提供方抽象，使阿里云之外的后端以后可以通过**插件**加入：CLI 用 `abx provider install <路径或 git URL>` 安装，只用 SDK 的用户用 `python -m agent_sandbox.providers install ...`；可按命令（`--provider`）、按进程（`ABX_PROVIDER`）、按项目（`./.env`）、按用户（配置）、按 SDK 调用（`Sandbox.create(provider=...)`）选择。
4. 内置提供方保持默认，对外呈现为**阿里云极速版（Alibaba Cloud Express Edition）**，稳定 id 为 `alicloud-express`。

**非目标（v1）**

* 在硬沙箱里运行不受信任的插件代码（跨平台做不到；我们采用同意 + 固定 + 完整性 + 环境清理，见 §8）。
* 公共插件注册表 / 市场（清单里预留了 `source` 位置；v1 只支持目录或 git URL）。
* 重命名 `ABX_SERVER_*`、`ABX_PTY_PORT`、`ABX_MAX_UPLOAD_SIZE`（已烘焙进已部署镜像的沙箱内 server 变量）。

---

## 1. 清单

扫描范围：`transport/config.py`、`transport/auth.py`、`models/config.py`、`models/errors.py`、`api/{sandbox,deploy,docker_builder,image,fc_template}.py`（构建与部署模块后来已从客户端删除）、`declarative/decorator.py`、`agent/{mcp,mcp_http}.py`、`utils/{github_token,registry,template_index,logging}.py`、CLI、`agent/qwen_code.py`、`.env.example` 以及文档。

### 1.1 沙箱控制面 / 传输层

| 概念 | `abx config` 键 | config.toml | 环境变量 | SDK 字段 |
|---|---|---|---|---|
| 沙箱 API Key | `sandbox_api_key` | 密钥在 `~/.abx/.env` | `ABX_SANDBOX_API_KEY` | `sandbox_api_key` |
| 平台地址 | `sandbox_base_url` | `[transport] sandbox_base_url` | `ABX_SANDBOX_BASE_URL` | `sandbox_base_url` |
| 数据平面域名 | `sandbox_domain` | `[transport] sandbox_domain` | `ABX_SANDBOX_DOMAIN` | `sandbox_domain` |
| 地域 | `region` | `[providers.alicloud-express] region` | `ALIBABA_CLOUD_REGION_ID` | `region` |
| HTTP 超时 | `http_timeout` | `[transport] http_timeout` | `ABX_HTTP_TIMEOUT` | `http_timeout` |
| HTTP/2 | `http2` | `http2` | `ABX_HTTP2` | `http2` |
| 最大重试 | `max_retries` | `max_retries` | `ABX_MAX_RETRIES` | `max_retries` |
| 日志级别 | `log_level` | `log_level` | `ABX_LOG_LEVEL` | `log_level` |
| 默认模板 | `default_template` | `default_template` | `ABX_DEFAULT_TEMPLATE` | `default_template` |
| 提供方 | `provider` | `[core] provider` | `ABX_PROVIDER` | `provider` |

沙箱 TTL（`Sandbox.create(timeout=)`、`--timeout/-t`）不是 HTTP 超时。

### 1.2 阿里云专属

| 概念 | `abx config` 键 | 环境变量 | 说明 |
|---|---|---|---|
| AccessKey ID | `access_key_id` | `ALICLOUD_ACCESS_KEY_ID` | `~/.abx/.env` |
| AccessKey Secret | `access_key_secret` | `ALICLOUD_ACCESS_KEY_SECRET` | `~/.abx/.env` |
| ACR 命名空间 | `acr_namespace` | `ACR_NAMESPACE` | |
| ACR 仓库地址 | `acr_registry` | `ACR_REGISTRY` | |
| ACR 仓库 | `acr_repo` | `ACR_REPO` | |
| ACR 用户名 / 密码 | `acr_username` / `acr_password` | `ACR_USERNAME` / `ACR_PASSWORD` | |
| ACR 企业版实例 | `acr_instance_id` | `ACREE_INSTANCE_ID` | |
| ACR 网络 | `acr_vpc_id`、`acr_vswitch_ids`、`acr_security_group_id` | `ACR_VPC_ID`、`ACR_VSWITCH_IDS`、`ACR_SECURITY_GROUP_ID` | |
| 团队 id | `team_id` | `ABX_ALICLOUD_EXPRESS_TEAM_ID` | 可选。不是必填项。 |

### 1.3 LLM / 编码代理（与提供方无关）

| 概念 | 键 | 环境变量 |
|---|---|---|
| LLM API Key | `llm_api_key` | `ABX_LLM_API_KEY` |
| LLM 地址 | `llm_base_url` | `ABX_LLM_BASE_URL` |
| LLM 模型 | `llm_model` | `ABX_LLM_MODEL` |
| 代理调优 | — | `ABX_QWEN_CODE_BIN`、`ABX_QWEN_RESEARCH_TIMEOUT`、`ABX_QWEN_CODEGEN_TIMEOUT` |

### 1.4 集成、工具、界面

| 概念 | 键 | 环境变量 | 说明 |
|---|---|---|---|
| GitHub token | `github_token` | `GITHUB_TOKEN` | 选项 `--token`（模板安装 / 搜索 / 更新）。存在 `~/.abx/.env`。 |
| 模板索引 URL | `template_index_url` | `ABX_TEMPLATE_INDEX_URL` | 仅环境变量 |
| 模板目录 | `template_dir` | `ABX_TEMPLATE_DIR` | 仅环境变量 |
| MCP server | `mcp_*` | `ABX_MCP_AUTH_TOKEN`、`ABX_MCP_ALLOWED_ORIGINS`、`ABX_MCP_RUNTIME_DIR` | 仅环境变量；沙箱调用用 `ABX_SANDBOX_API_KEY` |
| CLI 显示 | — | `ABX_ACTIVITY_LINES`、`ABX_DISCOVER_COMMANDS` | 不由 `abx config` 存储 |
| 快捷方式 | `shortcuts`、`shortcuts.<name>` | — | `config.toml` 的 `[shortcuts]` |
| 密钥库 | — | — | `~/.abx/secrets.json`（SDK `SecretStore`，0600）——不是配置面 |

### 1.5 沙箱内 server（`agent-sandbox-server`）

`ABX_SERVER_TOKEN`、`ABX_SERVER_BASE_DIR`、`ABX_SERVER_ENABLED_GROUPS`、`ABX_PTY_PORT`、`ABX_MAX_UPLOAD_SIZE`：已存在于外部镜像里的运行时变量，不重命名。

### 1.6 外部标准变量

`CI`、`GITHUB_ACTIONS`、`GITLAB_CI`、`JENKINS_URL`、`NO_COLOR`、`TERM`、`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`、`DOCKER_BUILDKIT`、`HOME`、`APPDATA`、`COMSPEC`。

### 1.7 其他配置面

| 位置 | 名字 | 处理 |
|---|---|---|
| `sandbox.yaml` 与 `@sandbox(...)` | `template`、`timeout`、`envs`、`cpu`、`memory`，以及 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain` | 还有 `provider`、`provider_options` |
| `GlobalConfig` | 与 `TransportConfig` 相同的字段名 | 普通数据模型 |
| 会话存储（`SessionInfo`） | `sandbox_base_url`、`sandbox_domain`、`envd_access_token` | 可选 `provider`（默认 `""` = 内置），重新连接时仍访问同一个提供方 |
| `Sandbox.create(secure=, request_timeout=, timeout=)` | 单次调用选项 | 不是凭证，保持不变 |
| 编码代理 id | — | *编码代理*不是*提供方* |
| `~/.qwen/settings.json` | Qwen Code CLI 自己的凭证文件 | 外部文件，abx 不改写 |
| 转发进沙箱的代理变量 | `ANTHROPIC_API_KEY`、`QODER_PERSONAL_ACCESS_TOKEN` 以及该代理自己的密钥变量 | 沙箱内代理凭证，原样转发；不是 abx 配置 |

**术语表（不要混用）。** *提供方（provider）*：创建并运行沙箱的后端（`alicloud-express`、某个插件）。*特性（feature）*：提供方实现的某项能力（§7.2）。*模板能力（template capability）*：沙箱*镜像*提供的服务（`shell`、`files`、`code`、`terminal`、`ports`）。*编码代理（coding agent）*：用于自然语言生成模板的 LLM CLI（`qwen-code`）。*核心键（core key）*：与提供方无关的配置键。*作用域键（scoped key）*：由某个提供方声明的键。

### 1.8 一个名字

§3 里的每个键只有一个环境变量。产品自己的设置用 `ABX_<KEY>`。产品采用的厂商变量就是那个唯一的名字：`ALICLOUD_ACCESS_KEY_ID`、`ALICLOUD_ACCESS_KEY_SECRET`、`ALIBABA_CLOUD_REGION_ID`、`ACR_*`、`ACREE_INSTANCE_ID`、`GITHUB_TOKEN`。`team_id` 可选，使用 `ABX_ALICLOUD_EXPRESS_TEAM_ID`。插件自己的字段使用 `ABX_<PROVIDER>_<KEY>`。

---

## 2. 命名原则

1. **键是 `snake_case`，每个概念只有一个名字，在所有位置相同。** 配置键、SDK 字段、关键字参数和选项（kebab-case）是同一个词：`sandbox_base_url` / `--sandbox-base-url`。
2. **前缀表示这个值关于什么。** `sandbox_*` 表示沙箱控制面 / 数据面；`llm_*` 表示 LLM 配置；`acr_*` 表示容器镜像仓库；`mcp_*` 表示 MCP server；`http_*` 表示 HTTP 客户端调优；提供方作用域的键在其命名空间内使用裸词（`region`、`access_key_id`）。
3. **每个键一个环境变量。** 产品设置用 `ABX_` + `UPPER(key)`（`sandbox_api_key` → `ABX_SANDBOX_API_KEY`）。厂商已经公布的变量就用那个变量，而且它是唯一的名字：阿里云 AccessKey 是 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`，地域是 `ALIBABA_CLOUD_REGION_ID`，ACR 是 `ACR_NAMESPACE` 以及对应的 `ACR_*`，GitHub token 是 `GITHUB_TOKEN`。`team_id` 可选，变量是 `ABX_ALICLOUD_EXPRESS_TEAM_ID`。插件字段是 `ABX_` + `UPPER(提供方 id，- 换成 _)` + `_` + `UPPER(key)`。
4. **提供方作用域。** 键要么是*核心键*（`provider`、`sandbox_api_key`、`sandbox_base_url`、`sandbox_domain`、`http_*`、`max_retries`、`llm_*`、`github_token`、`mcp_*` 等），要么是*提供方作用域键*（对 `alicloud-express` 是 `region`、`access_key_id`、`access_key_secret`、`acr_*`、`team_id`）。提供方可以声明自己使用某些核心键，并在自己的作用域里覆盖它们（`providers.<id>.sandbox_api_key`）。

---

## 3. 方案

### 3.1 核心键

| 键 | 类型 | 密钥 | 环境变量 | 默认值 |
|---|---|---|---|---|
| `provider` | id | 否 | `ABX_PROVIDER` | `alicloud-express` |
| `sandbox_api_key` | str | **是** | `ABX_SANDBOX_API_KEY` | 无 |
| `sandbox_base_url` | url | 否 | `ABX_SANDBOX_BASE_URL` | 由提供方推导（§4.5） |
| `sandbox_domain` | host | 否 | `ABX_SANDBOX_DOMAIN` | 由提供方推导 |
| `http_timeout` | float ≥ 1 | 否 | `ABX_HTTP_TIMEOUT` | `30.0` |
| `http2` | bool | 否 | `ABX_HTTP2` | `true` |
| `max_retries` | int ≥ 0 | 否 | `ABX_MAX_RETRIES` | `3` |
| `max_connections`、`max_keepalive_connections`、`keepalive_expiry`、`ws_ping_interval`、`retry_base_delay` | 数值 | 否 | `ABX_<KEY>` | 同现状 |
| `log_level` | 枚举 | 否 | `ABX_LOG_LEVEL` | `WARNING` |
| `default_template` | str | 否 | `ABX_DEFAULT_TEMPLATE` | `base` |
| `llm_api_key` | str | **是** | `ABX_LLM_API_KEY` | 无 |
| `llm_base_url` | url | 否 | `ABX_LLM_BASE_URL` | DashScope 兼容模式 |
| `llm_model` | str | 否 | `ABX_LLM_MODEL` | `qwen3-coder-plus` |
| `github_token` | str | **是** | `GITHUB_TOKEN` | 无 |
| `template_index_url` | url | 否 | `ABX_TEMPLATE_INDEX_URL` | 内置索引 |
| `template_dir` | path | 否 | `ABX_TEMPLATE_DIR` | 无 |
| `mcp_auth_token` | str | **是** | `ABX_MCP_AUTH_TOKEN` | 无 |
| `mcp_allowed_origins`、`mcp_runtime_dir` | str | 否 | `ABX_MCP_ALLOWED_ORIGINS`、`ABX_MCP_RUNTIME_DIR` | 无 |

不是持久配置键的纯环境变量调优（见环境变量指南，不变）：`ABX_ACTIVITY_LINES`、`ABX_DISCOVER_COMMANDS`、`ABX_QWEN_CODE_BIN`、`ABX_QWEN_RESEARCH_TIMEOUT`、`ABX_QWEN_CODEGEN_TIMEOUT`，以及沙箱内 server 变量（§1.5）。

`sandbox_domain` 和 `sandbox_base_url` 是通用键，因为每个 E2B 协议后端都有控制面 URL 和数据面域名；两者都没有的提供方不在 `uses_core` 里声明它们即可。

### 3.2 提供方作用域键：内置 `alicloud-express`

| 键 | 类型 | 密钥 | 环境变量 | 说明 |
|---|---|---|---|---|
| `region` | str | 否 | `ALIBABA_CLOUD_REGION_ID` | 推导基础 URL / 域名（§4.5）。默认 `cn-hangzhou`。 |
| `access_key_id` | str | 否（id） | `ALICLOUD_ACCESS_KEY_ID` | `credential` |
| `access_key_secret` | str | **是** | `ALICLOUD_ACCESS_KEY_SECRET` | `credential` |
| `acr_namespace` | str | 否 | `ACR_NAMESPACE` | |
| `acr_registry` | str | 否 | `ACR_REGISTRY` | |
| `acr_repo` | str | 否 | `ACR_REPO` | |
| `acr_username` | str | 否 | `ACR_USERNAME` | |
| `acr_password` | str | **是** | `ACR_PASSWORD` | |
| `acr_instance_id` | str | 否 | `ACREE_INSTANCE_ID` | |
| `acr_vpc_id` | str | 否 | `ACR_VPC_ID` | |
| `acr_vswitch_ids` | csv | 否 | `ACR_VSWITCH_IDS` | |
| `acr_security_group_id` | str | 否 | `ACR_SECURITY_GROUP_ID` | |
| `team_id` | str | 否 | `ABX_ALICLOUD_EXPRESS_TEAM_ID` | 可选。不是必填项。 |

内置提供方是唯一隐式使用通用 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain` 的提供方（与所有提供方一样，它也使用非密钥调优键 `http_timeout`、`http2`、`max_retries` 等）。插件只能通过 §4.6 的显式 `inherit` 申请来使用通用凭证 / 端点。

### 3.3 每个名字存在的位置

**`~/.abx/config.toml`**（手工编辑或由 `abx config set` 写入；SDK 与 CLI 都读取）：

```toml
[core]
provider = "alicloud-express"   # `abx provider default`

[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain   = "cn-hangzhou.e2b.fc.aliyuncs.com"
http_timeout = 30.0
http2 = true
max_retries = 3

[providers.alicloud-express]
region = "cn-hangzhou"

[providers.my-cloud]
cluster = "prod"

[shortcuts]
ps = "sandbox process list"
```

**`~/.abx/.env`**（权限 0600，密钥和类凭证值）。`abx config set` 写入该键唯一的环境变量：

| 键 | 存为 |
|---|---|
| `sandbox_api_key` | `ABX_SANDBOX_API_KEY` |
| `access_key_id`、`access_key_secret` | `ALICLOUD_ACCESS_KEY_ID`、`ALICLOUD_ACCESS_KEY_SECRET` |
| `acr_namespace`、`acr_password` 以及其他密钥或类凭证的 `acr_*` | 该键对应的 `ACR_*` / `ACREE_INSTANCE_ID` |
| `llm_api_key` | `ABX_LLM_API_KEY` |
| `github_token` | `GITHUB_TOKEN` |
| `team_id` | `ABX_ALICLOUD_EXPRESS_TEAM_ID`（可选） |
| `sandbox_base_url`、`sandbox_domain`、`http_timeout`、`http2`、`max_retries`、`llm_base_url`、`llm_model` | `[transport]` 中的同名键 |
| `region` | `[providers.alicloud-express]` 中的 `region`；环境变量 `ALIBABA_CLOUD_REGION_ID` |
| `provider` | `[core] provider` |

**SDK 接口**

* `TransportConfig` 字段：`provider`、`sandbox_base_url`、`sandbox_domain`、`sandbox_api_key`、`region`、`access_key_id`、`access_key_secret`、`http_timeout` 等，外加 `provider_options`。`model_dump()` 输出这些名字。
* `Sandbox.create/connect/list/kill_by_id/deploy` 与 `@sandbox(...)`：仅限关键字的参数 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain`、`region`、`provider`、`provider_options`、`access_key_id`、`access_key_secret`。

**CLI 选项**（规格见 CLI 文档）：`--sandbox-api-key`、`--sandbox-base-url`、`--sandbox-domain`、`--region/-r`、`--provider`、`--opt KEY=VALUE`。`--acr-*` 选项与 `acr_*` 一致。企业版实例的环境变量是 `ACREE_INSTANCE_ID`。

### 3.4 `abx config` 中的裸键与限定键

`abx config get|set|delete KEY` 接受：

1. **核心键**（`sandbox_api_key`、`sandbox_base_url`、`sandbox_domain` 等）。
2. **限定的提供方键** `providers.<id>.<key>`（无歧义，适用于所有提供方）。
3. **裸提供方键**（`region`、`access_key_id` 等）。它针对该命令的 `--provider` 所选提供方解析，否则针对**默认提供方**。如果该键不在那个提供方的 schema 里，命令以退出码 2 失败，并列出每个声明了该键的已安装提供方的限定形式。
4. `shortcuts` 与 `shortcuts.<name>`（保留前缀；提供方 id 和键永远不能以 `shortcuts` 开头）。

---

## 4. 优先级

### 4.1 层

```text
1. explicit        代码关键字参数 / CLI 选项 / `--opt`
2. process env     os.environ
3. ./.env          项目 dotenv
4. ~/.abx/.env     用户 dotenv
5. ~/.abx/config.toml
6. default         由提供方推导或内置
```

空白或只含空格的值在每一层都视为未设置（不会挡住下一层）。按顺序尝试各层。第一个设置了该键唯一变量的层决定结果。

### 4.2 一层内只有一个变量

为提供方 `P` 解析键 `K` 时，读取方只查找一个环境变量：

1. 插件自己的字段：`ABX_<P>_<K>`
2. 产品的核心设置：`ABX_<K>`
3. §3 把厂商变量指定为该键变量的情况（`ALICLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_REGION_ID`、`ACR_NAMESPACE`、`GITHUB_TOKEN` 等）

同一个键没有第二个变量。在 `config.toml` 中的顺序是 `[providers.<P>].<K>`，然后 `[transport].<K>`。

### 4.3 dotenv 先按层

`./.env` 和 `~/.abx/.env` 各自是一层。项目文件写了的键由项目文件决定。项目文件没有的键仍然来自 `~/.abx/.env`。

### 4.4 提供方选择优先级

```text
explicit provider= / --provider
  > ABX_PROVIDER（进程环境变量）
  > ./.env 中的 ABX_PROVIDER
  > ~/.abx/.env 中的 ABX_PROVIDER
  > ~/.abx/config.toml 的 [core] provider     （`abx provider default NAME`）
  > alicloud-express
```

CLI 对已有沙箱的操作还接受限定引用 `provider:sandbox_id`（§7.4），其优先级与显式选项同级。

### 4.5 推导默认值

提供方可以声明由其他键推导（数据，不是代码）：

```toml
[endpoint.derive]
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

只有当基础 URL 没有通过显式参数或进程环境变量给出时才推导。每个推导出的键按“设置默认值”语义应用，所以来自 `.env` / `config.toml` 的基础 URL / 域名会被保留，另一个仍由区域推导。当 URL 由参数 / 环境变量显式给出时域名不推导（保持提供方默认）。没有 `derive` 的提供方只使用静态默认值。

### 4.6 提供方作用域规则（凭证隔离）

* **只有当 `P` 是当前提供方时，作用域键才优先于通用键**：`providers.<P>.<key>` / `ABX_<P>_<KEY>` 优先于 `P` 被允许读取的核心键的通用名字。
* **凭证和端点绝不跨提供方。** 为提供方 `P` 解析时，永远不会查看 `Q ≠ P` 的 `ABX_<Q>_*` 或 `[providers.Q]`。
* **通用的凭证 / 端点键（`sandbox_api_key`、`sandbox_base_url`、`sandbox_domain`）属于内置提供方。** 没有这条规则，切换默认提供方会悄悄把阿里云密钥发给第三方插件。非内置提供方只有在 (a) 其清单在 `[core] inherit` 里列出它们，并且 (b) 用户在安装 / 更新时同意了，才会收到它们（回执记录同意的列表；同意界面会打印一行点名这些键的警告）。生效的列表是 `manifest.inherit ∩ receipt.consented.inherit`。参考的 `e2b-compatible` 提供方继承这三个键，因此 `ABX_SANDBOX_API_KEY` 和 `ABX_SANDBOX_BASE_URL` 只在这份有记录的同意之下才会交给它。
* 非密钥调优键（`http_timeout`、`http2`、`max_retries`、连接池 / WS / 退避）与所有提供方共享。
* LLM、GitHub 和 MCP 键不是提供方凭证，永远不会交给提供方。
* 插件自己的凭证是它声明的作用域字段（环境变量 `ABX_<P>_<KEY>`）。
* 插件的值只通过 `initialize` 请求进入插件进程，绝不通过环境变量（§8.3）。

---

## 5. 每个键一个环境变量

§3 的表就是全部。`explain_config()` 报告层和这一个变量名。密钥已脱敏。

`abx config set` 写入 §3.3 的存储名。没有第二个存储名，也没有把一个名字改写成另一个名字的命令。

---

## 6. 读取方接受什么

读取方接受 §3 中的变量以及对应的配置键。`load_config` 和 `TransportConfig` 使用 `sandbox_api_key`、`sandbox_base_url` 和 `sandbox_domain`。`abx config get|set` 使用这些键。

---

## 7. 提供方

### 7.1 标识

* 内置 id **`alicloud-express`**，显示名 **Alibaba Cloud Express Edition** / **阿里云极速版**。选择该 id 的理由：厂商前缀（`alicloud`，与 `ALICLOUD_*` 和 `alicloud` pip extra 一致）+ 版本（`express`，当前 API 实现的产品档位）。被否决的：`e2b`（是许多提供方都会说的*协议*）、`fc`（可能承载其他版本的产品族）、`aliyun` / `default`（不稳定："default"的含义会变；控制台品牌可能变化）、`alibaba`（太粗）。显示名可能变化；**id 永远不变**。
* id 语法：`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`，2–40 个字符，不含下划线（使 `-`→`_` 的环境变量映射是单射）。保留：`alicloud-express`、`default`、`all`、`none`、`builtin`、`shortcuts`、`core`、`transport`、`providers`、任何以 `abx-` 开头的、`e2b` 以及 `alicloud-`（为第一方版本保留）。
* 在用户运行 `abx provider default <id>` / 设置 `ABX_PROVIDER` 之前，默认**始终**是 `alicloud-express`。从不接触提供方的用户在任何输出里都看不到变化。

### 7.2 能力矩阵（特性标志）

提供方声明自己实现哪些**特性**。SDK / CLI 在调用前检查特性；不支持的特性抛出 `ProviderFeatureNotSupportedError`（`E8004`，现有 `CapabilityNotSupportedError` 的子类）——绝不是 `AttributeError` / HTTP 404。

| 特性 id | 含义 | Python SDK 接口 | 需要它的 CLI 命令 |
|---|---|---|---|
| `sandbox.lifecycle` | 创建 / 连接 / 列出 / 详情 / 销毁 | `Sandbox.create/connect/list/kill_by_id`、`info` | `create`、`list`、`info`、`kill`、`connect` |
| `sandbox.timeout` | 修改 TTL | `set_timeout`、`refresh` | `sandbox timeout` |
| `sandbox.pause` | 暂停 / 恢复 | `pause`、`resume` | `sandbox pause/resume` |
| `exec.run` | 运行命令，缓冲结果 | `commands.run` | `exec`、`run`、`shell` |
| `exec.stream` | 流式输出 | `commands.stream` | `shell-stream` |
| `process.manage` | 列出 / 终止 / 发信号 / 写 stdin | `commands.list/kill/send_*` | `sandbox process ...` |
| `pty` | 交互式终端 | `get_terminal` | `connect --pty` |
| `files.rw` | 读 / 写 / 列出 / stat / mkdir / 删除 / 移动 | `files.*` | `files`、`upload`、`download` |
| `files.watch` | 监听目录 | `files.watch` | — |
| `files.transfer` | 带签名的上传 / 下载 URL | `get_upload_url/get_download_url` | — |
| `code.interpret` | 有状态的代码上下文 | `run_code`、`code.*` | `sandbox code` |
| `templates.read` | 列出 / 查看模板 | `Template*` 读取 | `template list/info` |
| `templates.build` | 构建 / 部署 / 删除模板（镜像构建 + 注册） | —（仅 CLI） | `template build/deploy/delete`、`deploy`、`install` |
| `ports.url` | 端口的公网 URL | `network.get_url` | `sandbox system ports`、`url` |
| `ports.domain` | 沙箱 / 模板的自定义域名 | —（没有单沙箱 API） | — |
| `storage.mount` | 挂载对象存储（OSS） | —（没有单沙箱 API） | — |
| `network.vpc` | 接入 VPC | —（仅模板 `vpcConfig`） | `--vpc-id` 系列 |
| `sessions` | 沙箱标识在进程结束后仍存在（可按 id 重新连接） | `Sandbox.connect` + `LocalSessionStore` | `session ...` |

`alicloud-express` 实现全部特性。沙箱的能力仍是**模板的能力**（不变）；当提供方缺少某个能力标记背后的特性（`shell ← exec.run`、`files ← files.rw`、`code ← code.interpret`、`terminal ← pty`、`ports ← ports.url`）时，调用在调用时抛出 `E8004`。实现不会预先对两个集合求交集：模板是与提供方无关的数据，在调用处以精确的错误失败更简单，也不会与提供方的实际行为不一致。

### 7.3 取舍分析：插件如何加载？

要求：同一个插件应同时服务 **Python SDK 和 Node CLI**。

| 方案 | 一个插件服务两种语言 | 安装期风险 | 运行期隔离 | 流式 / 性能 | 工作量 | 结论 |
|---|---|---|---|---|---|---|
| **A. 各语言原生**（Python 入口点；npm 模块） | 否——每个提供方两份实现 | pip / npm 在安装时执行构建 / setup 代码 | 进程内：完全信任，可能让宿主崩溃 / 卡死 | 最好 | 每种语言较低 | **只作为 SDK 侧的高级路径保留**（`register_provider()`，入口点组 `agent_sandbox.providers`）；不能用 `abx provider install` 安装 |
| **B. 可执行程序 + stdio 上的 JSON-RPC（EPP/1）** | **是** | 无（只复制 + 校验；不运行任何东西） | 独立进程：崩溃 / 卡死 / 超时被隔离，环境被清理，以后可由 OS 沙箱包装 | 控制面良好；文件字节在 JSON 里是 base64（重数据请用 C） | 中（每种语言一个客户端） | **主要方案** |
| **C. 兼容 REST 的 `base_url`**（E2B 协议，声明式清单） | **是**，完全没有代码 | 无 | 无需隔离 | 原生速度（内置传输） | 最低 | **E2B 协议后端的主要方案** |
| D. localhost 上的 gRPC / HTTP 插件服务 | 是 | 无 | 进程级，但要处理端口分配、本地端口认证、防火墙提示 | 流式最好 | 高（代码生成、生命周期、端口） | v1 否决；EPP/2 可能作为备选传输加入 |
| E. WASM 组件 | 是 | 无 | 强 | 目前 I/O 方案有限 | 非常高 | v1 否决 |

**决定：B + C，外加 A 作为仅限 SDK 的逃生口。** B 和 C 都用*清单*（`abx-provider.toml`）描述插件；清单的 `runtime.kind` 为 `rest`（C）或 `exec`（B）。新后端的推荐架构是：*实现 E2B envd 数据面协议*（或复用它），并只为**控制面**（创建 / 连接 / 列出 / 销毁，返回 `envd_url` + token）提供一个 `exec` 插件——数据面（exec、文件、PTY、代码）随后经 SDK 和 CLI 里快速的原生传输流动。没有 envd 兼容性的后端也在插件里实现数据面方法（`exec.run`、`files.*`），接受 base64 的开销。

### 7.4 提供方契约

**Python SDK 接口**（`agent_sandbox.providers.base`）：

```python
class Provider(ABC):
    id: str
    display_name: str               # "Alibaba Cloud Express Edition"
    display_name_zh: str            # "阿里云极速版"
    version: str
    features: frozenset[ProviderFeature]
    config_fields: tuple[ConfigField, ...]   # 提供方作用域的 schema
    uses_core: frozenset[str]                # 它使用的核心键
    kind: Literal["builtin", "rest", "exec", "python"]

    def require(self, feature: ProviderFeature) -> None: ...   # 抛 ProviderFeatureNotSupportedError
    async def build_infra(self, config: TransportConfig) -> ProviderInfra: ...
```

`ProviderInfra` 携带 `Sandbox` 需要的东西：`config`、`auth`、`http_client`（非 HTTP 提供方可为 `None`）以及四个协议对象（`sandbox_protocol`、`process_protocol`、`filesystem_protocol`、`code_interpreter_protocol`）。对 HTTP / envd 提供方，它们是现有的类；对 `exec` 提供方，它们是在 EPP 调用之上实现相同方法的薄适配器。`Sandbox` 的构造函数本来就接受这些协议对象，因此 `Sandbox` 内部不需要改动。

**Node CLI 接口**（规格在 CLI 文档）：相同形状的 TypeScript 接口（`id`、`displayName`、`features: Set<ProviderFeature>`、`configFields`、`usesCore`、`buildInfra(config)`），线上字段保持 `snake_case`。

**线协议 EPP/1** —— JSON-RPC 2.0，在插件的 stdin / stdout 上以换行分隔的 UTF-8 JSON；stderr 是自由格式的日志文本（被捕获，`--verbose` 时显示，并附加到崩溃错误里）。每行一对请求 / 响应，不支持批量，单行最大 8 MiB（`max_message_bytes`）。宿主发请求；插件只能发*通知*（`log`、`progress`、`exec.output`、`exec.exit`、`pty.output`）。未知方法 → `-32601`；双方都必须忽略未知字段。

<a id="epp-methods"></a>

下表是规范性的，同时作为 `client-sdk/tests/fixtures/epp-methods.json` 发布（逐字节镜像到 `cli/docs/design/fixtures/`）：每个方法的特性、是 `required`（必需）、`optional`（可选）还是 `extension`（扩展）、宿主是否重试，以及每个参数的名称、类型和是否必须出现。有一个测试会让每个宿主适配器通过记录型客户端运行，当适配器发送了表中没有的参数、遗漏了表中标为必需的参数、或从未调用表中说宿主会调用的方法时测试失败。**支持**列：**R** = 对其特性是必需的，**O** = 可选（宿主会回退），**X** = 扩展（插件可以提供；宿主暂不调用）。

| 方法 | 参数（snake_case；`?` = 可选） | 结果 | 特性 | 支持 |
|---|---|---|---|---|
| `initialize` | `{protocol:"epp/1", host:{name,version}, provider_id, config:{…已声明字段}, core:{…已声明核心键}, locale, data_dir}` | `{protocol, plugin:{name,version}, features:[…]}` | — | R |
| `shutdown` | `{}` | `{}` | — | R |
| `sandbox.create` | `{template, timeout, metadata, envs, cpu, memory, disk, gpu, request_timeout, secure?, options?}` | `SandboxRecord` | `sandbox.lifecycle` | R |
| `sandbox.get` | `{sandbox_id}` | `SandboxRecord` | `sandbox.lifecycle` | R |
| `sandbox.connect` | `{sandbox_id}` | `SandboxRecord` | `sandbox.lifecycle` | O（可以恢复；回答 `-32601` 时宿主改调 `sandbox.get`） |
| `sandbox.list` | `{limit, status?, cursor?, metadata?}` | `{sandboxes:[SandboxRecord], next?}` | `sandbox.lifecycle` | R |
| `sandbox.kill` | `{sandbox_id}` | `{}` | `sandbox.lifecycle` | R |
| `sandbox.set_timeout` | `{sandbox_id, timeout}` | `{}` | `sandbox.timeout` | R |
| `sandbox.pause` / `sandbox.resume` | `{sandbox_id}` | `{}` | `sandbox.pause` | R |
| `exec.run` | `{sandbox_id, cmd, args, env, cwd, user, timeout, stdin?}` | `{exit_code, stdout, stderr, stdout_b64?, stderr_b64?}` | `exec.run` | R |
| `exec.start` | 同 `exec.run`，另加 `detached?` | `{process_id: string}`，随后是通知 `exec.output{process_id, stream, data}` 和恰好一个 `exec.exit{process_id, exit_code}` | `exec.stream` | R（`detached`：X） |
| `process.list` | `{sandbox_id}` | `{processes:[{pid, command, status, …}]}` | `process.manage` | R |
| `process.kill` / `process.signal` / `process.stdin` | `{sandbox_id, pid, signal? \| data?}` | `{}` | `process.manage` | R（`stdin` 可以回答 `-32003`） |
| `files.read` | `{sandbox_id, path, offset?, length?}` | `{content_b64, size}` | `files.rw` | R（`offset`/`length`：X） |
| `files.write` | `{sandbox_id, path, content_b64, mode?, append?}` | `{}` | `files.rw` | R（`mode`/`append`：X） |
| `files.list` | `{sandbox_id, path}` | `{entries:[{name,path,type,size,mtime?}]}` | `files.rw` | R |
| `files.stat` | `{sandbox_id, path}` | `{name,path,type,size,mtime?}` | `files.rw` | R |
| `files.mkdir` / `files.remove` | `{sandbox_id, path}` | `{}` | `files.rw` | R |
| `files.move` | `{sandbox_id, source, destination, overwrite?}`（插件也可接受 `src`/`dest`） | `{}` | `files.rw` | R |
| `files.search` / `files.chmod` | `{sandbox_id, path, pattern \| mode}` | `{entries}` / `{}` | `files.rw` | X |
| `ports.url` | `{sandbox_id, port}` | `{url, headers?}` | `ports.url` | R（SDK 在 `network.resolve()` 中调用） |
| `templates.list/get/delete/build/build_status` | | | `templates.read` / `templates.build` | R |
| `pty.open/write/resize/close` | | 通知 `pty.output` | `pty` | R |

参数约定：`secure` **仅**在调用者给 `Sandbox.create` 传了 `secure=True/False` 时发送（否则缺失，由插件自己的默认值决定；内置提供方按 `secure=True` 处理）。`options` 是调用者的 `provider_options`（仅已声明的配置字段）**去掉密钥字段**，用于每次创建的设置（网络策略、平台、镜像拉取设置）；插件必须对每次创建接受的键做白名单，并且绝不能让 `options` 改变服务地址或凭证。`process_id`（来自 `exec.start`）是**字符串**；`process.*` 的 `pid` 是不透明的 `string | integer`：`process.list` 条目的整数 `pid` 或某个 `process_id`，SDK 的 `ProcessInfo.pid` 以及 `commands.kill/send_signal/send_input` 两者都接受。`sandbox.get` 是唯一必需的查询；`sandbox.connect` 用于“连接”含义更多（恢复）的插件。双方都必须忽略未知参数。

`SandboxRecord` = `{sandbox_id, template, status("creating"|"running"|"paused"|"stopping"|"stopped"|"error"), region?, created_at?, expires_at?, metadata{}, envd_url?, envd_access_token?, url?}`（status 取值就是 SDK 的 `SandboxStatus`）。

约定：线上所有时长都是**秒**（`timeout`、`request_timeout`），`*_ms` 只出现在清单里；`sandbox.list` 接受不透明的 `cursor` 并返回 `next`（缺失 = 最后一页）；`exec.run` 在 `stdout` / `stderr` 里返回文本（非法 UTF-8 被替换），并可附加 `stdout_b64` / `stderr_b64` 表示精确字节；对 `exec.start`，插件按顺序发送一个进程的所有 `exec.output` 通知，最后恰好发一个 `exec.exit`；宿主只重试**幂等**方法（`sandbox.get/list/kill/connect`、`files.read/stat/list`、`ports.url`），且只在被标记为 `retryable` 的错误上重试；`sandbox.create`、`exec.*`、`files.write` 宿主从不重试。用 `$/cancel {id}` 取消的请求（宿主在超时或调用者离开时发送）告诉插件停止工作，例如杀掉为该 `exec.start` 派生的进程；它仍应应答。清单里配置字段的默认值会**随** `initialize.config` 送达，所以不要给带有替代项的字段（`base_url` 与 `domain`）设置默认值：默认值总会胜出。`data.sdk_code` 为 `-32001/-32002/-32000` 选择 SDK 异常类（例如 `E1001`、`E2000`、`E2001`、`E3001`、`E4001`；完整表是 `providers/epp.py` 里的 `_SDK_CODE_CLASSES`）；缺失**文件**时单独的 `-32002` 会变成 E8005（沙箱未找到），所以文件错误应带上 `sdk_code: "E4001"`。当存在 `envd_url` 时，宿主直接用原生 envd 传输与之通信（上面说的**混合**模型）；否则使用数据面方法。

对没有 envd 的提供方，宿主把沙箱的 envd URL 设为标记 URL `epp://<provider>/<sandbox_id>`；所有会调用 envd 的代码路径（命令列表、认证检查、终端）都必须跳过 `epp://` URL，改用提供方的数据面方法。

错误：JSON-RPC `error = {code, message, data:{sdk_code?, suggestion?, retryable?, details?}}`。

| EPP 错误码 | 含义 | 宿主异常 | CLI 退出码 |
|---|---|---|---|
| `-32001` | 未认证 / 凭证错误 | `AuthenticationError`（E1xxx；`data.sdk_code` 选择子类） | 3 |
| `-32002` | 未找到（沙箱、模板、文件） | `data.sdk_code` 指定的类（E2001、E4001…）；默认 `ProviderResourceNotFoundError` E8005 | 4 |
| `-32003` | 特性不支持 | `ProviderFeatureNotSupportedError` E8004 | 1 |
| `-32004` | 超出配额 | `QuotaExceededError` E2002 | 6 |
| `-32005` | 超时 | `CommandTimeoutError` / `ProviderTimeoutError` E8022 | 5 |
| `-32006` | 参数 / 配置无效 | `ProviderConfigError` E8002 | 2 |
| `-32000` | 其他提供方失败 | 带 `sdk_code` 的 `SandboxError` 或 E8000 | 1 |
| `-32600…-32603`、`-32700` | JSON-RPC 标准 | `ProviderProtocolError` E8020 | 1 |

因为宿主把插件错误映射回现有的层级和退出码，所以 CLI 确定的退出码（0–6）对每个提供方都成立。

插件进程的生命周期：首次使用时惰性启动，每个提供方会话一个进程（一次 SDK `Sandbox` 操作作用域 / 一次 CLI 调用），`initialize` 须在 `startup_timeout`（默认 10 秒）内完成，调用受 `call_timeout`（默认 60 秒，可由 `timeout` 按调用覆盖）限制，通过通知 `$/cancel {id}` 取消，`shutdown` 后关闭 stdin，3 秒后 SIGTERM，再过 3 秒 SIGKILL（进程组 / Windows Job Object）。宿主从不跨 CLI 调用复用进程（状态是提供方自己的责任），这使插件的编写天然无状态且崩溃安全。

**REST 类型的限制。** `rest` 提供方就是 E2B 协议加上不同的端点和 bearer / `X-API-Key` 密钥。需要请求签名（AK/SK）、OAuth 或非 E2B API 的提供方必须是 `exec`。

**版本协商。** `epp/1`；向后兼容的新增只提升清单的 `protocol_minor` 提示。宿主拒绝其 `protocol` 不被支持的清单（`E8013`）。`requires_abx`（见下）限制 SDK / CLI 的版本。

### 7.5 清单：`abx-provider.toml`

使用 TOML（`tomllib` / `tomli` 和 `smol-toml` 都已是依赖；允许注释；YAML 会增加 Python 依赖）。

```toml
manifest_version = 1

[provider]
id          = "local-process"
name        = "Local Process"
name_zh     = "本地进程"
version     = "0.1.0"
description = "Runs commands directly in a temp directory on this machine (demo, no isolation)."
license     = "Apache-2.0"
homepage    = "https://example.com/local-process"

[compat]
protocol    = "epp/1"                     # 或 kind = "rest" 时为 "e2b-rest/1"
requires    = { sdk = ">=0.3,<1", cli = ">=0.3,<1" }   # 比较符：>= <= > < == != ~=，逗号 = AND

[runtime]
kind    = "exec"                          # exec | rest
command = ["python3", "./provider.py"]    # argv，绝不是 shell 字符串；"./x" 在插件目录内解析
startup_timeout_ms = 10000
call_timeout_ms    = 60000
platforms = ["linux", "darwin", "win32"]  # 可选

[features]
supported = ["sandbox.lifecycle", "exec.run", "files.rw"]

[security]                                # 声明性的，安装和更新时展示，并哈希进同意记录
network      = []                         # 插件打算联系的主机（"*" = 任意）
filesystem   = ["data_dir"]               # "data_dir" | "cwd" | "home" | "any"
env_passthrough = []                      # 额外转发给进程的环境变量名
spawns_processes = true

[core]
inherit = []                              # sandbox_api_key | sandbox_base_url | sandbox_domain 的子集（需主动申请，同意时展示，见 §4.6）

[auth]                                    # 可选：哪些凭证组合能让提供方可用
any_of = [["api_key"]]                    # [[a, b], [c]] = (a AND b) OR c；驱动 `provider doctor` / "缺少凭证"错误

[config.fields.workdir_root]              # 提供方作用域的 schema -> `abx provider config`、校验、环境变量名
type = "path"                             # string | int | float | bool | enum | path | url | csv
required = false
secret = false
credential = false                        # true：缺失 -> E1003（退出码 3）而不是 E8002
default = ""
description = "Directory that holds sandbox working dirs"
description_zh = "沙箱工作目录的根目录"
env = ["LOCAL_PROCESS_ROOT"]              # 可选：该插件自己字段的额外（native）环境变量名；规范名 ABX_LOCAL_PROCESS_WORKDIR_ROOT 自动存在。以 ABX_、E2B_、ALICLOUD_ 开头的名字会被拒绝。
```

`kind = "rest"` 用下面的内容替换 `[runtime] command`：

```toml
[runtime]
kind = "rest"
[endpoint]
base_url = "https://sandbox.example.com"
domain   = "sandbox.example.com"
auth     = { scheme = "bearer" }          # bearer | header（header = "X-API-Key"）
[endpoint.derive]                          # 可选
sandbox_base_url = "https://api.{region}.example.com"
```

**校验规则（两种语言相同）**：`manifest_version == 1`；id 语法和保留 id；`command` 是不含 NUL 的非空字符串数组；以 `./` 或 `../` 开头的可执行路径必须解析到插件目录**内部**（不能逃逸）；`.bat` / `.cmd` / `.ps1` 启动器被拒绝（它们需要 shell；Node 不带 shell 拒绝启动它们）——Windows 插件使用 `.exe` 或解释器 + 脚本；`env_passthrough` 不得包含 `ABX_*`、`E2B_*`、`ALICLOUD_*`；`core.inherit` ⊆ {`sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`}；`[auth] any_of` 只引用已声明的字段；字段键匹配 `^[a-z][a-z0-9_]*$`，绝不与核心键或 `shortcuts*` 冲突；`type` 已知；密钥不需要 `default`；`features.supported` ⊆ 特性注册表；未知的顶层表被忽略（向前兼容）；文件大小 ≤ 256 KiB。

### 7.6 存储布局、安装、信任

```text
~/.abx/providers/
  .lock                       # 安装 / 更新 / 卸载用的 O_EXCL 锁
  .staging/                   # 安装在这里组装，然后原子重命名
  .trash/                     # 旧版本保留到交换成功
  <id>/
    abx-provider.toml
    ... 插件文件 ...
    .abx-install.json         # 回执（见下）
    data/                     # 保留给插件自己的状态；不参与摘要，更新时保留
```

目录本身就是事实来源；没有会漂移的单独索引。默认提供方保存在 `config.toml` 的 `[core] provider`。

回执 `.abx-install.json`：

```json
{
  "receipt_version": 1,
  "id": "local-process", "version": "0.1.0",
  "source": {"type": "git", "url": "https://example.com/org/repo.git", "ref": "v0.1.0",
             "commit": "<40-hex>", "subdir": "providers/local-process"},
  "tree_sha256": "<hex>", "manifest_sha256": "<hex>",
  "trust": "pinned",                        // pinned | local | link | unpinned
  "consented": {"runtime": ["python3","./provider.py"], "security": {...}, "features": [...]},
  "installed_at": "2026-10-12T06:00:00Z", "installed_by": {"name": "abx-cli", "version": "0.3.0"}
}
```

**目录树摘要（Python 和 Node 相同）。** `tree_sha256 = SHA-256( 对每个普通文件，按 UTF-8 路径字节排序：path + "\0" + ("x" 若可执行否则 "-") + "\0" + SHA-256(文件字节) + "\n" )`，路径是相对插件根目录的 POSIX 风格，排除 `.git/`、`.abx-install.json` 以及顶层 `data/`。其余所有内容都会计入摘要，包括插件的 `tests/` 目录（它会被安装并改变摘要；请安装 `--subdir` 或保持测试很小）。安装时拒绝符号链接（§8）。两种实现都用同一组向量测试。

**安装算法**（`abx provider install <source>`）：

1. 对 `<source>` 分类：存在的目录 → `local`；`--link` → `link`（指向该目录的符号链接，仅开发用）；git URL → `git`（`https://…`、`ssh://…`、`git@host:path`，可带 `git+` 前缀；`file://`、`ext::`、`git://` 和 `http://` 会被**拒绝**，除非 `--allow-insecure-transport`；带内嵌凭证的 URL 被拒绝——请使用凭证助手 / SSH agent）。
2. 暂存：local → 按 §8.2 的安全规则复制；git → 获取但**不检出**，验证后由安装器自己写入文件（见 §8.2），仅复制被跟踪的文件。把 ref 解析为完整的提交 SHA。
3. 解析并校验清单（§7.5）。计算 `tree_sha256`、`manifest_sha256`。
4. 如果给出 `--sha256 DIGEST`，必须等于 `tree_sha256`（否则 `E8011`）→ 信任级别 `pinned`。`--ref` 是完整 40 位十六进制提交的 git 来源是 `pinned`；标签 / 分支是 `unpinned`，在非交互模式下被拒绝，除非 `--allow-unpinned`。
5. **同意**：打印 id、名称、版本、来源、提交、摘要、运行命令、声明的安全块、特性和配置字段（密钥有标记）。交互式：`Install and trust this provider? [y/N]`。非交互 / CI：需要 `--yes`，否则以 2 退出（`E8012`）。
6. 在锁保护下原子交换到 `<id>/`；写入回执。**不会执行插件中的任何东西。** 第一次执行发生在某个命令使用它时（或 `abx provider doctor`）。

**运行期检查**（每次启动 `exec` 提供方）：回执存在；目录的 `tree_sha256` 与回执一致（不一致时 `E8011`，信息 `provider files changed since install; reinstall or run 'abx provider update <id>'`）——仅对信任级别 `link` / `local-dev` 跳过，它们在 stderr 打印一行 `warning: provider <id> is a linked development install`；`requires` 满足（`E8013`）。

**更新**（`abx provider update [<id>|--all] [--ref R] [--check] [--yes] [--allow-unpinned] [--allow-insecure-transport] [--no-verify]`）：从记录的来源重新获取，展示差异摘要（版本、提交范围、变化的运行命令 / 安全 / 特性 / 配置字段）；**只要运行命令、安全块或特性列表变化就需要重新同意**，否则 `--yes` 即可；已固定的安装只有在显式 `--ref` 时才移动；旧版本留在 `.trash/` 里，直到新版本通过 `initialize`；失败时旧文件**及 `data/`** 会被原样恢复。回执不记录 `--allow-insecure-transport`：`file://`/`http://`/`git://` 来源每次更新都需要该参数（再次确认这个刻意的举动）。`--check` 打印可用更新，不改动任何东西。

**卸载**（`abx provider uninstall <id> [--purge] [--yes]`）：删除目录。如果它是默认提供方，默认值回退到 `alicloud-express` 并打印提示。已保存的值（`[providers.<id>]`、`~/.abx/.env` 中的 `ABX_<ID>_*`）保留，除非 `--purge`。

### 7.7 多提供方规则

* 每个命令的解析：§4.4。一个命令只与**一个**提供方通信。
* 沙箱 id 是提供方本地的。CLI 有两种输出格式：**旧格式**（裸 id，没有 `provider` 字段——与今天逐字节相同）当且仅当*环境*提供方（§4.4 去掉显式选项：`ABX_PROVIDER` → `./.env` → `~/.abx/.env` → 配置 → 内置）**和**生效提供方（显式选项或环境提供方）都是 `alicloud-express` 时使用。其他任何情况 CLI 使用**限定格式**：id 打印为 `provider:sandbox_id`（如 `local-process:sbx-1`、`alicloud-express:sbx-9`），`--json` 的行增加 `"provider": "<id>"`，同时 id 字段保持裸 id。理由：恰好在有多个提供方时，不带限定的 id 是有歧义的，而稍后键入的裸 id 会针对环境提供方解析，它可能在 id 被打印之后已经变了。输入始终接受任何提供方的限定形式。裸 id 针对生效提供方解析（§4.4）。
* 如果显式的 `--provider P` 与限定引用 `Q:id` 冲突，命令以 2 退出（`E8030 ProviderMismatchError`）。
* `abx list --all-providers` 列出每个*已配置*（具有所需凭证）的提供方，并增加 `PROVIDER` 列 / `provider` 键；失败的提供方作为警告报告并跳过（至少一个成功则退出 0）。
* 模板目录按提供方划分；`template build/deploy/install` 需要 `templates.build`；没有它的提供方在任何 Docker 工作开始前就以 `E8004` 快速失败。
* 每个提供方的凭证相互隔离（§4.6）。`abx provider config <id> list` 只显示该提供方的作用域键以及它使用的核心键。

### 7.8 SDK 用法

```python
sb = await Sandbox.create(template="base")                              # 不变：alicloud-express
sb = await Sandbox.create(template="base", provider="local-process")    # 显式
sb = await Sandbox.create(provider="my-cloud", provider_options={"cluster": "prod"})
sb.provider  # "my-cloud"
sb = await Sandbox.create(provider=my_provider_instance)               # 也接受 Provider 对象（测试、编程方式）
sb = await Sandbox.create(provider="my-cloud", secure=False)           # 只因传了才会发给插件
url, headers = await sb.network.resolve(8080)                          # 声明了 ports.url 时询问插件
```

`provider_options` 既用于配置提供方，对 `exec` 插件还会（去掉密钥字段后）作为 `sandbox.create` 里的 `options` 送达；`secure` 默认为 `None`，此时不发送（内置提供方把 `None` 当作 `True`）。`Sandbox.network.get_url(port)` 仍是同步的本地计算；`resolve()`/`resolve_url()` 是感知提供方的形式。`ProcessInfo.pid` 和 `commands.kill(pid)` 接受 `int | str`。

`LocalSessionStore` 会话会记住提供方。**已规划、尚未实现**：`sandbox.yaml` 的 `provider:` / `provider_options:` 和 `@sandbox(provider=...)`（声明式层由另一个工作流负责；记录在后续事项中）。

`ABX_PROVIDER`、`./.env`、`~/.abx/.env` 和 `[core] provider` 按 §4.4 生效。`agent_sandbox.providers` 导出 `Provider`、`ProviderFeature`、`ConfigField`、`register_provider`、`get_provider`、`list_providers`、`resolve_provider_id`，以及安装 / 存储 API。`python -m agent_sandbox.providers {list,info,install,uninstall,update,default,test,doctor}` 为只用 SDK 的用户镜像 CLI（相同布局、相同回执、相同摘要）。

---

## 8. 安全模型

### 8.1 威胁模型

`exec` 插件是**以你的用户权限、拿着你为该提供方配置的凭证运行的第三方代码**。安装它是一个信任决定，与 `pip install` 一个你随后会运行的工具完全一样。我们无法以可移植的方式把它沙箱化。因此设计集中于：(1) 安装时不运行任何东西，(2) 精确知道装了什么（固定 + 摘要 + 同意记录），(3) 检测后续篡改，(4) 最小化进程收到的东西，(5) 控制崩溃和卡死，(6) 拒绝危险的安装输入。

### 8.2 安装期加固

* **不自动执行，不检出。** 不运行 `setup.py` / `postinstall` / Makefile / 钩子。Git 来源用 `git clone --depth 1 --no-checkout --filter=blob:limit=10m --no-recurse-submodules` 获取，然后**用 `git ls-tree -r -z -l <commit>` 枚举树，并在写任何文件之前校验**（只允许模式 `100644` / `100755` 的 blob；符号链接 `120000`、子模块 `160000` 和其他一切都被拒绝；检查大小和数量），blob 用 `git cat-file --batch` 读取并由安装器自己写入。因此没有 `git checkout`，也就没有 smudge / clean 过滤器、`.gitattributes` 驱动、`core.autocrlf` 改写、钩子，或大小写不敏感文件系统上的覆盖。Git 以 `-c core.hooksPath=<空目录> -c core.fsmonitor=false -c protocol.file.allow=never -c protocol.ext.allow=never -c http.followRedirects=false`、`GIT_TERMINAL_PROMPT=0`、`GIT_ALLOW_PROTOCOL=https:ssh`、`GIT_CONFIG_NOSYSTEM=1`、指向空文件的 `GIT_CONFIG_GLOBAL`（这样用户 git 配置里的 `url.<x>.insteadOf` 改写和凭证助手就无法重定向或泄露）、清理过的环境（没有 `GIT_SSH_COMMAND`、`GIT_ASKPASS`、`GIT_EXEC_PATH`）和超时运行。已文档化的后果：需要 git 凭证助手的私有 HTTPS 仓库，请自己克隆后安装该目录；SSH 来源照常使用 SSH agent。重定向到其他主机会被拒绝。
* **固定**：解析出的提交 SHA 和目录树摘要总是被存储，此后安装的内容不可变（每次启动都检查摘要）。`trust` 记录用户如何审查来源：`--ref <40-hex>` 或 `--sha256` ⇒ `pinned`；标签 / 分支 ⇒ `unpinned`（ref 在审查和安装之间可能已经移动；同意界面显示解析出的提交和摘要，便于带外验证）。无人值守（非交互）运行拒绝 `unpinned`，除非 `--allow-unpinned`。`update` 永远不会改变记录的来源 URL。
* **文件系统安全**：条目必须是普通文件或目录；符号链接、硬链接、设备、FIFO 被拒绝；路径被规范化且必须停留在插件根目录内（`..`、绝对路径、盘符和 NUL 被拒绝，大小写折叠冲突被拒绝）；限制：≤ 2000 个文件、总计 ≤ 50 MiB、单文件 ≤ 10 MiB；清单 ≤ 256 KiB；目录权限 0700，文件 0600（仅在来源有 +x 时才加 +x）。
* **URL 中的凭证**被拒绝，并在回执 / 日志中被**遮蔽**。
* **名字安全**：id 语法和保留 id；已安装的 id 需要 `--force`（此时就是一次更新）；插件不能替换内置或第一方 id。
* **`--link`**（开发用的符号链接安装，不复制，没有完整性检查）需要交互确认或 `--yes`，记录为信任级别 `link`，每次使用都向 stderr 打印 `warning: provider <id> is a linked development install`。
* **Windows**：替换其插件进程正在运行的提供方目录会以 `E8010` 失败（`provider 'x' is in use`）；交换会在 1 秒后重试一次。

### 8.3 运行期加固

* **环境清理**：进程环境是 `PATH`、`HOME`/`USERPROFILE`、`TMPDIR`/`TEMP`、`LANG`/`LC_*`、`SYSTEMROOT`/`ComSpec`（Windows）、清单的 `env_passthrough`、`ABX_PROVIDER_DATA_DIR`，以及 `PYTHONDONTWRITEBYTECODE=1`（解释器不能往受摘要校验的插件目录里写 `__pycache__`）。**不会**隐式泄入 `ABX_*`、`E2B_*`、`ALICLOUD_*`、`GITHUB_TOKEN`、`OPENAI_*` 等。
* **凭证传递**：值只在 `initialize` 请求里发送，并且只发送清单声明的字段（`config.fields` 和 `core.uses`）。密钥绝不出现在 argv 或环境变量里。
* `cwd` 是提供方的数据目录（`~/.abx/providers/<id>/data/`，以 0700 创建），绝不是用户的项目。
* 输出上限：每条协议行 8 MiB，捕获的 stderr 环形缓冲 64 KiB；超过上限或违反分帧的进程会被终止（`E8020`）。带未知 / 重复 id 的响应被忽略；插件提供的文本（消息、stderr 末尾、建议）在打印前会去掉控制字符 / ANSI 转义，宿主在 `initialize` 里发送的每个值都会（精确匹配）从捕获的 stderr 和错误信息中被遮蔽。`initialize` 的参数从不被记录，即使 `--verbose` 也不记录。
* 卡死时的超时和进程组终止（Windows Job Object）（`E8022`）；插件退出后（无论是否正常）宿主仍会终止进程组，所以孙进程不能活过一次会话。
* 可选的 OS 约束（bwrap / sandbox-exec / Job 限制）在用户配置里保留为 `security.sandbox = "auto|off|require"`；v1 **未实现**，文档不得声称有隔离。
* **通用键泄露防护**：§4.6 —— 非内置提供方只能通过已同意的 `core.inherit` 收到 `sandbox_api_key` / `sandbox_base_url` / `sandbox_domain`；`abx provider doctor` 打印生效的 inherit 列表，并在被继承的通用键同时也是另一个已配置提供方的生效键时发出警告。
* **解释器 / 依赖卫生**：安装器从不运行 `pip` / `npm`；插件作者自己 vendoring 依赖。`cwd` 是（空的、0700 的）数据目录，所以不会从工作目录里拾取可执行文件。

### 8.4 篡改检测与更新

每次启动都校验摘要（代价 O(插件大小)，大小限制保证插件很小）；对与风险相关的差异，更新需要重新同意；`.trash` 回滚；`abx provider info` 显示提交、摘要、信任级别和同意记录。

### 8.5 这些保证不包括什么

* 同一用户的文件访问：恶意插件可以读取 `~/.abx/.env`。缓解措施是同意、固定、篡改检测和声明权限的记录；真正的隔离需要 OS 钥匙串 + 约束（未来工作）。
* `security` 块（`network`、`filesystem`）是**建议性的**：展示给用户并记录，v1 不强制执行。
* 回执和摘要能检测意外或第三方的修改；以同一用户运行的恶意进程可以同时改写两者。签名回执 / 证明（Sigstore 风格）是未来工作。

---

## 9. 错误码

新类别 **E8xxx —— 提供方错误**（都继承 `SandboxError`；见 `reference/error-codes.md`）：

| 错误码 | 类 | 含义 | CLI 退出码 |
|---|---|---|---|
| E8000 | `ProviderError` | 基类 | 1 |
| E8001 | `ProviderNotFoundError` | id 未知 / 未安装 | 4 |
| E8002 | `ProviderConfigError` | 未知 / 无效的提供方选项，schema 违规 | 2 |
| E8003 | `ProviderConflictError` | id 重复或被保留 | 1 |
| E8004 | `ProviderFeatureNotSupportedError`（同时是 `CapabilityNotSupportedError`） | 提供方缺少该特性 | 1 |
| E8005 | `ProviderResourceNotFoundError` | 插件报告沙箱 / 文件 / 模板未找到（`-32002` 且没有更具体的 `sdk_code`） | 4 |
| E8010 | `ProviderInstallError` | 来源不可达、大小 / 路径限制 | 1 |
| E8011 | `ProviderIntegrityError` | 摘要 / 固定不匹配，安装后文件被改动 | 1 |
| E8012 | `ProviderTrustError` | 未满足同意 / 固定 / 传输策略 | 2 |
| E8013 | `ProviderVersionError` | `requires` 或协议不被支持 | 1 |
| E8014 | `ProviderManifestError` | 清单无效 | 1 |
| E8020 | `ProviderProtocolError` | JSON-RPC 格式错误，握手失败 | 1 |
| E8021 | `ProviderProcessError` | 启动失败 / 崩溃（附 stderr 末尾） | 1 |
| E8022 | `ProviderTimeoutError` | 启动或调用超时 | 5 |
| E8030 | `ProviderMismatchError` | 沙箱属于另一个提供方 | 2 |

缺少*凭证*字段（`credential = true`）时抛出已有的 `InvalidCredentialsError`（E1003，退出码 3），并点名提供方键及其所有环境变量名。

---

## 10. 测试策略

1. **键注册表**：表驱动测试断言 §3 的每一行（这一个环境变量在每一层解析为该键，覆盖 `load_config`、`explain_config`、`http_timeout_configured`）。
2. **与语言无关的解析向量**（`client-sdk/tests/fixtures/config-resolution-vectors.json`，镜像到 `cli/docs/design/fixtures/`）：每个向量是 `{sources:{overrides, environ, dotenv:[{…},{…}], toml}, provider, expect:{key:{value, source, name}}}`。Python 测试针对 Python 解析器运行；CLI 工作者针对 Node 解析器运行同一个文件。当两个仓库同时存在时，一个测试断言两份拷贝相同。
3. **构造函数套件**：测试固定 `TransportConfig(sandbox_api_key=…)`、`load_config(sandbox_base_url=…)` 和 `Sandbox.create(sandbox_api_key=…)` 在默认提供方路径上的行为。
4. **清单**：有效 / 无效清单（每条校验规则）、版本比较器、id 语法、保留 id。
5. **存储 / 安装器**：本地目录、git（仅在测试中用带不安全标志的 `file://` 本地裸仓库）、已固定 / 未固定、符号链接 / 路径穿越 / 大小限制拒绝、URL 凭证拒绝、目录树摘要向量（与 Node 共享）、篡改后的完整性失败、重新同意的更新、回滚、卸载 / purge、默认提供方回退、并发锁行为、安装时不执行任何代码（一个 `provider.py` 会写金丝雀文件的插件证明这一点）。
6. **EPP 客户端**对参考插件：握手、版本不匹配、特性门控、错误映射表、超时、崩溃、格式错误的行、超长的行、stderr 捕获、环境清理（插件回显它的环境）、进程组终止、取消。
7. **Sandbox 集成**：`Sandbox.create(provider="local-process")` → `commands.run`、`files.write/read/list/exists/remove`、`kill`、`connect`；不支持的特性 → `E8004`；默认路径不受影响。
8. **契约测试**：`providers/testing.py` 提供可复用的 `ProviderContractTests` 基类（18 个测试：声明、生命周期、幂等 kill、`set_timeout`、暂停 / 恢复、exec 退出码 / stderr / 环境变量、流顺序与单个 exit、超时强制执行、进程列表、文件文本 / 二进制 / 目录 / 移动 / 缺失 → 类型化未找到、`ports.url`、未声明特性 → E8004、密钥脱敏）。运行方式：`python -m agent_sandbox.providers test <id> [--option K=V]`（什么都没收集到时失败）、`pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract --provider-under-test <id>`，或写子类。未声明特性的测试期望 E8004；已声明的必须可用。
8a. **方法表**：`epp-methods.json`（见上）会与宿主适配器双向核对，并有记录型客户端测试固定参数名 / 类型（`files.move` 是 `source`/`destination`，`process_id` 是字符串，`pid` 是 `string|integer`，`secure` 仅在设置时发送，`options` 不含密钥）。
9. **参考插件**（`examples/providers/`）：`e2b-compatible`（`rest` 类型，只有清单）和 `local-process`（`exec` 类型，Python 标准库，约 200 行：生命周期、exec、文件）。供测试使用，也是作者的模板。Node CLI 测试使用相同的目录。

---

## 11. 实现映射（Python SDK）

| 部分 | 模块 |
|---|---|
| 键注册表、解析器、schema 导出 | `agent_sandbox/utils/config_keys.py` |
| `TransportConfig`、`load_config`、`explain_config` | `agent_sandbox/transport/config.py` |
| 提供方接口、特性、注册表 | `agent_sandbox/providers/{base,registry}.py` |
| 内置提供方 | `agent_sandbox/providers/builtin.py` |
| 清单 + 版本比较器 | `agent_sandbox/providers/manifest.py` |
| 存储、安装器、摘要 | `agent_sandbox/providers/{store,installer}.py` |
| EPP 客户端 + 适配器 | `agent_sandbox/providers/{epp,exec_provider}.py` |
| REST 提供方 | `agent_sandbox/providers/rest_provider.py` |
| 契约测试套件 | `agent_sandbox/providers/{testing,contract}.py` |
| `python -m agent_sandbox.providers` | `agent_sandbox/providers/{__main__,doctor}.py` |
| 错误 E8xxx | `agent_sandbox/models/errors.py`（追加） |
| `provider=` 接线 | `agent_sandbox/api/sandbox.py`（`_build_infra`、`create/connect/list/kill_by_id`、`close`） |

Node CLI 根据 `cli/docs/design/providers-and-credentials-cli.md` 里的规格重新实现同样的契约。

---

## 12. 修订（2026-10-13 复核）

这些规则是在用真实的 OpenSandbox 服务器驱动整个抽象之后新增的（见 [2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md)）。Python SDK 和 Node CLI 一致适用。

1. **只有一种「沙箱未找到」。** 来自 `sandbox.get`、`sandbox.connect`、`sandbox.set_timeout`、`sandbox.pause`、`sandbox.resume` 的 `-32002` 会被抛为 `SandboxNotFoundError`（E2009，退出码 4），与内置提供方抛出的类相同。插件可以写 `data.sdk_code = "E2009"`。对未知 id 调用 `sandbox.kill` 仍是空操作。其他的 `-32002` 保持原映射（`sdk_code` 对应的类，否则 E8005）。
2. **所有类型的提供方都强制执行特性。** `exec` 适配器和新增的 `feature_gate`（用于 `rest`）会在发出任何请求之前，对特性不在 `[features] supported` 中的方法抛出 `ProviderFeatureNotSupportedError`（E8004）。规则表为 `SANDBOX_RULES`、`PROCESS_RULES`、`FILESYSTEM_RULES`、`CODE_RULES`；一个方法只要有所列特性之一即可。
3. **列表显示特性。** `provider list` 为每个提供方返回 `features`（按注册表顺序）；文本形式会分组显示（`sandbox(lifecycle,pause) exec(run,stream) pty`）。
4. **未固定的安装。** `--yes` 不会接受分支、标签或缺失的 ref。要接受它们，需要交互式审阅（`confirm` 回调，不带 `--yes`）或 `--allow-unpinned`。拒绝（E8012）时会指出应固定的最新提交。`update` 适用同一规则。
5. **插件的记录不带内置默认值。** 除非插件上报，否则 `region` 为空；两者都给出时 `timeout` 为 `expires_at - created_at`。
6. **`[template]` 只用于创作。** 它不改变创建时 `template` 字符串的含义；那由插件定义（OpenSandbox：镜像 URI）。
7. **清单文件名。** 清单是 `abx-provider.toml`。插件根目录没有它时，以 E8014 失败（“file not found at the plugin root”），并提示使用 `owner/repo//subdir` / `--subdir`。
8. **一致性。** 契约套件要求未知 id 返回 `SandboxNotFoundError`（E2009）。
