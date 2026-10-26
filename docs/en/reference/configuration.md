# Configuration Reference

This guide describes asynchronous `ProviderSandbox` provider extensions. Root `Sandbox` and `AsyncSandbox` follow the pinned standard migration contract; see [Migrate from E2B](../guide/migrate-from-e2b.md).

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @agent-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

This document lists all Agent Sandbox configuration options, environment variables, default values, and priority rules.

---

## Configuration Priority

Configuration is loaded in the following priority order (highest to lowest):

```text
1. Code parameters (sandbox_api_key=, sandbox_base_url=, provider=, ...)   ← Highest
2. Process environment variables
3. ./.env                  (project file)
4. ~/.abx/.env             (user file)
5. ~/.abx/config.toml
6. Provider / built-in defaults                                           ← Lowest
```

Resolution is **layer first**. Each key has exactly one environment variable. The first layer that sets that variable wins.

Both `.env` files are separate layers, so `./.env` beats `~/.abx/.env` per key. A key that the project file does not set still comes from `~/.abx/.env`.

A blank or whitespace-only value does not count. It does not hide the next layer.

## Credential resolution

Every credential uses the layers above at the moment it is needed. `abx config list` shows the winner and labels it `(env)`, `(user)`, `(default)`, or `(not set)`.

Each key has one name. Product settings use `ABX_<KEY>`. A vendor that already publishes a variable keeps that variable: Alibaba Cloud access keys are `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`, the region is `ALIBABA_CLOUD_REGION_ID`, and the GitHub token is `GITHUB_TOKEN`. Template build (`ACR_*`, `team_id`) and template generation (`ABX_LLM_*`) settings belong to the `abx` CLI and are listed in its [configuration reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/configuration.md); the Python SDK does not read them.

| What you need | Key | Environment variable |
|---|---|---|
| Sandbox API key | `sandbox_api_key` | `ABX_SANDBOX_API_KEY` |
| Sandbox API base URL | `sandbox_base_url` | `ABX_SANDBOX_BASE_URL` |
| Data-plane domain | `sandbox_domain` | `ABX_SANDBOX_DOMAIN` |
| Region | `region` | `ALIBABA_CLOUD_REGION_ID` |
| Alibaba Cloud AK / SK | `access_key_id` / `access_key_secret` | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` |
| GitHub token | `github_token` | `GITHUB_TOKEN` |
| Default provider | `provider` | `ABX_PROVIDER` |

The same chain is what these calls read:

- `Sandbox.create` and the other SDK clients (`load_config`)
- natural-language `abx create` (the coding agent)
- `abx template install` / `abx template search` (GitHub token)
- `abx mcp install` (the sandbox API key copied into the editor config)

`abx mcp install` writes `ABX_SANDBOX_API_KEY` into the Cursor and Claude config. `ABX_SANDBOX_BASE_URL` and `ALIBABA_CLOUD_REGION_ID` are copied into the same file only when the process environment sets them. `abx mcp start` loads `~/.abx` again, so a region saved with `abx config set region` still applies when the editor starts the server.

`abx config list` marks a process variable as `(env)` and either file as `(user)`. The value in the table is the one the command will use.

### Provider scoping

The generic keys `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` belong to the built-in provider `alicloud-express`. A [provider plugin](../guide/providers.md) receives them only when its manifest lists them under `[core] inherit` **and** you consented to that when you installed it. Without this rule, switching `ABX_PROVIDER` would silently send your Alibaba Cloud key to a third-party process. LLM, GitHub and MCP keys are never delivered to a provider. Plugin-specific credentials are provider-scoped keys (`ABX_<PROVIDER>_API_KEY`, or `[providers.<id>]` in `config.toml`).

Resolving for provider `P` never reads `ABX_<Q>_*` or `[providers.Q]` for another provider `Q`.

---

Sandbox calls require `ABX_SANDBOX_API_KEY`; AK/SK settings configure separate official control-plane operations and cannot substitute for it. See [authentication migration](../guide/authentication.md).

## Environment Variables

Each row is the only environment variable for that key. `abx config set` writes that same name.

### Sandbox connection and tuning

| Environment variable | Config key | Description |
|---|---|---|
| `ABX_PROVIDER` | `provider` | Default provider id (default `alicloud-express`) |
| `ABX_SANDBOX_API_KEY` | `sandbox_api_key` | Sandbox API key |
| `ABX_SANDBOX_BASE_URL` | `sandbox_base_url` | Platform API URL |
| `ABX_SANDBOX_DOMAIN` | `sandbox_domain` | Data-plane domain |
| `ALIBABA_CLOUD_REGION_ID` | `region` | Region of the built-in provider |
| `ABX_HTTP_TIMEOUT` | `http_timeout` | HTTP timeout in seconds |
| `ABX_HTTP2` | `http2` | HTTP/2 on or off |
| `ABX_MAX_CONNECTIONS`, `ABX_MAX_KEEPALIVE_CONNECTIONS`, `ABX_KEEPALIVE_EXPIRY`, `ABX_WS_PING_INTERVAL` | same names, lower case | Pool, keep-alive and WebSocket tuning |
| `ABX_LOG_LEVEL` | `log_level` | SDK log level (default `WARNING`) |
| `ABX_DEFAULT_TEMPLATE` | `default_template` | Default template (MCP server) |

### Alibaba Cloud Express Edition (`alicloud-express`)

| Environment variable | Config key | Description |
|---|---|---|
| `ALICLOUD_ACCESS_KEY_ID` | `access_key_id` | Alibaba Cloud AccessKey ID |
| `ALICLOUD_ACCESS_KEY_SECRET` | `access_key_secret` | Alibaba Cloud AccessKey Secret |

### GitHub, templates, MCP

| Environment variable | Config key | Description |
|---|---|---|
| `GITHUB_TOKEN` | `github_token` | GitHub token for template downloads (CI: inject as a secret) |
| `ABX_TEMPLATE_INDEX_URL`, `ABX_TEMPLATE_DIR` | `template_index_url`, `template_dir` | Template index and directory (environment only) |
| `ABX_MCP_AUTH_TOKEN`, `ABX_MCP_ALLOWED_ORIGINS`, `ABX_MCP_RUNTIME_DIR` | `mcp_*` | MCP server (environment only) |

Keys marked "environment only" are read from the same layers but cannot be written with `abx config set`.

The SDK field for the sandbox key is `sandbox_api_key`. The SDK field for the base URL is `sandbox_base_url`. The SDK field for the data-plane host is `sandbox_domain`.

### One name per key

A key is read from its one environment variable and stored under that same name. `abx config set sandbox_api_key` writes `ABX_SANDBOX_API_KEY` to `~/.abx/.env`. `abx config set sandbox_base_url` writes `sandbox_base_url` in `[transport]`. `abx config set github_token` writes `GITHUB_TOKEN`. `abx config set region` writes `region` for the built-in provider; the environment variable for that key is `ALIBABA_CLOUD_REGION_ID`.

### Server-Side Environment Variables

The following environment variables are used for in-sandbox Server configuration:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ABX_SERVER_TOKEN` | — | Server authentication token |
| `ABX_SERVER_BASE_DIR` | `/home/user` | Directory every path-taking endpoint (including shell `cwd`) must stay under |
| `ABX_SERVER_ENABLED_GROUPS` | — | Comma list of groups to turn on, for example `agents,dev_tools`. The only group variable; there is none for turning groups off |
| `ABX_SERVER_POLICY` | — | Inline JSON policy document (same keys as the `server:` block) |
| `ABX_SERVER_POLICY_FILE` | — | Path to a policy JSON file |
| `ABX_PTY_PORT` | `9001` | PTY terminal WebSocket port |
| `ABX_MAX_UPLOAD_SIZE` | 100 MiB | Maximum decoded upload size |

### Build, deploy and template-generation keys

The `ACR_*`, `team_id` and `ABX_LLM_*` keys are declared by the `abx` CLI, which is the only component that builds or generates templates. The Python SDK is a runtime client and neither declares nor reads them.

---

## config.toml Configuration

Config file path: `~/.abx/config.toml`

```toml
[core]
provider = "alicloud-express"   # default provider (abx provider default NAME)

[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain = "cn-hangzhou.e2b.fc.aliyuncs.com"
http_timeout = 30.0

[providers.alicloud-express]
region = "cn-hangzhou"

[providers.my-cloud]            # a plugin's own scoped keys
endpoint = "https://sandbox.my-cloud.example"   # key declared by that plugin

[shortcuts]
init = "template init"          # command path, not "abx template init"
ps   = "sandbox process list"
```

Lookup order for a key inside `config.toml`: `[providers.<id>].<key>`, then `[transport].<key>`. The key name in the file is the config key in the tables above.

`[shortcuts]` (top-level command aliases) is read only by the `abx` CLI and ignored by the SDK. Its rules (the value has no `abx` prefix, a bad line is skipped at startup) are in the [CLI reference](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/cli-reference.md#shortcut-aliases-shortcutsalias).

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
| `provider_options` | `dict` | `{}` | Provider-scoped values: a plugin's own keys |
| `http_timeout` | `float` | `30.0` | HTTP request timeout (seconds, ≥1.0) |
| `max_connections` | `int` | `100` | Maximum connections |
| `max_keepalive_connections` | `int` | `20` | Maximum keep-alive connections |
| `keepalive_expiry` | `float` | `30.0` | Keep-alive connection expiry (seconds) |
| `http2` | `bool` | `True` | Whether to enable HTTP/2 |
| `ws_ping_interval` | `float` | `30.0` | WebSocket ping interval (seconds) |

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
from agent_sandbox.transport.config import explain_config

explain_config()   # {"sandbox_api_key": {"value": "****3dc1", "source": "environ", "name": "ABX_SANDBOX_API_KEY", "secret": True}, ...}
```

`explain_config()` tells you which layer (`override`, `environ`, `dotenv`, `toml`, `derived`, `default`) and which variable decided each key; secrets are masked. The `name` is the one environment variable for that key.

---

## SDK Parameter Override

`ProviderSandbox.create`, `connect` and `list` accept only `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` for these overrides. Control-plane `kill_by_id`, `get_info_by_id` and `set_timeout_by_id` accept the first two and do not need a data-plane domain. Their `_sync` variants use the same parameters. Standard `Sandbox` / `AsyncSandbox` retain their separate `ApiParams` contract.

Pass parameters directly in code (highest priority):

```python
from agent_sandbox import ProviderSandbox as Sandbox

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
2. `~/.abx/.env` (used for any key the project file does not set)

`.env` file format. Use the one variable for each key:

```bash
ABX_SANDBOX_API_KEY=your-api-key
ALIBABA_CLOUD_REGION_ID=cn-beijing
ABX_PROVIDER=alicloud-express
```

The `abx config set sandbox_api_key <KEY>` command saves the API Key to `~/.abx/.env` as `ABX_SANDBOX_API_KEY` (file permissions 600). `github_token` is stored as `GITHUB_TOKEN`. Access keys are stored as `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.

---

## Configuration File Locations Summary

| File | Path | Description |
|------|------|-------------|
| config.toml | `~/.abx/config.toml` | SDK extended configuration (`[core]`, `[transport]`, `[providers.<id>]`, `[shortcuts]`) |
| .env | `~/.abx/.env` | Authentication credentials (written by auth login / `abx config set`) |
| .env (local) | `./.env` | Project-level environment variables |
| Session storage | `~/.abx/sessions/*.json` | Local session data |
| Template cache | `~/.abx/templates/` | Installed templates |
| Provider plugins | `~/.abx/providers/<id>/` | Installed provider plugins (code, `abx-provider.toml`, `.abx-install.json` receipt; `data/` is the plugin's own state) |

---

## Related: the abx CLI

Reading and writing this configuration from the command line is a CLI feature: `abx config list|get|set|init`, the keys accepted by `abx config get|set`, and the `ABX_ACTIVITY_LINES` display variable. They are documented in the CLI repository: [CLI Configuration](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/configuration.md); provider-aware keys are in its [Providers and credentials CLI spec](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/design/providers-and-credentials-cli.md).

### Transport attempts

Builtin platform/envd HTTP performs one transport attempt. Provider-engine read recovery is separate. Applications that retry safe reads must bound attempts; reconcile an unknown write outcome before repeating a mutation.


Application HTTP clients share authentication regression vectors with CLI and Node consumers. SDK configuration remains through parameters and its existing environment/dotenv/configuration sources; there is no SDK setup wizard.
