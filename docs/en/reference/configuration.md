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

Resolution is **layer first**. The first layer that has a value under *any* of the key's names wins. Names are only compared inside one layer.

Inside one layer the name order is, most specific first:

1. the provider-scoped canonical name, `EBX_<PROVIDER>_<KEY>` (for example `EBX_ALICLOUD_EXPRESS_REGION`). Only keys a provider inherits from the core have this form;
2. the canonical name `EBX_<KEY>` (for example `EBX_SANDBOX_API_KEY`);
3. the **compat** names (E2B: `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN`) and the **native** names that other tools define (`ALICLOUD_ACCESS_KEY_ID`, `GITHUB_TOKEN`, `OPENAI_API_KEY`, ...);
4. the **legacy** Easy Sandbox names (`SANDBOX_API_KEY`, `SANDBOX_REGION`, `AccessKey`, `ACR_*`, ...).

Both `.env` files are separate layers, so `./.env` beats `~/.ebx/.env` per key. A key that the project file does not set still comes from `~/.ebx/.env`.

A blank or whitespace-only value does not count. It does not hide the next layer.

Every legacy name from earlier releases keeps working. The full list is in [Name aliases](#name-aliases). A **compat** name (`E2B_*`) or **native** name (`GITHUB_TOKEN`, `OPENAI_*`, `ALICLOUD_*`) is never deprecated.

> **Behaviour note.** Earlier releases merged `./.env` and `~/.ebx/.env` per exact variable name *before* applying name priority. With `./.env: SANDBOX_API_KEY=a` and `~/.ebx/.env: E2B_API_KEY=b` the result was `b`, which contradicted "`./.env` overrides `~/.ebx/.env`". The resolver is now layer first, so the project file wins (`a`). This corner case (different names for one key in both files) is the only observable change. `E2B_*` keeps its position ahead of `SANDBOX_*` in every layer.

## Credential resolution

Every credential uses the layers above at the moment it is needed. `ebx config list` shows the winner and labels it `(env)`, `(user)`, `(default)`, or `(not set)`.

Canonical names are `snake_case` keys, with `EBX_<KEY>` as the environment variable. Keys that belong to one provider carry the provider prefix, `EBX_<PROVIDER>_<KEY>` (provider id upper-cased, `-` becomes `_`).

| What you need | Canonical key / SDK argument | Canonical env var | Also accepted (same layer, lower priority) |
|---|---|---|---|
| Sandbox API key | `sandbox_api_key` | `EBX_SANDBOX_API_KEY` | `E2B_API_KEY` (compat), `SANDBOX_API_KEY` (legacy) |
| Sandbox API base URL | `sandbox_base_url` | `EBX_SANDBOX_BASE_URL` | `E2B_API_URL` (compat), `SANDBOX_API_BASE_URL` (legacy) |
| Data-plane domain | `sandbox_domain` | `EBX_SANDBOX_DOMAIN` | `E2B_DOMAIN` (compat) |
| Region (`alicloud-express`) | `region` | `EBX_ALICLOUD_EXPRESS_REGION` | `SANDBOX_REGION` (legacy) |
| Alibaba Cloud AK / SK (`alicloud-express`) | `access_key_id` / `access_key_secret` | `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID` / `..._ACCESS_KEY_SECRET` | `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` (native), `AccessKey` / `AccessSecret` (legacy) |
| ACR settings (`alicloud-express`) | `acr_namespace`, `acr_registry`, `acr_repo`, `acr_username`, `acr_password`, ... | `EBX_ALICLOUD_EXPRESS_ACR_<KEY>` | `ACR_NAMESPACE`, `ACR_REGISTRY`, ... (legacy) |
| GitHub token | `github_token` | `EBX_GITHUB_TOKEN` | `GITHUB_TOKEN` (native) |
| LLM API key | `llm_api_key` | `EBX_LLM_API_KEY` | `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY` (native), `EBX_QWEN_CODE_API_KEY` (legacy) |
| LLM base URL | `llm_base_url` | `EBX_LLM_BASE_URL` | `OPENAI_BASE_URL` (native) |
| LLM model | `llm_model` | `EBX_LLM_MODEL` | `OPENAI_MODEL` (native) |
| Default provider | `provider` | `EBX_PROVIDER` | none |

The complete list, with every alias and the SDK keyword argument that matches it, is in [Name aliases](#name-aliases).

`EBX_GITHUB_TOKEN` outranks `GITHUB_TOKEN` on purpose. CI platforms inject `GITHUB_TOKEN` automatically. A person who sets the more specific `EBX_GITHUB_TOKEN` means it.

The same chain is what these calls read:

- `Sandbox.create` and the other SDK clients (`load_config`)
- `Sandbox.deploy` (`resolve_llm_env`)
- natural-language `ebx create` (the coding agent)
- `ebx template install` / `ebx template search` (GitHub token)
- `ebx mcp install` (the sandbox API key copied into the editor config)

An older `EBX_QWEN_CODE_API_KEY` is still accepted as `llm_api_key` when the `llm_*` value is unset. It is a legacy name, so it comes after every other name in its layer.

`ebx mcp install` writes that sandbox API key into the Cursor and Claude config. `E2B_API_URL` and `SANDBOX_REGION` are copied into the same file only when the process environment sets them. `ebx mcp start` loads `~/.ebx` again, so a region saved with `ebx config set region` still applies when the editor starts the server.

`ebx config list` marks a process variable as `(env)` and either file as `(user)`. The value in the table is the one the command will use.

### Provider scoping

The generic keys `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` (and all their aliases, such as `E2B_API_KEY`) belong to the built-in provider `alicloud-express`. A [provider plugin](../guide/providers.md) receives them only when its manifest lists them under `[core] inherit` **and** you consented to that when you installed it. Without this rule, switching `EBX_PROVIDER` would silently send your Alibaba Cloud key to a third-party process. LLM, GitHub and MCP keys are never delivered to a provider. Plugin-specific credentials are provider-scoped keys (`EBX_<PROVIDER>_API_KEY`, or `[providers.<id>]` in `config.toml`).

Resolving for provider `P` never reads `EBX_<Q>_*` or `[providers.Q]` for another provider `Q`.

---

## Environment Variables

### Sandbox connection and tuning

| Canonical | Compat / native alias | Legacy alias | Config key | Description |
|---|---|---|---|---|
| `EBX_PROVIDER` | | | `provider` | Default provider id (default `alicloud-express`) |
| `EBX_SANDBOX_API_KEY` | `E2B_API_KEY` | `SANDBOX_API_KEY` | `sandbox_api_key` | Sandbox API key |
| `EBX_SANDBOX_BASE_URL` | `E2B_API_URL` | `SANDBOX_API_BASE_URL` | `sandbox_base_url` | Platform API URL |
| `EBX_SANDBOX_DOMAIN` | `E2B_DOMAIN` | | `sandbox_domain` | Data-plane domain |
| `EBX_ALICLOUD_EXPRESS_REGION` | | `SANDBOX_REGION` | `region` | Region of the built-in provider |
| `EBX_HTTP_TIMEOUT` | | `SANDBOX_HTTP_TIMEOUT` | `http_timeout` | HTTP timeout in seconds |
| `EBX_HTTP2` | | | `http2` | HTTP/2 on or off |
| `EBX_MAX_RETRIES` | | | `max_retries` | Maximum retry count |
| `EBX_MAX_CONNECTIONS`, `EBX_MAX_KEEPALIVE_CONNECTIONS`, `EBX_KEEPALIVE_EXPIRY`, `EBX_WS_PING_INTERVAL`, `EBX_RETRY_BASE_DELAY` | | | same names, lower case | Pool, keep-alive, WebSocket and back-off tuning |
| `EBX_LOG_LEVEL` | | `SANDBOX_LOG_LEVEL` | `log_level` | SDK log level (default `WARNING`) |
| `EBX_DEFAULT_TEMPLATE` | | `SANDBOX_TEMPLATE`, then `EBX_TEMPLATE` | `default_template` | Default template (MCP server) |

### Alibaba Cloud Express Edition (`alicloud-express`)

| Canonical | Native alias | Legacy alias | Config key | Description |
|---|---|---|---|---|
| `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID` | `ALICLOUD_ACCESS_KEY_ID` | `AccessKey` | `access_key_id` | Alibaba Cloud AccessKey ID |
| `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_SECRET` | `ALICLOUD_ACCESS_KEY_SECRET` | `AccessSecret` | `access_key_secret` | Alibaba Cloud AccessKey Secret |
| `EBX_ALICLOUD_EXPRESS_ACR_NAMESPACE` | | `ACR_NAMESPACE` | `acr_namespace` | ACR namespace |
| `EBX_ALICLOUD_EXPRESS_ACR_REGISTRY` | | `ACR_REGISTRY` | `acr_registry` | ACR registry host |
| `EBX_ALICLOUD_EXPRESS_ACR_REPO` | | `ACR_REPO` | `acr_repo` | ACR repository |
| `EBX_ALICLOUD_EXPRESS_ACR_USERNAME` | | `ACR_USERNAME` | `acr_username` | ACR user name |
| `EBX_ALICLOUD_EXPRESS_ACR_PASSWORD` | | `ACR_PASSWORD` | `acr_password` | ACR password |
| `EBX_ALICLOUD_EXPRESS_ACR_INSTANCE_ID` | | `ACREE_INSTANCE_ID` | `acr_instance_id` | ACR Enterprise Edition instance |
| `EBX_ALICLOUD_EXPRESS_ACR_VPC_ID` | | `ACR_VPC_ID` | `acr_vpc_id` | ACR VPC |
| `EBX_ALICLOUD_EXPRESS_ACR_VSWITCH_IDS` | | `ACR_VSWITCH_IDS` | `acr_vswitch_ids` | ACR vSwitch ids (comma separated) |
| `EBX_ALICLOUD_EXPRESS_ACR_SECURITY_GROUP_ID` | | `ACR_SECURITY_GROUP_ID` | `acr_security_group_id` | ACR security group |
| `EBX_ALICLOUD_EXPRESS_TEAM_ID` | `E2B_TEAM_ID` (compat) | `TEAM_ID` | `team_id` | Team id |

### LLM, GitHub, templates, MCP

| Canonical | Native / legacy alias | Config key | Description |
|---|---|---|---|
| `EBX_LLM_API_KEY` | `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`; legacy `EBX_QWEN_CODE_API_KEY` | `llm_api_key` | LLM API key (store with `ebx config set llm_api_key`) |
| `EBX_LLM_BASE_URL` | `OPENAI_BASE_URL`; legacy toml `qwen_code_base_url` | `llm_base_url` | LLM base URL |
| `EBX_LLM_MODEL` | `OPENAI_MODEL`; legacy toml `qwen_code_model` | `llm_model` | LLM model name |
| `EBX_GITHUB_TOKEN` | `GITHUB_TOKEN` | `github_token` | GitHub token for template downloads (CI: inject as a secret) |
| `EBX_TEMPLATE_INDEX_URL`, `EBX_TEMPLATE_DIR` | | `template_index_url`, `template_dir` | Template index and directory (environment only) |
| `EBX_MCP_AUTH_TOKEN`, `EBX_MCP_ALLOWED_ORIGINS`, `EBX_MCP_RUNTIME_DIR` | | `mcp_*` | MCP server (environment only) |

Keys marked "environment only" are read from the same layers but cannot be written with `ebx config set`.

When both `E2B_API_KEY` and `SANDBOX_API_KEY` are present, `E2B_API_KEY` takes priority, and `EBX_SANDBOX_API_KEY` beats both. The SDK field is `sandbox_api_key`; the old field name `api_key` still works as a constructor / keyword argument.

For the LLM API key the order inside one layer is `EBX_LLM_API_KEY`, then `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`. Any of those in the process environment wins over `./.env`, which wins over `~/.ebx/.env`. The same holds for the LLM base URL and model.

### Name aliases

Aliases come in four kinds. Only **legacy** aliases are reported by `audit_config()` / `ebx config check`.

| Kind | Meaning | Example | Reported by audit |
|---|---|---|---|
| canonical | The documented name | `EBX_SANDBOX_API_KEY` | no |
| compat | E2B-compatible name, kept so existing E2B code works | `E2B_API_KEY` | no |
| native | Name defined by another tool or vendor | `ALICLOUD_ACCESS_KEY_ID`, `GITHUB_TOKEN`, `OPENAI_API_KEY` | no |
| legacy | Earlier Easy Sandbox name | `SANDBOX_API_KEY`, `AccessKey`, `ACR_NAMESPACE` | yes |

Using a legacy name never changes stdout or stderr. To see what you use, run `python -c "from easy_sandbox.transport.config import audit_config; print(audit_config())"` (names only, never values). Set `EBX_WARN_DEPRECATED=1` to get one `DeprecationWarning` per legacy constructor keyword (`api_key=`, `api_url=`, `domain=`) per process. No alias is removed in 0.x.

SDK constructor / keyword aliases:

| Canonical | Accepted legacy keyword |
|---|---|
| `sandbox_api_key` | `api_key` |
| `sandbox_base_url` | `api_url`, `api_base_url` |
| `sandbox_domain` | `domain` |

The properties `TransportConfig.api_key`, `.api_url` and `.domain` stay available as read and write aliases.

### Migrating stored configuration

Phase 1 (this release) keeps writing the old storage names so that older tools still read the same files: `ebx config set sandbox_api_key` writes `E2B_API_KEY` to `~/.ebx/.env`, and the base URL is stored as `api_url` in `[transport]`. `migrate` rewrites everything to canonical names and sets `[core] config_format = 2`.

```python
from easy_sandbox.transport.config import plan_migration, apply_migration

for step in plan_migration():       # dry run, no values printed
    print(step)
apply_migration()                   # writes canonical names; keeps config.toml.bak / .env.bak (mode 600)
```

After migration, older Easy Sandbox releases no longer see the moved keys. Compat names (`E2B_*`) are only renamed in files; they keep working in the process environment forever.

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

| Environment Variable | Description |
|---------------------|-------------|
| `BAILIAN_CODING_PLAN_API_KEY` | Bailian Coding Agent API Key (for deploy) |
| `DASHSCOPE_API_KEY` | DashScope API Key (for deploy) |
| `OPENAI_API_KEY` | OpenAI-compatible API Key (for deploy) |

---

## config.toml Configuration

Config file path: `~/.ebx/config.toml`

```toml
[core]
provider = "alicloud-express"   # default provider (ebx provider default NAME)
# config_format = 2             # set by `config migrate`

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

Lookup order for a key inside `config.toml`: `[providers.<id>].<key>`, then `[transport].<key>`, then `[transport].<legacy name>` (`api_url`, `api_base_url`, `domain`, `api_key`, `qwen_code_*`). Flat legacy keys at the top level are read only when the file has no `[transport]` table. Files written by earlier releases (`[transport] api_url = ...`, `region = ...`) keep working unchanged.

`[shortcuts]` (top-level command aliases) is read only by the `ebx` CLI and ignored by the SDK. Its rules (the value has no `ebx` prefix, a bad line is skipped at startup) are in the [CLI reference](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/cli-reference.md#shortcut-aliases-shortcutsalias).

---

## TransportConfig Fields

| Field | Legacy name | Type | Default | Description |
|-------|-------------|------|---------|-------------|
| `provider` | | `str` | `"alicloud-express"` | Active provider id |
| `sandbox_base_url` | `api_url`, `api_base_url` | `str` | `"https://api.cn-hangzhou.e2b.fc.aliyuncs.com"` | Platform API URL |
| `sandbox_domain` | `domain` | `str` | `"cn-hangzhou.e2b.fc.aliyuncs.com"` | Data plane domain |
| `region` | | `str` | `"cn-hangzhou"` | Region (`alicloud-express`) |
| `sandbox_api_key` | `api_key` | `str \| None` | `None` | Sandbox API key |
| `access_key_id` | | `str \| None` | `None` | Alibaba Cloud AK |
| `access_key_secret` | | `str \| None` | `None` | Alibaba Cloud SK |
| `provider_options` | | `dict` | `{}` | Provider-scoped values: extra built-in keys such as `acr_*`, or a plugin's own keys |
| `http_timeout` | | `float` | `30.0` | HTTP request timeout (seconds, ≥1.0) |
| `max_connections` | | `int` | `100` | Maximum connections |
| `max_keepalive_connections` | | `int` | `20` | Maximum keep-alive connections |
| `keepalive_expiry` | | `float` | `30.0` | Keep-alive connection expiry (seconds) |
| `http2` | | `bool` | `True` | Whether to enable HTTP/2 |
| `ws_ping_interval` | | `float` | `30.0` | WebSocket ping interval (seconds) |
| `max_retries` | | `int` | `3` | Maximum retry count |
| `retry_base_delay` | | `float` | `1.0` | Retry base delay (seconds) |

The legacy names are accepted by the constructor and by `load_config(...)`, and remain readable and writable as properties (`config.api_key`, `config.api_url`, `config.domain`).

### Automatic Region Derivation

When the base URL is not set by an argument or a process environment variable, but a region is, the built-in provider derives:

```text
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

Values read from `.env` files or `config.toml` count as defaults, so a base URL stored there is kept and the other value is still derived from the region. This is the historical behaviour and is unchanged. Providers other than `alicloud-express` have no region derivation unless their manifest declares one.

### Inspecting the result

```python
from easy_sandbox.transport.config import explain_config, audit_config

explain_config()   # {"sandbox_api_key": {"value": "****3dc1", "source": "environ", "name": "E2B_API_KEY", "secret": True}, ...}
audit_config()     # [{"where": "env", "name": "SANDBOX_API_KEY", "canonical_key": "sandbox_api_key",
                   #   "canonical_name": "EBX_SANDBOX_API_KEY", "kind": "legacy"}, ...]
```

`explain_config()` tells you which layer (`override`, `environ`, `dotenv`, `toml`, `derived`, `default`) and which name decided each key; secrets are masked. `audit_config()` lists only legacy names, never values.

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
sandbox = await Sandbox.create(provider="my-cloud", provider_options={"api_key": "REPLACE_ME"})
```

The old keyword names `api_key=`, `api_url=` and `domain=` are still accepted and mean exactly the same. Passing a canonical and a legacy keyword with different values for one setting raises `ValueError`. See [Providers](../guide/providers.md).

---

## .env File

The SDK reads both `.env` files. Each is its own layer, so they merge per key:

1. `.env` in the current directory (wins when it sets the key)
2. `~/.ebx/.env` (used for any key the project file does not set)

`.env` file format. Any accepted name works; canonical names are recommended for new files:

```bash
EBX_SANDBOX_API_KEY=your-api-key
EBX_ALICLOUD_EXPRESS_REGION=cn-beijing
EBX_PROVIDER=alicloud-express
```

`E2B_API_KEY=...` and `SANDBOX_REGION=cn-beijing` in the same file mean the same thing.

The `ebx config set sandbox_api_key <KEY>` command saves the API Key to `~/.ebx/.env` (file permissions 600). Credential keys such as `github_token` (mapped to `GITHUB_TOKEN`) are stored the same way.

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

Reading and writing this configuration from the command line is a CLI feature: `ebx config list|get|set|init`, the keys accepted by `ebx config get|set`, the `EBX_ACTIVITY_LINES` display variable, and `ebx config check` / `ebx config migrate` (the CLI forms of `audit_config()` and `apply_migration()`, specified in [Providers and credentials](../design/providers-and-credentials.md)). They are documented in the CLI repository: [CLI Configuration](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/reference/configuration.md); the planned provider-aware grammar is in its [Providers and credentials CLI spec](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/design/providers-and-credentials-cli.md).
