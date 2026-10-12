# 配置参考

> **说明：** 本页出现的 `ebx` 命令由 `cli` 仓库中的 Node.js CLI 提供（`npm install -g @easy-sandbox/cli`）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`easy-sandbox`）与容器侧运行时（`easy-sandbox-server`）。

本文档列出 Easy Sandbox 的所有配置项、环境变量、默认值和优先级规则。

---

## 配置优先级

配置按以下优先级加载（从高到低）：

```text
1. 代码参数（sandbox_api_key=、sandbox_base_url=、provider= 等）   ← 最高
2. 进程环境变量
3. ./.env                  （项目文件）
4. ~/.ebx/.env             （用户文件）
5. ~/.ebx/config.toml
6. 提供方 / 内置默认值                                           ← 最低
```

解析是**先按层**的。只要某一层里有这个键的**任意一个**名字，这一层就决定结果。名字的先后只在同一层内比较。

同一层内，名字顺序从最具体到最通用：

1. 提供方作用域的规范名 `EBX_<PROVIDER>_<KEY>`（例如 `EBX_ALICLOUD_EXPRESS_REGION`），只用于提供方继承的核心键；
2. 规范名 `EBX_<KEY>`（例如 `EBX_SANDBOX_API_KEY`）；
3. **compat** 名（E2B：`E2B_API_KEY`、`E2B_API_URL`、`E2B_DOMAIN`）和其他工具定义的 **native** 名（`ALICLOUD_ACCESS_KEY_ID`、`GITHUB_TOKEN`、`OPENAI_API_KEY` 等）；
4. **legacy** 名，即 Easy Sandbox 早期使用的名字（`SANDBOX_API_KEY`、`SANDBOX_REGION`、`AccessKey`、`ACR_*` 等）。

两个 `.env` 文件各自是一层，所以 `./.env` 按键优先于 `~/.ebx/.env`。项目文件里没有的键，仍然来自 `~/.ebx/.env`。

空白或只含空格的值不算已配置，也不会挡住下一层。

早期版本的所有名字都继续有效，完整列表见 [名称别名](#名称别名)。**compat** 名（`E2B_*`）和 **native** 名（`GITHUB_TOKEN`、`OPENAI_*`、`ALICLOUD_*`）永远不会被弃用。

> **行为说明。** 早期版本先把 `./.env` 和 `~/.ebx/.env` 按完全相同的变量名合并，再套用名字优先级。若 `./.env` 里是 `SANDBOX_API_KEY=a`，`~/.ebx/.env` 里是 `E2B_API_KEY=b`，结果是 `b`，这与"`./.env` 优先于 `~/.ebx/.env`"相矛盾。现在解析器先按层，项目文件获胜（`a`）。这个边角场景（同一个键在两个文件里用不同名字）是唯一可观察的变化。`E2B_*` 在每一层里仍排在 `SANDBOX_*` 之前。

## 凭证解析

每项凭证在真正使用时都按上面的分层顺序解析。`ebx config list` 会标出来源：`(env)`、`(user)`、`(default)` 或 `(not set)`。

规范名是 `snake_case` 键，对应的环境变量是 `EBX_<KEY>`。只属于某个提供方的键带提供方前缀：`EBX_<PROVIDER>_<KEY>`（提供方 id 大写，`-` 换成 `_`）。

| 要用的值 | 规范键 / SDK 参数 | 规范环境变量 | 同层内还接受（优先级更低） |
|---|---|---|---|
| 沙箱 API Key | `sandbox_api_key` | `EBX_SANDBOX_API_KEY` | `E2B_API_KEY`（compat）、`SANDBOX_API_KEY`（legacy） |
| 沙箱 API 地址 | `sandbox_base_url` | `EBX_SANDBOX_BASE_URL` | `E2B_API_URL`（compat）、`SANDBOX_API_BASE_URL`（legacy） |
| 数据平面域名 | `sandbox_domain` | `EBX_SANDBOX_DOMAIN` | `E2B_DOMAIN`（compat） |
| 区域（`alicloud-express`） | `region` | `EBX_ALICLOUD_EXPRESS_REGION` | `SANDBOX_REGION`（legacy） |
| 阿里云 AK / SK（`alicloud-express`） | `access_key_id` / `access_key_secret` | `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID` / `..._ACCESS_KEY_SECRET` | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET`（native）、`AccessKey` / `AccessSecret`（legacy） |
| ACR 设置（`alicloud-express`） | `acr_namespace`、`acr_registry`、`acr_repo`、`acr_username`、`acr_password` 等 | `EBX_ALICLOUD_EXPRESS_ACR_<KEY>` | `ACR_NAMESPACE`、`ACR_REGISTRY` 等（legacy） |
| GitHub token | `github_token` | `EBX_GITHUB_TOKEN` | `GITHUB_TOKEN`（native） |
| LLM API Key | `llm_api_key` | `EBX_LLM_API_KEY` | `BAILIAN_CODING_PLAN_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`（native）、`EBX_QWEN_CODE_API_KEY`（legacy） |
| LLM 地址 | `llm_base_url` | `EBX_LLM_BASE_URL` | `OPENAI_BASE_URL`（native） |
| LLM 模型 | `llm_model` | `EBX_LLM_MODEL` | `OPENAI_MODEL`（native） |
| 默认提供方 | `provider` | `EBX_PROVIDER` | 无 |

完整列表（每个别名以及对应的 SDK 关键字参数）见 [名称别名](#名称别名)。

`EBX_GITHUB_TOKEN` 有意排在 `GITHUB_TOKEN` 之前。CI 平台会自动注入 `GITHUB_TOKEN`，而专门设置了更具体的 `EBX_GITHUB_TOKEN` 的人就是想用它。

下面这些调用读的是同一条链：

- `Sandbox.create` 以及其他 SDK 客户端（`load_config`）
- `Sandbox.deploy`（`resolve_llm_env`）
- 自然语言 `ebx create`（编码代理）
- `ebx template install` / `ebx template search`（GitHub token）
- `ebx mcp install`（写入编辑器配置的沙箱 API Key）

旧的 `EBX_QWEN_CODE_API_KEY` 只在 `llm_api_key` 未设置时才当作该键使用。它是 legacy 名，所以在同一层里排在其他所有名字之后。

`ebx mcp install` 把这条链解析出的沙箱 API Key 写入 Cursor 和 Claude 的配置。`E2B_API_URL` 和 `SANDBOX_REGION` 只有在进程环境变量里设置了才会写进同一份文件。`ebx mcp start` 会再次读取 `~/.ebx`，所以用 `ebx config set region` 保存的区域在编辑器启动 server 时仍然生效。

`ebx config list` 把进程环境变量标成 `(env)`，把 `./.env` 和 `~/.ebx` 标成 `(user)`。表里命中的那一列就是命令真正会用的值。

### 提供方作用域

通用键 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain`（及其所有别名，如 `E2B_API_KEY`）属于内置提供方 `alicloud-express`。[提供方插件](../guide/providers.md)只有在其清单的 `[core] inherit` 列出这些键，**并且**你在安装时同意了，才会收到它们。没有这条规则，切换 `EBX_PROVIDER` 会悄悄把你的阿里云密钥发给第三方进程。LLM、GitHub 和 MCP 的键永远不会交给提供方。插件自己的凭证是提供方作用域的键（`EBX_<PROVIDER>_API_KEY`，或 `config.toml` 的 `[providers.<id>]`）。

为提供方 `P` 解析时，永远不会读取其他提供方 `Q` 的 `EBX_<Q>_*` 或 `[providers.Q]`。

---

## 环境变量

### 沙箱连接与调优

| 规范名 | compat / native 别名 | legacy 别名 | 配置键 | 说明 |
|---|---|---|---|---|
| `EBX_PROVIDER` | | | `provider` | 默认提供方 id（默认 `alicloud-express`） |
| `EBX_SANDBOX_API_KEY` | `E2B_API_KEY` | `SANDBOX_API_KEY` | `sandbox_api_key` | 沙箱 API Key |
| `EBX_SANDBOX_BASE_URL` | `E2B_API_URL` | `SANDBOX_API_BASE_URL` | `sandbox_base_url` | 平台 API URL |
| `EBX_SANDBOX_DOMAIN` | `E2B_DOMAIN` | | `sandbox_domain` | 数据平面域名 |
| `EBX_ALICLOUD_EXPRESS_REGION` | | `SANDBOX_REGION` | `region` | 内置提供方的区域 |
| `EBX_HTTP_TIMEOUT` | | `SANDBOX_HTTP_TIMEOUT` | `http_timeout` | HTTP 超时秒数 |
| `EBX_HTTP2` | | | `http2` | 是否启用 HTTP/2 |
| `EBX_MAX_RETRIES` | | | `max_retries` | 最大重试次数 |
| `EBX_MAX_CONNECTIONS`、`EBX_MAX_KEEPALIVE_CONNECTIONS`、`EBX_KEEPALIVE_EXPIRY`、`EBX_WS_PING_INTERVAL`、`EBX_RETRY_BASE_DELAY` | | | 同名小写 | 连接池、保活、WebSocket 和退避调优 |
| `EBX_LOG_LEVEL` | | `SANDBOX_LOG_LEVEL` | `log_level` | SDK 日志级别（默认 `WARNING`） |
| `EBX_DEFAULT_TEMPLATE` | | `SANDBOX_TEMPLATE`，然后 `EBX_TEMPLATE` | `default_template` | 默认模板（MCP server） |

### 阿里云极速版（`alicloud-express`）

| 规范名 | native 别名 | legacy 别名 | 配置键 | 说明 |
|---|---|---|---|---|
| `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID` | `ALICLOUD_ACCESS_KEY_ID` | `AccessKey` | `access_key_id` | 阿里云 AccessKey ID |
| `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_SECRET` | `ALICLOUD_ACCESS_KEY_SECRET` | `AccessSecret` | `access_key_secret` | 阿里云 AccessKey Secret |
| `EBX_ALICLOUD_EXPRESS_ACR_NAMESPACE` | | `ACR_NAMESPACE` | `acr_namespace` | ACR 命名空间 |
| `EBX_ALICLOUD_EXPRESS_ACR_REGISTRY` | | `ACR_REGISTRY` | `acr_registry` | ACR 仓库地址 |
| `EBX_ALICLOUD_EXPRESS_ACR_REPO` | | `ACR_REPO` | `acr_repo` | ACR 仓库 |
| `EBX_ALICLOUD_EXPRESS_ACR_USERNAME` | | `ACR_USERNAME` | `acr_username` | ACR 用户名 |
| `EBX_ALICLOUD_EXPRESS_ACR_PASSWORD` | | `ACR_PASSWORD` | `acr_password` | ACR 密码 |
| `EBX_ALICLOUD_EXPRESS_ACR_INSTANCE_ID` | | `ACREE_INSTANCE_ID` | `acr_instance_id` | ACR 企业版实例 |
| `EBX_ALICLOUD_EXPRESS_ACR_VPC_ID` | | `ACR_VPC_ID` | `acr_vpc_id` | ACR VPC |
| `EBX_ALICLOUD_EXPRESS_ACR_VSWITCH_IDS` | | `ACR_VSWITCH_IDS` | `acr_vswitch_ids` | ACR 交换机 id（逗号分隔） |
| `EBX_ALICLOUD_EXPRESS_ACR_SECURITY_GROUP_ID` | | `ACR_SECURITY_GROUP_ID` | `acr_security_group_id` | ACR 安全组 |
| `EBX_ALICLOUD_EXPRESS_TEAM_ID` | `E2B_TEAM_ID`（compat） | `TEAM_ID` | `team_id` | 团队 id |

### LLM、GitHub、模板、MCP

| 规范名 | native / legacy 别名 | 配置键 | 说明 |
|---|---|---|---|
| `EBX_LLM_API_KEY` | `BAILIAN_CODING_PLAN_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`；legacy `EBX_QWEN_CODE_API_KEY` | `llm_api_key` | LLM API Key（用 `ebx config set llm_api_key` 保存） |
| `EBX_LLM_BASE_URL` | `OPENAI_BASE_URL`；legacy toml `qwen_code_base_url` | `llm_base_url` | LLM 地址 |
| `EBX_LLM_MODEL` | `OPENAI_MODEL`；legacy toml `qwen_code_model` | `llm_model` | LLM 模型名 |
| `EBX_GITHUB_TOKEN` | `GITHUB_TOKEN` | `github_token` | GitHub token（模板下载用；CI 以 Secret 注入） |
| `EBX_TEMPLATE_INDEX_URL`、`EBX_TEMPLATE_DIR` | | `template_index_url`、`template_dir` | 模板索引与目录（仅环境变量） |
| `EBX_MCP_AUTH_TOKEN`、`EBX_MCP_ALLOWED_ORIGINS`、`EBX_MCP_RUNTIME_DIR` | | `mcp_*` | MCP server（仅环境变量） |

标注"仅环境变量"的键从相同的分层读取，但不能用 `ebx config set` 写入。

当 `E2B_API_KEY` 和 `SANDBOX_API_KEY` 同时存在时，`E2B_API_KEY` 优先，而 `EBX_SANDBOX_API_KEY` 优先于两者。SDK 字段是 `sandbox_api_key`；旧字段名 `api_key` 仍可作为构造函数 / 关键字参数使用。

LLM API Key 在同一层内的顺序是 `EBX_LLM_API_KEY`，然后 `BAILIAN_CODING_PLAN_API_KEY`、`DASHSCOPE_API_KEY`、`OPENAI_API_KEY`。进程环境变量里的任何一个都优先于 `./.env`，`./.env` 又优先于 `~/.ebx/.env`。LLM 地址和模型同理。

### 名称别名

别名分四类。只有 **legacy** 别名会被 `audit_config()` / `ebx config check` 报告。

| 类别 | 含义 | 示例 | 审计是否报告 |
|---|---|---|---|
| canonical | 文档推荐的名字 | `EBX_SANDBOX_API_KEY` | 否 |
| compat | E2B 兼容名，保留以便现有 E2B 代码继续工作 | `E2B_API_KEY` | 否 |
| native | 其他工具或厂商定义的名字 | `ALICLOUD_ACCESS_KEY_ID`、`GITHUB_TOKEN`、`OPENAI_API_KEY` | 否 |
| legacy | Easy Sandbox 早期的名字 | `SANDBOX_API_KEY`、`AccessKey`、`ACR_NAMESPACE` | 是 |

使用 legacy 名绝不会改变 stdout 或 stderr。想知道自己用了哪些，运行 `python -c "from easy_sandbox.transport.config import audit_config; print(audit_config())"`（只输出名字，不输出值）。设置 `EBX_WARN_DEPRECATED=1` 后，每个进程对每个 legacy 构造函数关键字（`api_key=`、`api_url=`、`domain=`）发出一次 `DeprecationWarning`。0.x 不会删除任何别名。

SDK 构造函数 / 关键字别名：

| 规范名 | 接受的 legacy 关键字 |
|---|---|
| `sandbox_api_key` | `api_key` |
| `sandbox_base_url` | `api_url`、`api_base_url` |
| `sandbox_domain` | `domain` |

属性 `TransportConfig.api_key`、`.api_url` 和 `.domain` 仍可读可写。

### 迁移已保存的配置

阶段 1（当前版本）继续写入旧的存储名，以便旧工具读取同样的文件：`ebx config set sandbox_api_key` 把 `E2B_API_KEY` 写入 `~/.ebx/.env`，基础 URL 以 `api_url` 存在 `[transport]` 里。`migrate` 把所有内容改写为规范名，并设置 `[core] config_format = 2`。

```python
from easy_sandbox.transport.config import plan_migration, apply_migration

for step in plan_migration():       # 预演，不输出任何值
    print(step)
apply_migration()                   # 写入规范名；保留 config.toml.bak / .env.bak（权限 600）
```

迁移之后，旧版本的 Easy Sandbox 看不到被移动的键。compat 名（`E2B_*`）只会在文件里被改名，在进程环境变量里永远有效。

### Server 端环境变量

以下环境变量用于沙箱内部 Server 配置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `EBX_SERVER_TOKEN` | — | Server 认证令牌 |
| `EBX_SERVER_BASE_DIR` | — | Server 工作基目录 |
| `EBX_SERVER_DISABLED_GROUPS` | `DEV_TOOLS,BROWSER` | 禁用的能力组（逗号分隔） |
| `EBX_PTY_PORT` | — | PTY 终端 WebSocket 端口 |
| `EBX_MAX_UPLOAD_SIZE` | — | 最大上传文件大小 |

### 部署相关

| 环境变量 | 说明 |
|----------|------|
| `BAILIAN_CODING_PLAN_API_KEY` | 百炼编码 Agent API Key（deploy 用） |
| `DASHSCOPE_API_KEY` | DashScope API Key（deploy 用） |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key（deploy 用） |

---

## config.toml 配置

配置文件路径：`~/.ebx/config.toml`

```toml
[core]
provider = "alicloud-express"   # 默认提供方（ebx provider default NAME）
# config_format = 2             # 由 `config migrate` 设置

[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain = "cn-hangzhou.e2b.fc.aliyuncs.com"
http_timeout = 30.0
max_retries = 3

[providers.alicloud-express]
region = "cn-hangzhou"

[providers.my-cloud]            # 插件自己的作用域键
endpoint = "https://sandbox.my-cloud.example"   # 该插件声明的键

[shortcuts]
init = "template init"          # 命令路径，不要写成 "ebx template init"
ps   = "sandbox process list"
```

`config.toml` 中某个键的查找顺序：`[providers.<id>].<key>`，然后 `[transport].<key>`，然后 `[transport].<legacy 名>`（`api_url`、`api_base_url`、`domain`、`api_key`、`qwen_code_*`）。顶层的扁平 legacy 键只在文件没有 `[transport]` 表时才读取。早期版本写出的文件（`[transport] api_url = ...`、`region = ...`）不需要改动，继续有效。

`[shortcuts]`（顶层命令别名）只由 `ebx` CLI 读取，SDK 会忽略。其规则（值不带 `ebx` 前缀、写错的行在启动时被跳过）见 [CLI 参考](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/reference/cli-reference.md#快捷方式别名shortcutsalias)。

---

## TransportConfig 字段

| 字段 | legacy 名 | 类型 | 默认值 | 说明 |
|------|-----------|------|--------|------|
| `provider` | | `str` | `"alicloud-express"` | 当前提供方 id |
| `sandbox_base_url` | `api_url`、`api_base_url` | `str` | `"https://api.cn-hangzhou.e2b.fc.aliyuncs.com"` | 平台 API URL |
| `sandbox_domain` | `domain` | `str` | `"cn-hangzhou.e2b.fc.aliyuncs.com"` | 数据平面域名 |
| `region` | | `str` | `"cn-hangzhou"` | 区域（`alicloud-express`） |
| `sandbox_api_key` | `api_key` | `str \| None` | `None` | 沙箱 API Key |
| `access_key_id` | | `str \| None` | `None` | 阿里云 AK |
| `access_key_secret` | | `str \| None` | `None` | 阿里云 SK |
| `provider_options` | | `dict` | `{}` | 提供方作用域的值：内置提供方的额外键（如 `acr_*`）或插件自己的键 |
| `http_timeout` | | `float` | `30.0` | HTTP 请求超时（秒，≥1.0） |
| `max_connections` | | `int` | `100` | 最大连接数 |
| `max_keepalive_connections` | | `int` | `20` | 最大保活连接数 |
| `keepalive_expiry` | | `float` | `30.0` | 保活连接过期时间（秒） |
| `http2` | | `bool` | `True` | 是否启用 HTTP/2 |
| `ws_ping_interval` | | `float` | `30.0` | WebSocket ping 间隔（秒） |
| `max_retries` | | `int` | `3` | 最大重试次数 |
| `retry_base_delay` | | `float` | `1.0` | 重试基础延迟（秒） |

构造函数和 `load_config(...)` 都接受 legacy 名，它们也仍然是可读可写的属性（`config.api_key`、`config.api_url`、`config.domain`）。

### 区域自动推导

当基础 URL 没有通过参数或进程环境变量设置，但设置了区域时，内置提供方会推导：

```text
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

来自 `.env` 文件或 `config.toml` 的值算作默认值，因此保存在那里的基础 URL 会保留，另一个值仍由区域推导。这是历史行为，保持不变。`alicloud-express` 之外的提供方没有区域推导，除非其清单声明了。

### 查看解析结果

```python
from easy_sandbox.transport.config import explain_config, audit_config

explain_config()   # {"sandbox_api_key": {"value": "****3dc1", "source": "environ", "name": "E2B_API_KEY", "secret": True}, ...}
audit_config()     # [{"where": "env", "name": "SANDBOX_API_KEY", "canonical_key": "sandbox_api_key",
                   #   "canonical_name": "EBX_SANDBOX_API_KEY", "kind": "legacy"}, ...]
```

`explain_config()` 告诉你每个键由哪一层（`override`、`environ`、`dotenv`、`toml`、`derived`、`default`）的哪个名字决定，密钥已脱敏。`audit_config()` 只列出 legacy 名，从不输出值。

---

## SDK 参数覆盖

在代码中直接传参（最高优先级）：

```python
from easy_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.create(
    sandbox_api_key="REPLACE_ME",
    sandbox_base_url="https://api.cn-beijing.e2b.fc.aliyuncs.com",
    access_key_id="REPLACE_ME",
    access_key_secret="REPLACE_ME",
)

# 为这次调用选择另一个提供方；选项按提供方作用域
sandbox = await Sandbox.create(provider="my-cloud", provider_options={"api_key": "REPLACE_ME"})
```

旧的关键字 `api_key=`、`api_url=`、`domain=` 仍然被接受，含义完全相同。对同一个设置同时传规范关键字和 legacy 关键字且值不同，会抛出 `ValueError`。见[提供方](../guide/providers.md)。

---

## .env 文件

SDK 会读取这两个 `.env`，每个文件各自是一层，所以按键合并：

1. 当前目录下的 `.env`（写了该键时优先）
2. `~/.ebx/.env`（项目文件没有的键用这里的值）

`.env` 文件格式。任何被接受的名字都可以；新文件推荐使用规范名：

```bash
EBX_SANDBOX_API_KEY=your-api-key
EBX_ALICLOUD_EXPRESS_REGION=cn-beijing
EBX_PROVIDER=alicloud-express
```

同一文件里的 `E2B_API_KEY=...` 和 `SANDBOX_REGION=cn-beijing` 含义相同。

`ebx config set sandbox_api_key <KEY>` 命令将 API Key 保存到 `~/.ebx/.env`（文件权限 600）。`github_token`（对应 `GITHUB_TOKEN`）等凭证键以同样方式存储。

---

## 配置文件位置汇总

| 文件 | 路径 | 说明 |
|------|------|------|
| config.toml | `~/.ebx/config.toml` | SDK 扩展配置（`[core]`、`[transport]`、`[providers.<id>]`、`[shortcuts]`） |
| .env | `~/.ebx/.env` | 认证凭证（auth login / `ebx config set` 写入） |
| .env（本地） | `./.env` | 项目级环境变量 |
| 会话存储 | `~/.ebx/sessions/*.json` | 本地会话数据 |
| 模板缓存 | `~/.ebx/templates/` | 已安装的模板 |
| 提供方插件 | `~/.ebx/providers/<id>/` | 已安装的提供方插件（代码、`ebx-provider.toml`、`.ebx-install.json` 回执；`data/` 是插件自己的状态目录） |

---

## 相关：ebx CLI

从命令行读写这些配置属于 CLI 功能：`ebx config list|get|set|init`、`ebx config get|set` 接受的键、显示变量 `EBX_ACTIVITY_LINES`，以及 `ebx config check` / `ebx config migrate`（即 `audit_config()` 与 `apply_migration()` 的 CLI 形式，规格见[Provider 与凭证](../design/providers-and-credentials.md)）。它们记录在 CLI 仓库：[CLI 配置参考](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/zh/reference/configuration.md)；面向 provider 的新语法见其 [Provider 与凭证 CLI 规格](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/design/providers-and-credentials-cli.md)。
