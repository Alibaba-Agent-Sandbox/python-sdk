# Configuration Reference

> **Note:** The `ebx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @easy-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`easy-sandbox`) and the container-side runtime (`easy-sandbox-server`).

This document lists all Easy Sandbox configuration options, environment variables, default values, and priority rules.

---

## Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):

```text
1. Code parameters (sandbox_api_key=, sandbox_base_url=, provider=, ...)   ← Highest
2. Process environment variables
3. ./.env                  (project file)
4. ~/.ebx/.env             (user file)
5. ~/.ebx/config.toml
6. Provider / built-in defaults                                           ← Lowest
```

Resolution is **layer first**. Each key has exactly one environment variable. The first layer that sets that variable wins.

Both `.env` files are separate layers, so `./.env` beats `~/.ebx/.env` per key. A key that the project file does not set still comes from `~/.ebx/.env`.

A blank or whitespace-only value does not count. It does not hide the next layer.

## Credential resolution

Every credential uses the layers above at the moment it is needed. `ebx config list` shows the winner and labels it `(env)`, `(user)`, `(default)`, or `(not set)`.

Each key has one name. Product settings use `EBX_<KEY>`. A vendor that already publishes a variable keeps that variable: Alibaba Cloud access keys are `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`, the region is `ALIBABA_CLOUD_REGION_ID`, ACR settings are `ACR_NAMESPACE` and the matching `ACR_*` variables, and the GitHub token is `GITHUB_TOKEN`. `team_id` is optional and is not required; its environment variable is `EBX_ALICLOUD_EXPRESS_TEAM_ID`.

| What you need | Key | Environment variable |
|---|---|---|
| Sandbox API key | `sandbox_api_key` | `EBX_SANDBOX_API_KEY` |
| Sandbox API base URL | `sandbox_base_url` | `EBX_SANDBOX_BASE_URL` |
| Data-plane domain | `sandbox_domain` | `EBX_SANDBOX_DOMAIN` |
| Region | `region` | `ALIBABA_CLOUD_REGION_ID` |
| Alibaba Cloud AK / SK | `access_key_id` / `access_key_secret` | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` |
| ACR namespace / password | `acr_namespace` / `acr_password` | `ACR_NAMESPACE` / `ACR_PASSWORD` |
| GitHub token | `github_token` | `GITHUB_TOKEN` |
| LLM API key | `llm_api_key` | `EBX_LLM_API_KEY` |
| LLM base URL | `llm_base_url` | `EBX_LLM_BASE_URL` |
| LLM model | `llm_model` | `EBX_LLM_MODEL` |
| Default provider | `provider` | `EBX_PROVIDER` |
| Team id (optional) | `team_id` | `EBX_ALICLOUD_EXPRESS_TEAM_ID` |

The same chain is what these calls read:

- `Sandbox.create` and the other SDK clients (`load_config`)
- `Sandbox.deploy` (`resolve_llm_env`)
- natural-language `ebx create` (the coding agent)
- `ebx template install` / `ebx template search` (GitHub token)
- `ebx mcp install` (the sandbox API key copied into the editor config)

`ebx mcp install` writes `EBX_SANDBOX_API_KEY` into the Cursor and Claude config. `EBX_SANDBOX_BASE_URL` and `ALIBABA_CLOUD_REGION_ID` are copied into the same file only when the process environment sets them. `ebx mcp start` loads `~/.ebx` again, so a region saved with `ebx config set region` still applies when the editor starts the server.

`ebx config list` marks a process variable as `(env)` and either file as `(user)`. The value in the table is the one the command will use.

### Provider scoping

The generic keys `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` belong to the built-in provider `alicloud-express`. A [provider plugin](../guide/providers.md) receives them only when its manifest lists them under `[core] inherit` **and** you consented to that when you installed it. Without this rule, switching `EBX_PROVIDER` would silently send your Alibaba Cloud key to a third-party process. LLM, GitHub and MCP keys are never delivered to a provider. Plugin-specific credentials are provider-scoped keys (`EBX_<PROVIDER>_API_KEY`, or `[providers.<id>]` in `config.toml`).

Resolving for provider `P` never reads `EBX_<Q>_*` or `[providers.Q]` for another provider `Q`.

---

## Environment Variables

Each row is the only environment variable for that key. `ebx config set` writes that same name.

### Sandbox connection and tuning

| Environment variable | Config key | Description |
|---|---|---|
| `EBX_PROVIDER` | `provider` | Default provider id (default `alicloud-express`) |
| `EBX_SANDBOX_API_KEY` | `sandbox_api_key` | Sandbox API key |
| `EBX_SANDBOX_BASE_URL` | `sandbox_base_url` | Platform API URL |
| `EBX_SANDBOX_DOMAIN` | `sandbox_domain` | Data-plane domain |
| `ALIBABA_CLOUD_REGION_ID` | `region` | Region of the built-in provider |
| `EBX_HTTP_TIMEOUT` | `http_timeout` | HTTP timeout in seconds |
| `EBX_HTTP2` | `http2` | HTTP/2 on or off |
| `EBX_MAX_RETRIES` | `max_retries` | Maximum retry count |
| `EBX_MAX_CONNECTIONS`, `EBX_MAX_KEEPALIVE_CONNECTIONS`, `EBX_KEEPALIVE_EXPIRY`, `EBX_WS_PING_INTERVAL`, `EBX_RETRY_BASE_DELAY` | same names, lower case | Pool, keep-alive, WebSocket and back-off tuning |
| `EBX_LOG_LEVEL` | `log_level` | SDK log level (default `WARNING`) |
| `EBX_DEFAULT_TEMPLATE` | `default_template` | Default template (MCP server) |

### Alibaba Cloud Express Edition (`alicloud-express`)

| Environment variable | Config key | Description |
|---|---|---|
| `ALICLOUD_ACCESS_KEY_ID` | `access_key_id` | Alibaba Cloud AccessKey ID |
| `ALICLOUD_ACCESS_KEY_SECRET` | `access_key_secret` | Alibaba Cloud AccessKey Secret |
| `ACR_NAMESPACE` | `acr_namespace` | ACR namespace |
| `ACR_REGISTRY` | `acr_registry` | ACR registry host |
| `ACR_REPO` | `acr_repo` | ACR repository |
| `ACR_USERNAME` | `acr_username` | ACR user name |
| `ACR_PASSWORD` | `acr_password` | ACR password |
| `ACREE_INSTANCE_ID` | `acr_instance_id` | ACR Enterprise Edition instance |
| `ACR_VPC_ID` | `acr_vpc_id` | ACR VPC |
| `ACR_VSWITCH_IDS` | `acr_vswitch_ids` | ACR vSwitch ids (comma separated) |
| `ACR_SECURITY_GROUP_ID` | `acr_security_group_id` | ACR security group |
| `EBX_ALICLOUD_EXPRESS_TEAM_ID` | `team_id` | Team id. Optional. Not required. |

### LLM, GitHub, templates, MCP

| Environment variable | Config key | Description |
|---|---|---|
| `EBX_LLM_API_KEY` | `llm_api_key` | LLM API key (store with `ebx config set llm_api_key`) |
| `EBX_LLM_BASE_URL` | `llm_base_url` | LLM base URL |
| `EBX_LLM_MODEL` | `llm_model` | LLM model name |
| `GITHUB_TOKEN` | `github_token` | GitHub token for template downloads (CI: inject as a secret) |
| `EBX_TEMPLATE_INDEX_URL`, `EBX_TEMPLATE_DIR` | `template_index_url`, `template_dir` | Template index and directory (environment only) |
| `EBX_MCP_AUTH_TOKEN`, `EBX_MCP_ALLOWED_ORIGINS`, `EBX_MCP_RUNTIME_DIR` | `mcp_*` | MCP server (environment only) |

Keys marked "environment only" are read from the same layers but cannot be written with `ebx config set`.

The SDK field for the sandbox key is `sandbox_api_key`. The SDK field for the base URL is `sandbox_base_url`. The SDK field for the data-plane host is `sandbox_domain`.

### One name per key

A key is read from its one environment variable and stored under that same name. `ebx config set sandbox_api_key` writes `EBX_SANDBOX_API_KEY` to `~/.ebx/.env`. `ebx config set sandbox_base_url` writes `sandbox_base_url` in `[transport]`. `ebx config set github_token` writes `GITHUB_TOKEN`. `ebx config set region` writes `region` for the built-in provider; the environment variable for that key is `ALIBABA_CLOUD_REGION_ID`.

### Server-Side Environment Variables

The following environment variables are used for in-sandbox Server configuration:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `EBX_SERVER_TOKEN` | — | Server authentication token |
| `EBX_SERVER_BASE_DIR` | — | Server working base directory |
| `EBX_SERVER_DISABLED_GROUPS` | `DEV_TOOLS,BROWSER` | Disabled capability groups (comma-separated) |
| `EBX_PTY_PORT` | — | PTY terminal WebSocket port |
| `EBX_MAX_UPLOAD_SIZE` | — | Maximum upload file size |

### Deployment Related

Deploy reads the LLM profile from the same keys as the rest of the SDK:

| Environment Variable | Description |
|---------------------|-------------|
| `EBX_LLM_API_KEY` | LLM API key |
| `EBX_LLM_BASE_URL` | LLM base URL |
| `EBX_LLM_MODEL` | LLM model name |

---

## config.toml Configuration

Config file path: `~/.ebx/config.toml`

```toml
[core]
provider = "alicloud-express"   # default provider (ebx provider default NAME)

[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain = "cn-hangzhou.e2b.fc.aliyuncs.com"
http_timeout = 30.0
max_retries = 3

[providers.alicloud-express]
region = "cn-hangzhou"

[providers.my-cloud]            # a plugin's own scoped keys
endpoint = "https://sandbox.my-cloud.example"   # key declared by that plugin

[shortcuts]
init = "template init"          # command path, not "ebx template init"
ps   = "sandbox process list"
```

Lookup order for a key inside `config.toml`: `[providers.<id>].<key>`, then `[transport].<key>`. The key name in the file is the config key in the tables above.

`[shortcuts]` (top-level command aliases) is read only by the `ebx` CLI and ignored by the SDK. Its rules (the value has no `ebx` prefix, a bad line is skipped at startup) are in the [CLI reference](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/cli-reference.md#shortcut-aliases-shortcutsalias).

---

## TransportConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | `"alicloud-express"` | Active provider id |
| `sandbox_base_url` | `str` | `"https://api.cn-hangzhou.e2b.fc.aliyuncs.com"` | Platform API URL |
| `sandbox_domain` | `str` | `"cn-hangzhou.e2b.fc.aliyuncs.com"` | Data plane domain |
| `region` | `str` | `"cn-hangzhou"` | Region (`alicloud-express`) |
| `sandbox_api_key` | `str \| None` | `None` | Sandbox API key |
| `access_key_id` | `str \| None` | `None` | Alibaba Cloud AK |
| `access_key_secret` | `str \| None` | `None` | Alibaba Cloud SK |
| `provider_options` | `dict` | `{}` | Provider-scoped values: extra built-in keys such as `acr_*`, or a plugin's own keys |
| `http_timeout` | `float` | `30.0` | HTTP request timeout (seconds, ≥1.0) |
| `max_connections` | `int` | `100` | Maximum connections |
| `max_keepalive_connections` | `int` | `20` | Maximum keep-alive connections |
| `keepalive_expiry` | `float` | `30.0` | Keep-alive connection expiry (seconds) |
| `http2` | `bool` | `True` | Whether to enable HTTP/2 |
| `ws_ping_interval` | `float` | `30.0` | WebSocket ping interval (seconds) |
| `max_retries` | `int` | `3` | Maximum retry count |
| `retry_base_delay` | `float` | `1.0` | Retry base delay (seconds) |

The constructor and `load_config(...)` take these field names.

### Automatic Region Derivation

When the base URL is not set by an argument or a process environment variable, but a region is, the built-in provider derives:

```text
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

Values read from `.env` files or `config.toml` count as defaults, so a base URL stored there is kept and the other value is still derived from the region. This is the historical behaviour and is unchanged. Providers other than `alicloud-express` have no region derivation unless their manifest declares one.

### Inspecting the result

```python
from easy_sandbox.transport.config import explain_config

explain_config()   # {"sandbox_api_key": {"value": "****3dc1", "source": "environ", "name": "EBX_SANDBOX_API_KEY", "secret": True}, ...}
```

`explain_config()` tells you which layer (`override`, `environ`, `dotenv`, `toml`, `derived`, `default`) and which variable decided each key; secrets are masked. The `name` is the one environment variable for that key.

---

## SDK Parameter Override

Pass parameters directly in code (highest priority):

```python
from easy_sandbox.api.sandbox import Sandbox

sandbox = await Sandbox.create(
    sandbox_api_key="REPLACE_ME",
    sandbox_base_url="https://api.cn-beijing.e2b.fc.aliyuncs.com",
    access_key_id="REPLACE_ME",
    access_key_secret="REPLACE_ME",
)

# Pick another provider for this call; options are provider-scoped
sandbox = await Sandbox.create(provider="my-cloud", provider_options={"endpoint": "https://sandbox.my-cloud.example"})
```

See [Providers](../guide/providers.md).

---

## .env File

The SDK reads both `.env` files. Each is its own layer, so they merge per key:

1. `.env` in the current directory (wins when it sets the key)
2. `~/.ebx/.env` (used for any key the project file does not set)

`.env` file format. Use the one variable for each key:

```bash
EBX_SANDBOX_API_KEY=your-api-key
ALIBABA_CLOUD_REGION_ID=cn-beijing
EBX_PROVIDER=alicloud-express
```

The `ebx config set sandbox_api_key <KEY>` command saves the API Key to `~/.ebx/.env` as `EBX_SANDBOX_API_KEY` (file permissions 600). `github_token` is stored as `GITHUB_TOKEN`. Access keys are stored as `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.

---

## Configuration File Locations Summary

| File | Path | Description |
|------|------|-------------|
| config.toml | `~/.ebx/config.toml` | SDK extended configuration (`[core]`, `[transport]`, `[providers.<id>]`, `[shortcuts]`) |
| .env | `~/.ebx/.env` | Authentication credentials (written by auth login / `ebx config set`) |
| .env (local) | `./.env` | Project-level environment variables |
| Session storage | `~/.ebx/sessions/*.json` | Local session data |
| Template cache | `~/.ebx/templates/` | Installed templates |
| Provider plugins | `~/.ebx/providers/<id>/` | Installed provider plugins (code, `ebx-provider.toml`, `.ebx-install.json` receipt; `data/` is the plugin's own state) |

---

## Related: the ebx CLI

Reading and writing this configuration from the command line is a CLI feature: `ebx config list|get|set|init`, the keys accepted by `ebx config get|set`, and the `EBX_ACTIVITY_LINES` display variable. They are documented in the CLI repository: [CLI Configuration](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/configuration.md); provider-aware keys are in its [Providers and credentials CLI spec](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/design/providers-and-credentials-cli.md).
