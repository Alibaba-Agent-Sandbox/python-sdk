# 配置参考

本指南描述异步 `ProviderSandbox` 扩展；根级 `Sandbox` 和 `AsyncSandbox` 遵循固定版本的标准迁移契约，详见[从 E2B 迁移](../guide/migrate-from-e2b.md)。

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（`npm install -g @agent-sandbox/cli`）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

本文档列出 Agent Sandbox 的所有配置项、环境变量、默认值和优先级规则。

---

## 配置优先级

配置按以下优先级加载（从高到低）：

```text
1. 代码参数（sandbox_api_key=、sandbox_base_url=、provider= 等）   ← 最高
2. 进程环境变量
3. ./.env                  （项目文件）
4. ~/.abx/.env             （用户文件）
5. ~/.abx/config.toml
6. 提供方 / 内置默认值                                           ← 最低
```

解析是**先按层**的。每个键只有一个环境变量。第一个设置了该变量的层决定结果。

两个 `.env` 文件各自是一层，所以 `./.env` 按键优先于 `~/.abx/.env`。项目文件里没有的键，仍然来自 `~/.abx/.env`。

空白或只含空格的值不算已配置，也不会挡住下一层。

## 凭证解析

每项凭证在真正使用时都按上面的分层顺序解析。`abx config list` 会标出来源：`(env)`、`(user)`、`(default)` 或 `(not set)`。

每个键只有一个名字。产品自己的设置用 `ABX_<KEY>`。厂商已经公布的变量就用那个变量：阿里云 AccessKey 是 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`，地域是 `ALIBABA_CLOUD_REGION_ID`，GitHub token 是 `GITHUB_TOKEN`。模板构建（`ACR_*`、`team_id`）和模板生成（`ABX_LLM_*`）的设置属于 `abx` CLI，见其[配置参考](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/configuration.md)；Python SDK 不读取它们。

| 要用的值 | 键 | 环境变量 |
|---|---|---|
| 沙箱 API Key | `sandbox_api_key` | `ABX_SANDBOX_API_KEY` |
| 沙箱 API 地址 | `sandbox_base_url` | `ABX_SANDBOX_BASE_URL` |
| 数据平面域名 | `sandbox_domain` | `ABX_SANDBOX_DOMAIN` |
| 地域 | `region` | `ALIBABA_CLOUD_REGION_ID` |
| 阿里云 AK / SK | `access_key_id` / `access_key_secret` | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` |
| GitHub token | `github_token` | `GITHUB_TOKEN` |
| 默认提供方 | `provider` | `ABX_PROVIDER` |

下面这些调用读的是同一条链：

- `Sandbox.create` 以及其他 SDK 客户端（`load_config`）
- 自然语言 `abx create`（编码代理）
- `abx template install` / `abx template search`（GitHub token）
- `abx mcp install`（写入编辑器配置的沙箱 API Key）

`abx mcp install` 把 `ABX_SANDBOX_API_KEY` 写入 Cursor 和 Claude 的配置。`ABX_SANDBOX_BASE_URL` 和 `ALIBABA_CLOUD_REGION_ID` 只有在进程环境变量里设置了才会写进同一份文件。`abx mcp start` 会再次读取 `~/.abx`，所以用 `abx config set region` 保存的区域在编辑器启动 server 时仍然生效。

`abx config list` 把进程环境变量标成 `(env)`，把 `./.env` 和 `~/.abx` 标成 `(user)`。表里命中的那一列就是命令真正会用的值。

### 提供方作用域

通用键 `sandbox_api_key`、`sandbox_base_url`、`sandbox_domain` 属于内置提供方 `alicloud-express`。[提供方插件](../guide/providers.md)只有在其清单的 `[core] inherit` 列出这些键，**并且**你在安装时同意了，才会收到它们。没有这条规则，切换 `ABX_PROVIDER` 会悄悄把你的阿里云密钥发给第三方进程。LLM、GitHub 和 MCP 的键永远不会交给提供方。插件自己的凭证是提供方作用域的键（`ABX_<PROVIDER>_API_KEY`，或 `config.toml` 的 `[providers.<id>]`）。

为提供方 `P` 解析时，永远不会读取其他提供方 `Q` 的 `ABX_<Q>_*` 或 `[providers.Q]`。

---

沙箱调用需要 `ABX_SANDBOX_API_KEY`；AK/SK 用于独立官方控制面，不能替代沙箱密钥。见[鉴权迁移](../guide/authentication.md)。

## 环境变量

每一行都是该键唯一的环境变量。`abx config set` 写入同一个名字。

### 沙箱连接与调优

| 环境变量 | 配置键 | 说明 |
|---|---|---|
| `ABX_PROVIDER` | `provider` | 默认提供方 id（默认 `alicloud-express`） |
| `ABX_SANDBOX_API_KEY` | `sandbox_api_key` | 沙箱 API Key |
| `ABX_SANDBOX_BASE_URL` | `sandbox_base_url` | 平台 API URL |
| `ABX_SANDBOX_DOMAIN` | `sandbox_domain` | 数据平面域名 |
| `ALIBABA_CLOUD_REGION_ID` | `region` | 内置提供方的区域 |
| `ABX_HTTP_TIMEOUT` | `http_timeout` | HTTP 超时秒数 |
| `ABX_HTTP2` | `http2` | 是否启用 HTTP/2 |
| `ABX_MAX_CONNECTIONS`、`ABX_MAX_KEEPALIVE_CONNECTIONS`、`ABX_KEEPALIVE_EXPIRY`、`ABX_WS_PING_INTERVAL` | 同名小写 | 连接池、保活和 WebSocket 调优 |
| `ABX_LOG_LEVEL` | `log_level` | SDK 日志级别（默认 `WARNING`） |
| `ABX_DEFAULT_TEMPLATE` | `default_template` | 默认模板（MCP server） |

### 阿里云极速版（`alicloud-express`）

| 环境变量 | 配置键 | 说明 |
|---|---|---|
| `ALICLOUD_ACCESS_KEY_ID` | `access_key_id` | 阿里云 AccessKey ID |
| `ALICLOUD_ACCESS_KEY_SECRET` | `access_key_secret` | 阿里云 AccessKey Secret |

### GitHub、模板、MCP

| 环境变量 | 配置键 | 说明 |
|---|---|---|
| `GITHUB_TOKEN` | `github_token` | GitHub token（模板下载用；CI 以 Secret 注入） |
| `ABX_TEMPLATE_INDEX_URL`、`ABX_TEMPLATE_DIR` | `template_index_url`、`template_dir` | 模板索引与目录（仅环境变量） |
| `ABX_MCP_AUTH_TOKEN`、`ABX_MCP_ALLOWED_ORIGINS`、`ABX_MCP_RUNTIME_DIR` | `mcp_*` | MCP server（仅环境变量） |

标注"仅环境变量"的键从相同的分层读取，但不能用 `abx config set` 写入。

沙箱密钥的 SDK 字段是 `sandbox_api_key`。基础 URL 的 SDK 字段是 `sandbox_base_url`。数据平面域名的 SDK 字段是 `sandbox_domain`。

### 每个键一个名字

读取某个键时只看它那一个环境变量，保存时也用同一个名字。`abx config set sandbox_api_key` 把 `ABX_SANDBOX_API_KEY` 写入 `~/.abx/.env`。`abx config set sandbox_base_url` 把 `sandbox_base_url` 写入 `[transport]`。`abx config set github_token` 写入 `GITHUB_TOKEN`。`abx config set region` 为内置提供方写入 `region`；该键的环境变量是 `ALIBABA_CLOUD_REGION_ID`。

### Server 端环境变量

以下环境变量用于沙箱内部 Server 配置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ABX_SERVER_TOKEN` | — | Server 认证令牌 |
| `ABX_SERVER_BASE_DIR` | `/home/user` | 所有接收路径的端点（包括 shell 的 `cwd`）必须留在其下的目录 |
| `ABX_SERVER_ENABLED_GROUPS` | — | 要打开的组，逗号分隔，例如 `agents,dev_tools`。唯一的组环境变量，没有用来关闭组的变量 |
| `ABX_SERVER_POLICY` | — | 内联 JSON 策略文档（键与 `server:` 块相同） |
| `ABX_SERVER_POLICY_FILE` | — | 策略 JSON 文件路径 |
| `ABX_PTY_PORT` | `9001` | PTY 终端 WebSocket 端口 |
| `ABX_MAX_UPLOAD_SIZE` | 100 MiB | 解码后上传大小上限 |

### 构建与部署相关的键

`ACR_*`、`team_id` 和 `ABX_LLM_*` 键由 `abx` CLI 声明，只有它会构建或生成模板。Python SDK 是运行时客户端，既不声明也不读取它们。

---

## config.toml 配置

配置文件路径：`~/.abx/config.toml`

```toml
[core]
provider = "alicloud-express"   # 默认提供方（abx provider default NAME）

[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain = "cn-hangzhou.e2b.fc.aliyuncs.com"
http_timeout = 30.0

[providers.alicloud-express]
region = "cn-hangzhou"

[providers.my-cloud]            # 插件自己的作用域键
endpoint = "https://sandbox.my-cloud.example"   # 该插件声明的键

[shortcuts]
init = "template init"          # 命令路径，不要写成 "abx template init"
ps   = "sandbox process list"
```

`config.toml` 中某个键的查找顺序：`[providers.<id>].<key>`，然后 `[transport].<key>`。文件里的键名就是上表中的配置键。

`[shortcuts]`（顶层命令别名）只由 `abx` CLI 读取，SDK 会忽略。其规则（值不带 `abx` 前缀、写错的行在启动时被跳过）见 [CLI 参考](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/cli-reference.md#快捷方式别名shortcutsalias)。

---

## TransportConfig 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | `str` | `"alicloud-express"` | 当前提供方 id |
| `sandbox_base_url` | `str` | `"https://api.cn-hangzhou.e2b.fc.aliyuncs.com"` | 平台 API URL |
| `sandbox_domain` | `str` | `"cn-hangzhou.e2b.fc.aliyuncs.com"` | 数据平面域名 |
| `region` | `str` | `"cn-hangzhou"` | 区域（`alicloud-express`） |
| `sandbox_api_key` | `str \| None` | `None` | 沙箱 API Key |
| `access_key_id` | `str \| None` | `None` | 阿里云 AK |
| `access_key_secret` | `str \| None` | `None` | 阿里云 SK |
| `provider_options` | `dict` | `{}` | 提供方作用域的值：插件自己的键 |
| `http_timeout` | `float` | `30.0` | HTTP 请求超时（秒，≥1.0） |
| `max_connections` | `int` | `100` | 最大连接数 |
| `max_keepalive_connections` | `int` | `20` | 最大保活连接数 |
| `keepalive_expiry` | `float` | `30.0` | 保活连接过期时间（秒） |
| `http2` | `bool` | `True` | 是否启用 HTTP/2 |
| `ws_ping_interval` | `float` | `30.0` | WebSocket ping 间隔（秒） |

构造函数和 `load_config(...)` 使用这些字段名。

### 区域自动推导

当基础 URL 没有通过参数或进程环境变量设置，但设置了区域时，内置提供方会推导：

```text
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

来自 `.env` 文件或 `config.toml` 的值算作默认值，因此保存在那里的基础 URL 会保留，另一个值仍由区域推导。这是历史行为，保持不变。`alicloud-express` 之外的提供方没有区域推导，除非其清单声明了。

### 查看解析结果

```python
from agent_sandbox.transport.config import explain_config

explain_config()   # {"sandbox_api_key": {"value": "****3dc1", "source": "environ", "name": "ABX_SANDBOX_API_KEY", "secret": True}, ...}
```

`explain_config()` 告诉你每个键由哪一层（`override`、`environ`、`dotenv`、`toml`、`derived`、`default`）的哪个变量决定，密钥已脱敏。`name` 就是该键唯一的环境变量。

---

## SDK 参数覆盖

`ProviderSandbox.create`、`connect` 和 `list` 的这些覆盖参数仅为 `sandbox_api_key`、`sandbox_base_url` 和 `sandbox_domain`。控制面方法 `kill_by_id`、`get_info_by_id` 和 `set_timeout_by_id` 接受前两个参数，不需要数据面域名；其 `_sync` 版本使用相同参数。标准 `Sandbox` / `AsyncSandbox` 保留各自的 `ApiParams` 契约。

在代码中直接传参（最高优先级）：

```python
from agent_sandbox import ProviderSandbox as Sandbox

sandbox = await Sandbox.create(
    sandbox_api_key="REPLACE_ME",
    sandbox_base_url="https://api.cn-beijing.e2b.fc.aliyuncs.com",
    access_key_id="REPLACE_ME",
    access_key_secret="REPLACE_ME",
)

# 为这次调用选择另一个提供方；选项按提供方作用域
sandbox = await Sandbox.create(provider="my-cloud", provider_options={"endpoint": "https://sandbox.my-cloud.example"})
```

见[提供方](../guide/providers.md)。

---

## .env 文件

SDK 会读取这两个 `.env`，每个文件各自是一层，所以按键合并：

1. 当前目录下的 `.env`（写了该键时优先）
2. `~/.abx/.env`（项目文件没有的键用这里的值）

`.env` 文件格式。每个键使用它那一个变量：

```bash
ABX_SANDBOX_API_KEY=your-api-key
ALIBABA_CLOUD_REGION_ID=cn-beijing
ABX_PROVIDER=alicloud-express
```

`abx config set sandbox_api_key <KEY>` 命令将 API Key 以 `ABX_SANDBOX_API_KEY` 保存到 `~/.abx/.env`（文件权限 600）。`github_token` 存为 `GITHUB_TOKEN`。AccessKey 存为 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`。

---

## 配置文件位置汇总

| 文件 | 路径 | 说明 |
|------|------|------|
| config.toml | `~/.abx/config.toml` | SDK 扩展配置（`[core]`、`[transport]`、`[providers.<id>]`、`[shortcuts]`） |
| .env | `~/.abx/.env` | 认证凭证（auth login / `abx config set` 写入） |
| .env（本地） | `./.env` | 项目级环境变量 |
| 会话存储 | `~/.abx/sessions/*.json` | 本地会话数据 |
| 模板缓存 | `~/.abx/templates/` | 已安装的模板 |
| 提供方插件 | `~/.abx/providers/<id>/` | 已安装的提供方插件（代码、`abx-provider.toml`、`.abx-install.json` 回执；`data/` 是插件自己的状态目录） |

---

## 相关：abx CLI

从命令行读写这些配置属于 CLI 功能：`abx config list|get|set|init`、`abx config get|set` 接受的键，以及显示变量 `ABX_ACTIVITY_LINES`。它们记录在 CLI 仓库：[CLI 配置参考](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/configuration.md)；面向 provider 的键见其 [Provider 与凭证 CLI 规格](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/design/providers-and-credentials-cli.md)。

### 传输尝试

内置平台/envd HTTP 每次只执行一次传输尝试，提供方引擎的读取恢复独立处理。应用重试安全读取时应限制次数；写操作结果未知时，应先核对远端状态，再决定是否重新执行。
