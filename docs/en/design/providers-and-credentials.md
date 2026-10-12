# Providers and Credentials — Naming Scheme and Provider Plugin Architecture

> **Status**: Accepted (design reviewed in two adversarial rounds, see [providers-and-credentials-review.md](providers-and-credentials-review.md)) · **Scope**: Python SDK (`client-sdk`) and the Node.js `ebx` CLI · **CLI-facing spec**: `cli/docs/design/providers-and-credentials-cli.md`
>
> **Compatibility rule for everything below**: every old name, file layout and behaviour keeps working. This document only *adds* canonical names and a provider layer. Nothing is removed in 0.x.

---

## 0. Goals, non-goals

**Goals**

1. One coherent naming scheme for every credential / configuration key, in every surface: `config.toml`, `~/.ebx/.env`, `ebx config set/get`, environment variables, SDK `TransportConfig` fields and `Sandbox.*` keyword arguments, CLI flags.
2. A documented precedence story and a complete alias table. Old names keep working everywhere.
3. A provider abstraction so that backends other than Alibaba Cloud can be added later by **plugins**, installed with `ebx provider install <path-or-git-url>` (CLI) or `python -m easy_sandbox.providers install ...` (SDK-only users), selectable per command (`--provider`), per process (`EBX_PROVIDER`), per project (`./.env`), per user (config), and per SDK call (`Sandbox.create(provider=...)`).
4. The built-in provider stays the default and is presented as **Alibaba Cloud Express Edition (阿里云极速版)** with the stable id `alicloud-express`.

**Non-goals (v1)**

* Running untrusted plugin code in a hard sandbox (cross-platform it is not achievable; we do consent + pinning + integrity + env scrubbing instead, see §8).
* A public plugin registry / marketplace (the manifest has a reserved `source` slot; v1 installs from a directory or a git URL only).
* Renaming `EBX_SERVER_*`, `EBX_PTY_PORT`, `EBX_MAX_UPLOAD_SIZE` (in-sandbox server variables baked into deployed images).
* Removing any alias.

---

## 1. Inventory (as of `b15b88f` + the split)

Sources scanned: `transport/config.py`, `transport/auth.py`, `models/config.py`, `models/errors.py`, `api/{sandbox,deploy,docker_builder,image,fc_template}.py`, `declarative/decorator.py`, `agent/{mcp,mcp_http}.py`, `utils/{github_token,registry,template_index,logging}.py`, the original Python CLI (`cli/commands/config_cmd.py`, `template.py`, `sandbox.py`, `mcp.py`, `cli/region.py`, `cli/main.py`), `agent/qwen_code.py`, `.env.example`, and the docs (`reference/configuration.md`, `guide/environment-variables.md`, `guide/authentication.md`).

### 1.1 Sandbox control plane / transport

| Concept | `ebx config` key | config.toml (`[transport]`) | Env vars (priority order, process env, `./.env`, `~/.ebx/.env`) | SDK field / kwarg | CLI flag |
|---|---|---|---|---|---|
| Sandbox API key | `sandbox_api_key` (alias `api_key`) | `api_key` (legacy, read) | `E2B_API_KEY` > `SANDBOX_API_KEY`; `config set` writes `E2B_API_KEY` to `~/.ebx/.env` | `api_key` | `--api-key` (`mcp install`, `mcp start`) |
| Platform base URL | `api_url` | `api_url` (`api_base_url` legacy) | `E2B_API_URL` > `SANDBOX_API_BASE_URL` | `api_url` (`api_base_url` accepted by `load_config`) | `--api-url` (`mcp`) |
| Data-plane domain | `domain` | `domain` | `E2B_DOMAIN` | `domain` | `--domain` (`mcp`) |
| Region | `region` | `region` | `SANDBOX_REGION` | `region` (`load_config` only) | `--region/-r` (command-level) |
| HTTP timeout | `http_timeout` | `http_timeout` | `SANDBOX_HTTP_TIMEOUT` | `http_timeout` | — |
| HTTP/2 | `http2` | `http2` | — | `http2` | — |
| Max retries | `max_retries` | `max_retries` | — | `max_retries` | — |
| Pool/keep-alive/WS/backoff | — | `max_connections`, `max_keepalive_connections`, `keepalive_expiry`, `ws_ping_interval`, `retry_base_delay` | — | same | — |
| Sandbox TTL | — | — | — | `Sandbox.create(timeout=)` | `--timeout/-t` (global, default 300; **not** an HTTP timeout) |
| Default template | — | — | `SANDBOX_TEMPLATE` > `EBX_TEMPLATE` (MCP only) | `GlobalConfig.default_template` | `--template` |
| Log level | — | — | `SANDBOX_LOG_LEVEL` | — | `--log-level`, `--verbose` |

### 1.2 Alibaba Cloud (provider-specific)

| Concept | `ebx config` key | Storage | Env vars | SDK | CLI flag |
|---|---|---|---|---|---|
| AccessKey ID | `access_key_id` | `~/.ebx/.env` | `ALICLOUD_ACCESS_KEY_ID` > `AccessKey` | `access_key_id` | — |
| AccessKey Secret | `access_key_secret` | `~/.ebx/.env` | `ALICLOUD_ACCESS_KEY_SECRET` > `AccessSecret` | `access_key_secret` | — |
| ACR namespace | `acr_namespace` | `~/.ebx/.env` | `ACR_NAMESPACE` | `ACRConfig.namespace` | `--acr-namespace` |
| ACR registry | — | — | `ACR_REGISTRY` (process env only) | `ACRConfig.registry` | `--acr-registry` |
| ACR repo | — | — | `ACR_REPO` | `ACRConfig.repo` | `--acr-repo` |
| ACR username / password | — | — | `ACR_USERNAME`, `ACR_PASSWORD` | `ACRConfig.username/password` | `--acr-username`, `--acr-password` |
| ACR EE instance | — | — | `ACREE_INSTANCE_ID` | `ACRConfig.acree_instance_id` | `--acree-instance-id` |
| ACR EE network | — | — | `ACR_VPC_ID`, `ACR_VSWITCH_IDS`, `ACR_SECURITY_GROUP_ID` | `ACRConfig.vpc_id` ... | `--vpc-id`, `--vswitch-ids`, `--security-group-id` |
| Team id | — | — | `TEAM_ID` > `E2B_TEAM_ID` (flag env only) | — | `--team-id` |

### 1.3 LLM / coding agent (provider-independent)

| Concept | Key | Env vars (priority) | SDK |
|---|---|---|---|
| LLM API key | `llm_api_key` (stored as `EBX_LLM_API_KEY` in `~/.ebx/.env`; a legacy `[transport] llm_api_key` is still read) | `EBX_LLM_API_KEY` > `BAILIAN_CODING_PLAN_API_KEY` > `DASHSCOPE_API_KEY` > `OPENAI_API_KEY` > `EBX_QWEN_CODE_API_KEY` (legacy) | `Sandbox.deploy(llm_api_key=)` |
| LLM base URL | `llm_base_url` (legacy toml `qwen_code_base_url`) | `EBX_LLM_BASE_URL` > `OPENAI_BASE_URL` | `openai_base_url=` |
| LLM model | `llm_model` (legacy toml `qwen_code_model`) | `EBX_LLM_MODEL` > `OPENAI_MODEL` | `openai_model=` |
| Removed keys | `qwen_code_api_key`, `qwen_code_base_url`, `qwen_code_model` (`config get/set` name the replacement) | `EBX_QWEN_CODE_API_KEY` still read | — |
| Agent tuning | — | `EBX_QWEN_CODE_BIN`, `EBX_QWEN_RESEARCH_TIMEOUT`, `EBX_QWEN_CODEGEN_TIMEOUT` | — |

### 1.4 Integrations, tooling, UI

| Concept | Key | Env | Notes |
|---|---|---|---|
| GitHub token | `github_token` (`~/.ebx/.env` as `GITHUB_TOKEN`) | `GITHUB_TOKEN` | flag `--token` (template install/search/update). `.env.example` mentions `SANDBOX_GITHUB_TOKEN` — **no code ever read it** (documentation bug, not an alias). |
| Template index URL | — | `EBX_TEMPLATE_INDEX_URL` | `utils/template_index.py` |
| Template dir | — | `EBX_TEMPLATE_DIR` | CLI `template build` argument |
| Team id | see 1.2 | | |
| MCP server | — | `EBX_MCP_AUTH_TOKEN`, `EBX_MCP_ALLOWED_ORIGINS`, `EBX_MCP_RUNTIME_DIR`, plus `E2B_API_KEY/E2B_API_URL/E2B_DOMAIN/SANDBOX_*` | `agent/mcp*.py`, `ebx mcp install/start` |
| CLI display | — | `EBX_ACTIVITY_LINES`, `EBX_DISCOVER_COMMANDS` | not stored by `ebx config` |
| Shortcuts | `shortcuts`, `shortcuts.<name>` | — | `[shortcuts]` table of `config.toml` |
| Secret store | — | — | `~/.ebx/secrets.json` (SDK `SecretStore`, 0600) — not a config surface |

### 1.5 In-sandbox server (`easy-sandbox-server`) — out of scope for renames

`EBX_SERVER_TOKEN`, `EBX_SERVER_BASE_DIR`, `EBX_SERVER_DISABLED_GROUPS`, `EBX_PTY_PORT`, `EBX_MAX_UPLOAD_SIZE`. They are runtime variables of container images that already exist in the wild; they follow the `EBX_` prefix and are left unchanged.

### 1.6 External / standard variables the tools honour (never renamed)

`CI`, `GITHUB_ACTIONS`, `GITLAB_CI`, `JENKINS_URL`, `NO_COLOR`, `TERM`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `DOCKER_BUILDKIT`, `HOME`, `APPDATA`, `COMSPEC`.

### 1.7 Other configuration surfaces found in the review (round 1)

| Surface | Names | Treatment |
|---|---|---|
| `sandbox.yaml` (`SandboxDeclarativeConfig`) and `@sandbox(...)` | `template`, `timeout`, `envs`, `cpu`, `memory`, `api_key`, `api_url`, `domain` | gain `provider`, `provider_options`, canonical `sandbox_*` kwargs; old kwargs unchanged |
| `GlobalConfig` (`models/config.py`, exported, unused by the loaders) | `api_key`, `api_url`, `domain`, `region`, `timeout` (sandbox TTL, **not** `http_timeout`), `max_retries`, `secure`, `log_level`, `default_template` | aligned to the same canonical names with legacy aliases; stays a plain data model |
| Session store (`~/.ebx/sessions/*.json`, `SessionInfo`) | `api_url`, `domain`, `envd_access_token` | gains an optional `provider` (default `""` = built-in) so a re-attached session talks to the same provider |
| `Sandbox.create(secure=, request_timeout=, timeout=)` | per-call options | unchanged (not credentials) |
| Coding-agent backend id (`qwen-code`, `DEFAULT_CODING_AGENT`) | — | a *coding agent* is not a *provider*; kept apart (see glossary) |
| `~/.qwen/settings.json` | agent-owned credential file the Qwen Code CLI reads | external file, never written or renamed by ebx |
| BYO-agent variables forwarded into sandboxes | `ANTHROPIC_API_KEY`, `QODER_PERSONAL_ACCESS_TOKEN`, `OPENAI_API_KEY`… | in-sandbox agent credentials, forwarded as-is; not ebx config |
| Documentation-only names | `SANDBOX_TIMEOUT` (sdk-api-design.md), `SANDBOX_GITHUB_TOKEN` (`.env.example`) | **never read by any code**; not aliases; documentation fixed |
| Developer scripts | `ACR_TAG`, `EBX_CATALOG_DIR`, `EBX_TEMPLATES_CACHE`, `FC_HTTP_TRIGGER_URL` (placeholder) | `scripts/` only; out of scope |

**Glossary (terms that must not be mixed up).** *Provider*: a backend that creates and runs sandboxes (`alicloud-express`, a plugin). *Feature*: something a provider implements (§7.2). *Template capability*: what a sandbox *image* serves (`shell`, `files`, `code`, `terminal`, `ports`; `models/template.py`). *Coding agent*: the LLM CLI used for natural-language template generation (`qwen-code`). *Core key*: provider-independent configuration key. *Scoped key*: declared by one provider.

### 1.8 Inconsistencies found (what the scheme fixes)

1. `sandbox_api_key` is prefixed but the matching URL is bare `api_url` / env `E2B_API_URL`; domain is bare `domain`.
2. Four different env-prefix families (`E2B_*`, `SANDBOX_*`, `ALICLOUD_*`/`AccessKey`, `EBX_*`) with no rule which one a new key belongs to.
3. `http2` and `max_retries` can only be set in `config.toml`; there is no env var, while `http_timeout` has one.
4. The same SDK concept has different names per surface: `api_key` (SDK) vs `sandbox_api_key` (CLI key) vs `E2B_API_KEY` (env) vs `--api-key`.
5. Layer order is not uniform: `load_config` merges `./.env` and `~/.ebx/.env` first and then applies name priority (so `~/.ebx/.env: E2B_API_KEY` beats `./.env: SANDBOX_API_KEY`), contradicting the documented "`./.env` overrides `~/.ebx/.env`"; `resolve_llm_env` is layer-first. See §4.3.
6. ACR keys other than `acr_namespace` are only readable from the process environment / flags (`.env.example` says so) while the namespace honours `.env`.
7. `SANDBOX_TEMPLATE` beats `EBX_TEMPLATE` in MCP (reverse of the usual specific-beats-generic intuition).
8. `.env.example` documents a variable (`SANDBOX_GITHUB_TOKEN`) nothing reads.

---

## 2. Naming principles

1. **Keys are `snake_case`, one canonical name per concept, identical in every surface.** The config key, the SDK field, the keyword argument and the flag (kebab-cased) are the same word: `sandbox_base_url` / `--sandbox-base-url`.
2. **Prefix = what the value is about.** `sandbox_*` for the sandbox control/data plane (generic, protocol level); `llm_*` for the LLM profile; `acr_*` for the container registry; `mcp_*` for the MCP server; `http_*` for HTTP client tuning; bare words for provider-scoped keys inside their provider namespace (`region`, `access_key_id`).
3. **Canonical environment variable = `EBX_` + `UPPER(key)`** (`sandbox_api_key` → `EBX_SANDBOX_API_KEY`). Provider-scoped: `EBX_` + `UPPER(provider_id with - → _)` + `_` + `UPPER(key)` (`EBX_ALICLOUD_EXPRESS_REGION`). The mapping is mechanical, so a new key never needs a naming debate. (The LLM names `EBX_LLM_*`, `EBX_MCP_*`, `EBX_TEMPLATE_*` already follow it.)
4. **Four alias classes**, each with a different lifecycle:

| Class | Meaning | Examples | Lifecycle |
|---|---|---|---|
| `canonical` | The documented name | `sandbox_api_key`, `EBX_SANDBOX_API_KEY` | — |
| `compat` | Kept for **E2B protocol compatibility** (E2B tooling and docs set these) | `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN`, `E2B_TEAM_ID` | **Never deprecated** |
| `native` | Third-party/vendor standard name users already export for other tools | `ALICLOUD_ACCESS_KEY_ID/SECRET`, `GITHUB_TOKEN`, `OPENAI_*`, `DASHSCOPE_API_KEY` | **Never deprecated** |
| `legacy` | ebx-invented older names | `SANDBOX_API_KEY`, `SANDBOX_API_BASE_URL`, `SANDBOX_REGION`, `SANDBOX_HTTP_TIMEOUT`, `AccessKey`, `AccessSecret`, `ACR_*`, `api_url`, `domain`, `api_key`, `EBX_QWEN_CODE_API_KEY` | Documented as legacy; **still accepted indefinitely in 0.x**; opt-in warnings (§6) |

5. **Provider scoping.** Keys are either *core* (provider-independent: `provider`, `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, `http_*`, `max_retries`, `llm_*`, `github_token`, `mcp_*`, ...) or *provider-scoped* (declared by a provider's config schema: `region`, `access_key_id`, `access_key_secret`, `acr_*`, `team_id` for `alicloud-express`). A provider may also declare that it consumes core keys (`uses_core`) and may **override** them in its own scope (`providers.<id>.sandbox_api_key`), which is how two providers get two different API keys.

---

## 3. The canonical scheme

### 3.1 Core keys

| Canonical key | Type | Secret | Canonical env | `compat` env | `legacy` env | Legacy config/kwarg names | Default |
|---|---|---|---|---|---|---|---|
| `provider` | id | no | `EBX_PROVIDER` | — | — | — | `alicloud-express` |
| `sandbox_api_key` | str | **yes** | `EBX_SANDBOX_API_KEY` | `E2B_API_KEY` | `SANDBOX_API_KEY` | `api_key` | none |
| `sandbox_base_url` | url | no | `EBX_SANDBOX_BASE_URL` | `E2B_API_URL` | `SANDBOX_API_BASE_URL` | `api_url`, `api_base_url` | provider-derived (see §4.5) |
| `sandbox_domain` | host | no | `EBX_SANDBOX_DOMAIN` | `E2B_DOMAIN` | — | `domain` | provider-derived |
| `http_timeout` | float ≥ 1 | no | `EBX_HTTP_TIMEOUT` | — | `SANDBOX_HTTP_TIMEOUT` | — | `30.0` |
| `http2` | bool | no | `EBX_HTTP2` | — | — | — | `true` |
| `max_retries` | int ≥ 0 | no | `EBX_MAX_RETRIES` | — | — | — | `3` |
| `max_connections`, `max_keepalive_connections`, `keepalive_expiry`, `ws_ping_interval`, `retry_base_delay` | num | no | `EBX_<KEY>` | — | — | — | as today |
| `log_level` | enum | no | `EBX_LOG_LEVEL` | — | `SANDBOX_LOG_LEVEL` | — | `WARNING` |
| `default_template` | str | no | `EBX_DEFAULT_TEMPLATE` | — | `SANDBOX_TEMPLATE`, `EBX_TEMPLATE` (in that order) | — | `base` |
| `llm_api_key` | str | **yes** | `EBX_LLM_API_KEY` | — | `native`: `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY`; `legacy`: `EBX_QWEN_CODE_API_KEY` | toml `llm_api_key` | none |
| `llm_base_url` | url | no | `EBX_LLM_BASE_URL` | — | `native`: `OPENAI_BASE_URL` | toml `qwen_code_base_url` | DashScope compatible-mode |
| `llm_model` | str | no | `EBX_LLM_MODEL` | — | `native`: `OPENAI_MODEL` | toml `qwen_code_model` | `qwen3-coder-plus` |
| `github_token` | str | **yes** | `EBX_GITHUB_TOKEN` | — | `native`: `GITHUB_TOKEN` | — | none |
| `template_index_url` | url | no | `EBX_TEMPLATE_INDEX_URL` | — | — | — | built-in index |
| `template_dir` | path | no | `EBX_TEMPLATE_DIR` | — | — | — | none |
| `mcp_auth_token` | str | **yes** | `EBX_MCP_AUTH_TOKEN` | — | — | — | none |
| `mcp_allowed_origins`, `mcp_runtime_dir` | str | no | `EBX_MCP_ALLOWED_ORIGINS`, `EBX_MCP_RUNTIME_DIR` | — | — | — | none |

Env-only tuning that is **not** a persistent config key (documented in the environment-variable guide, unchanged): `EBX_ACTIVITY_LINES`, `EBX_DISCOVER_COMMANDS`, `EBX_QWEN_CODE_BIN`, `EBX_QWEN_RESEARCH_TIMEOUT`, `EBX_QWEN_CODEGEN_TIMEOUT`, and the in-sandbox server variables (§1.5).

`EBX_GITHUB_TOKEN` outranks `GITHUB_TOKEN` on purpose: CI platforms inject `GITHUB_TOKEN` automatically; a person who sets the more specific `EBX_GITHUB_TOKEN` means it.

`sandbox_domain` and `sandbox_base_url` are generic because every E2B-protocol backend has a control-plane URL and a data-plane domain; providers that have neither simply do not declare them in `uses_core`.

### 3.2 Provider-scoped keys: built-in `alicloud-express`

| Key (scoped) | Type | Secret | Canonical env | `native` env | `legacy` env | Bare alias for the **default** provider | Notes |
|---|---|---|---|---|---|---|---|
| `region` | str | no | `EBX_ALICLOUD_EXPRESS_REGION` | — | `SANDBOX_REGION` | `region` | Derives base URL/domain (§4.5). Default `cn-hangzhou`. |
| `access_key_id` | str | no (id) | `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID` | `ALICLOUD_ACCESS_KEY_ID` | `AccessKey` | `access_key_id` | `credential` |
| `access_key_secret` | str | **yes** | `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_SECRET` | `ALICLOUD_ACCESS_KEY_SECRET` | `AccessSecret` | `access_key_secret` | `credential` |
| `acr_namespace` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_NAMESPACE` | — | `ACR_NAMESPACE` | `acr_namespace` | |
| `acr_registry` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_REGISTRY` | — | `ACR_REGISTRY` | `acr_registry` | |
| `acr_repo` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_REPO` | — | `ACR_REPO` | `acr_repo` | |
| `acr_username` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_USERNAME` | — | `ACR_USERNAME` | `acr_username` | |
| `acr_password` | str | **yes** | `EBX_ALICLOUD_EXPRESS_ACR_PASSWORD` | — | `ACR_PASSWORD` | `acr_password` | |
| `acr_instance_id` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_INSTANCE_ID` | — | `ACREE_INSTANCE_ID` | `acr_instance_id` | flag `--acree-instance-id` kept |
| `acr_vpc_id` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_VPC_ID` | — | `ACR_VPC_ID` | `acr_vpc_id` | |
| `acr_vswitch_ids` | csv | no | `EBX_ALICLOUD_EXPRESS_ACR_VSWITCH_IDS` | — | `ACR_VSWITCH_IDS` | `acr_vswitch_ids` | |
| `acr_security_group_id` | str | no | `EBX_ALICLOUD_EXPRESS_ACR_SECURITY_GROUP_ID` | — | `ACR_SECURITY_GROUP_ID` | `acr_security_group_id` | |
| `team_id` | str | no | `EBX_ALICLOUD_EXPRESS_TEAM_ID` | — | `TEAM_ID` | `team_id` | `compat`: `E2B_TEAM_ID` |

The built-in provider is the only one that implicitly consumes the generic `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain` (and, like every provider, the non-secret tuning keys `http_timeout`, `http2`, `max_retries`, ...). Plugins consume generic credentials/endpoints only through the explicit `inherit` opt-in of §4.6.

The names are long on purpose: CI jobs are the main user of the canonical env names and explicitness beats brevity there. Short forms exist as `native`/`legacy` aliases (`ALICLOUD_ACCESS_KEY_ID`, `ACR_NAMESPACE`) and as **bare keys** in `ebx config` (below).

### 3.3 Where each name lives

**`~/.ebx/config.toml`** (hand-edited or written by `ebx config set`; read by SDK and CLI):

```toml
[core]                          # new, optional
provider = "alicloud-express"   # `ebx provider default`
config_format = 1               # 1 = legacy storage names are written (default); 2 = canonical storage names (after `ebx config migrate`)

[transport]                     # existing section; generic keys. Both canonical and legacy names are read.
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"   # legacy: api_url
sandbox_domain   = "cn-hangzhou.e2b.fc.aliyuncs.com"               # legacy: domain
http_timeout = 30.0
http2 = true
max_retries = 3

[providers.alicloud-express]    # new; provider-scoped non-secret values
region = "cn-hangzhou"          # legacy location: [transport] region

[providers.my-cloud]            # a plugin's values
cluster = "prod"

[shortcuts]                     # unchanged
ps = "sandbox process list"
```

**`~/.ebx/.env`** (0600, secrets and credential-like values; env-style names): canonical `EBX_SANDBOX_API_KEY`, `EBX_ALICLOUD_EXPRESS_ACCESS_KEY_ID`, ... The legacy names written today (`E2B_API_KEY`, `ALICLOUD_ACCESS_KEY_ID`, `ACR_NAMESPACE`, `EBX_LLM_API_KEY`, `GITHUB_TOKEN`) are read as aliases.

**Storage-name policy (expand/contract).** The Python SDK and the Node CLI both read these files, and users may run an old and a new version side by side (an old MCP server started by an editor, a CI image with an older SDK). Therefore:

* **Phase 1 (this release): read-new/write-old.** Every reader accepts canonical + aliases. `ebx config set` keeps writing the **legacy storage name** for keys that had one (`api_url`, `E2B_API_KEY`, `ALICLOUD_ACCESS_KEY_ID`, ...) while `config_format` is absent or `1`; keys with no legacy storage name (`provider`, `sandbox_domain`... see table) are written canonically (an old version ignores unknown keys, `extra=ignore`).
* **Explicit migration:** `ebx config migrate` (and `python -m easy_sandbox.transport.config migrate`) rewrites storage names to canonical, keeps `config.toml.bak` / `.env.bak` (0600), sets `config_format = 2`. After that `config set` writes canonical names. Older versions then no longer see those values — the user chose that.
* **Phase 2 (a later minor release)**: new files are created with `config_format = 2`; legacy names are still read. No removal.

Which keys have a legacy storage name that Phase 1 keeps writing:

| Canonical key | Phase-1 stored as |
|---|---|
| `sandbox_api_key` | `E2B_API_KEY` in `~/.ebx/.env` |
| `sandbox_base_url` | `api_url` in `[transport]` |
| `sandbox_domain` | `domain` in `[transport]` |
| `region` | `region` in `[transport]` (legacy location; provider tables are written only for non-default providers or format 2) |
| `access_key_id`, `access_key_secret` | `ALICLOUD_ACCESS_KEY_ID`, `ALICLOUD_ACCESS_KEY_SECRET` in `~/.ebx/.env` |
| `acr_namespace` | `ACR_NAMESPACE` in `~/.ebx/.env` |
| `llm_api_key` | `EBX_LLM_API_KEY` in `~/.ebx/.env` |
| `github_token` | `GITHUB_TOKEN` in `~/.ebx/.env` |
| `http_timeout`, `http2`, `max_retries`, `llm_base_url`, `llm_model` | same name in `[transport]` (already canonical) |
| other `acr_*`, `team_id` (new settable keys) | canonical name in `[providers.alicloud-express]` / secret `acr_password` as `ACR_PASSWORD` in `.env` |
| `provider` | `[core] provider` |

**SDK surface**

* `TransportConfig` fields (canonical): `provider`, `sandbox_base_url`, `sandbox_domain`, `sandbox_api_key`, `region`, `access_key_id`, `access_key_secret`, `http_timeout`, ..., plus `provider_options: dict[str, Any]`.
  Legacy names remain **readable and writable attributes** (`config.api_key`, `config.api_url`, `config.domain`, `config.api_base_url`) and **accepted constructor/`load_config` keyword names** (`TransportConfig(api_key=...)`, `load_config(api_url=...)`). `model_dump()` emits canonical names; `model_dump(by_alias=...)` is not used.
* `Sandbox.create/connect/list/kill_by_id/deploy` and `@sandbox(...)`: new keyword-only parameters `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, `region`, `provider`, `provider_options`; old `api_key`, `api_url`, `domain`, `access_key_id`, `access_key_secret` unchanged. Passing both a canonical and a legacy kwarg with **different** values is a `ValueError` (identical values are accepted) — an explicit in-call conflict is a bug, unlike a layer conflict.

**CLI flags** (spec in the CLI doc): canonical `--sandbox-api-key`, `--sandbox-base-url`, `--sandbox-domain`, `--region/-r`, `--provider`, `--opt KEY=VALUE`; legacy `--api-key`, `--api-url`, `--domain` stay as aliases of the same option. `--acr-*` flags unchanged (they already match `acr_*`), `--acree-instance-id` stays as alias of `--acr-instance-id`.

### 3.4 Bare keys vs qualified keys in `ebx config`

`ebx config get|set|delete KEY` accepts:

1. A **core key** (canonical or legacy name).
2. A **qualified provider key** `providers.<id>.<key>` (canonical, unambiguous, works for every provider).
3. A **bare provider key** (`region`, `access_key_id`, ...). It resolves against the provider selected by `--provider` for the command, else the **default provider**. If the key does not exist in that provider's schema the command fails with exit 2 and names the qualified form of every installed provider that declares it. With the built-in default this is exactly today's behaviour.
4. `shortcuts` and `shortcuts.<name>` (reserved prefix; provider ids and keys can never start with `shortcuts`).

---

## 4. Precedence

### 4.1 Layers

```text
1. explicit        code kwargs / CLI flags / `--opt`
2. process env     os.environ
3. ./.env          project dotenv (first candidate)      ─┐ each existing file in `_ENV_FILE_CANDIDATES`
4. ~/.ebx/.env     user dotenv (second candidate)         ─┘ is its own layer, in list order
5. ~/.ebx/config.toml
6. default         provider-derived or built-in
```

A blank or whitespace-only value is *unset* in every layer (it never hides the next layer). Layers are tried in order; **the first layer that has any acceptable name for the key decides**, and within that layer the names are tried in the *name order* below.

### 4.2 Name order inside one layer (most specific first)

For key `K` resolved for provider `P`:

1. provider-scoped canonical: `EBX_<P>_<K>` (only if `K` is in `P`'s schema or `P` declares it in `uses_core`)
2. canonical: `EBX_<K>` (core keys)
3. `compat`/`native` names in the table order (`E2B_API_KEY`, `ALICLOUD_ACCESS_KEY_ID`, `GITHUB_TOKEN`, ...)
4. `legacy` names in the table order (`SANDBOX_API_KEY`, `AccessKey`, ...)

In `config.toml` the analogue is: `[providers.<P>].<K>` > `[transport].<K>` (canonical name) > `[transport].<legacy name>` > top-level flat legacy keys (only when the file has no `[transport]` table, as today).

The pre-existing relative orders are preserved verbatim (`E2B_API_KEY` > `SANDBOX_API_KEY`; `E2B_API_URL` > `SANDBOX_API_BASE_URL`; `SANDBOX_TEMPLATE` > `EBX_TEMPLATE`; `ALICLOUD_*` > `AccessKey`). The only new rule is that canonical names sit in front of them.

### 4.3 The one normalisation (layer-first for dotenv)

Before this change `load_config` merged `./.env` and `~/.ebx/.env` per exact variable name **before** applying name priority. Example: `./.env: SANDBOX_API_KEY=a` and `~/.ebx/.env: E2B_API_KEY=b` resolved to `b`, although the documentation says "`./.env` overrides `~/.ebx/.env`". The new resolver is layer-first (as `resolve_llm_env` and the CLI `_effective_value` already were): the project file wins as documented. This is a bug fix in a corner (different names for the same key in both files) and is called out in the CHANGELOG. Every other combination resolves exactly as before — including all the existing tests.

### 4.4 Provider selection precedence

```text
explicit provider= / --provider
  > EBX_PROVIDER (process env)
  > EBX_PROVIDER in ./.env
  > EBX_PROVIDER in ~/.ebx/.env
  > [core] provider in ~/.ebx/config.toml     (`ebx provider default NAME`)
  > alicloud-express
```

Operations on an *existing* sandbox from the CLI additionally honour the qualified reference `provider:sandbox_id` (§7.4), which sits at the level of an explicit flag.

### 4.5 Derived defaults

Providers may declare derivations from other keys (data, no code):

```toml
[endpoint.derive]
sandbox_base_url = "https://api.{region}.e2b.fc.aliyuncs.com"
sandbox_domain   = "{region}.e2b.fc.aliyuncs.com"
```

The behaviour of today's `load_config` is preserved exactly: derivation applies only when the base URL was **not** given by an explicit argument or a **process environment** variable (canonical, `compat` or `legacy` name); each derived key is applied with "set default" semantics, so a base URL/domain coming from `.env`/`config.toml` is kept and the other one is still derived from the region; when the URL is explicit by argument/env the domain is not derived (it stays the provider default `cn-hangzhou…`) — kept for bit-for-bit compatibility. Providers without `derive` just use their static defaults.

### 4.6 Provider scoping rules (credential isolation)

* **Scoped beats generic** only while `P` is the active provider: `providers.<P>.<key>` / `EBX_<P>_<KEY>` outrank the generic name of a core key `P` is allowed to read.
* **Credentials and endpoints never cross providers.** Resolving for provider `P` never looks at `EBX_<Q>_*` or `[providers.Q]` for `Q ≠ P`.
* **The generic credential/endpoint keys (`sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, together with all their aliases such as `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN`) belong to the built-in provider.** Without this rule, switching the default provider would silently send the Alibaba Cloud key to a third-party plugin (and a plugin's key to the Alibaba endpoint). A non-builtin provider receives them **only** when (a) its manifest lists them in `[core] inherit` **and** (b) the user consented to that at install/update time (the receipt records the consented list; the consent screen prints a warning line naming the keys). The effective list is `manifest.inherit ∩ receipt.consented.inherit`. The reference `e2b-compatible` provider inherits all three, so `E2B_API_KEY`/`E2B_API_URL` work with it — by explicit, recorded consent.
* Non-secret tuning keys (`http_timeout`, `http2`, `max_retries`, pool/WS/backoff) are shared with every provider.
* LLM, GitHub and MCP keys are not provider credentials and are **never** delivered to a provider.
* A plugin's own credentials are scoped fields it declares (typically `api_key`; env `EBX_<P>_API_KEY`) plus any `native` env names the plugin lists on that field (visible in `ebx provider info`).
* Plugin values reach a plugin process only through the `initialize` request, never through the environment (§8.3).

---

## 5. Complete alias table

`status`: `C` canonical · `E` compat (E2B protocol) · `N` native (vendor/third-party standard) · `L` legacy. Every row keeps working in every surface where the old name worked before.

### 5.1 Environment variables

| Old / alternative name | Status | Canonical key | Scope | Notes |
|---|---|---|---|---|
| `E2B_API_KEY` | E | `sandbox_api_key` | core | also what `ebx config set sandbox_api_key` writes in phase 1 |
| `SANDBOX_API_KEY` | L | `sandbox_api_key` | core | |
| `E2B_API_URL` | E | `sandbox_base_url` | core | |
| `SANDBOX_API_BASE_URL` | L | `sandbox_base_url` | core | |
| `E2B_DOMAIN` | E | `sandbox_domain` | core | |
| `SANDBOX_REGION` | L | `region` | `alicloud-express` | applies to the active provider if it declares `region` |
| `SANDBOX_HTTP_TIMEOUT` | L | `http_timeout` | core | |
| `SANDBOX_LOG_LEVEL` | L | `log_level` | core | |
| `SANDBOX_TEMPLATE`, `EBX_TEMPLATE` | L | `default_template` | core | order kept |
| `ALICLOUD_ACCESS_KEY_ID` | N | `access_key_id` | `alicloud-express` | |
| `ALICLOUD_ACCESS_KEY_SECRET` | N | `access_key_secret` | `alicloud-express` | |
| `AccessKey` / `AccessSecret` | L | `access_key_id` / `access_key_secret` | `alicloud-express` | |
| `ACR_NAMESPACE` `ACR_REGISTRY` `ACR_REPO` `ACR_USERNAME` `ACR_PASSWORD` `ACR_VPC_ID` `ACR_VSWITCH_IDS` `ACR_SECURITY_GROUP_ID` | L | `acr_*` | `alicloud-express` | |
| `ACREE_INSTANCE_ID` | L | `acr_instance_id` | `alicloud-express` | |
| `TEAM_ID` | L | `team_id` | `alicloud-express` | |
| `E2B_TEAM_ID` | E | `team_id` | `alicloud-express` | |
| `GITHUB_TOKEN` | N | `github_token` | core | |
| `BAILIAN_CODING_PLAN_API_KEY`, `DASHSCOPE_API_KEY`, `OPENAI_API_KEY` | N | `llm_api_key` | core | order kept |
| `EBX_QWEN_CODE_API_KEY` | L | `llm_api_key` | core | lowest in env; `~/.ebx` use unchanged |
| `OPENAI_BASE_URL` / `OPENAI_MODEL` | N | `llm_base_url` / `llm_model` | core | |
| `EBX_LLM_*`, `EBX_MCP_*`, `EBX_TEMPLATE_INDEX_URL`, `EBX_TEMPLATE_DIR` | C | unchanged | core | already canonical |
| `SANDBOX_GITHUB_TOKEN` | — | — | — | never worked; **not** supported (fix `.env.example`) |

### 5.2 `ebx config` keys, `config.toml` keys, SDK names, flags

| Old name | Where it worked | Canonical | Status |
|---|---|---|---|
| `api_key` | `ebx config` alias; SDK kwarg/field; `[transport] api_key` | `sandbox_api_key` | L (kwarg/field: C-compatible, never removed) |
| `api_url` | `ebx config`; SDK kwarg/field; `[transport] api_url` | `sandbox_base_url` | L |
| `api_base_url` | `load_config` kwarg; `[transport] api_base_url`; `TransportConfig.api_base_url` | `sandbox_base_url` | L |
| `domain` | `ebx config`; SDK; `[transport] domain` | `sandbox_domain` | L |
| `region`, `access_key_id`, `access_key_secret`, `acr_namespace` | everywhere | same key, now provider-scoped (`providers.alicloud-express.<key>`); bare form kept for the default provider | C |
| `qwen_code_api_key/base_url/model` | removed keys; toml values read | `llm_*` | L (unchanged behaviour: `config get/set` name the replacement) |
| `--api-key`, `--api-url`, `--domain` | `ebx mcp install/start` | `--sandbox-api-key`, `--sandbox-base-url`, `--sandbox-domain` | L (flags are aliases of one option) |
| `--acree-instance-id` | template commands | `--acr-instance-id` | L |

---

## 6. Deprecation and signalling policy

1. **Default: silent.** No existing command changes stdout or stderr because an old name was used. Env vars, `.env` entries, `config.toml` keys, SDK kwargs and attributes are all silent forever unless the user opts in. Justification: these names are baked into CI secrets, Dockerfiles, editor MCP configs and E2B-compat code that nobody will rewrite for a warning, and warning noise in CI logs/`--json` output is a regression for consumers.
2. **Pull-based audit (no side effects)**: `easy_sandbox.transport.config.audit_config()` (SDK) / `ebx config check` (CLI) list every legacy name in use, where (`env`, `./.env`, `~/.ebx/.env`, `config.toml`), and the canonical replacement. `--strict` exits 1 if any `legacy` name is found (never for `compat`/`native`). Output contains names only, never values.
3. **Opt-in push**: `EBX_WARN_DEPRECATED=1` (or `warn_deprecated = true` in `[core]`) makes the SDK emit one `DeprecationWarning` per legacy name per process (also for legacy kwargs) and the CLI one stderr line per legacy name at startup. Off by default; never printed when `--json`, `--quiet` or `--ci` is active *unless* the env var is set explicitly (explicit opt-in beats quiet-mode).
4. **One documented interactive hint**: using a *renamed config key* (`api_url`, `domain`, `api_key`, `api_base_url`) in `ebx config get|set|delete` prints a single dim line on **stderr** — `note: 'api_url' is now 'sandbox_base_url' (the old name keeps working)` — **only** when stderr is a TTY and neither `--json`, `--quiet`, `--ci` nor a CI environment is active. stdout is untouched. Non-interactive consumers (scripts, CI, golden tests, `--json`) therefore observe no change. This is the only default-behaviour signal and exists because `config` is the one place where a human types key names directly.
5. `compat` (E2B) and `native` names never trigger any of the above.
6. Removal policy: no alias is removed in 0.x. A removal would need a major version, a one-release `EBX_WARN_DEPRECATED` default flip and a `config migrate` run.

---

## 7. Providers

### 7.1 Identity

* Built-in id **`alicloud-express`**, display name **Alibaba Cloud Express Edition** / **阿里云极速版**. Reasons for the id: vendor prefix (`alicloud`, same as `ALICLOUD_*` and the `alicloud` pip extra) + edition (`express`, the product tier the current API implements). Rejected: `e2b` (a *protocol* that many providers will speak), `fc` (a product family that may host other editions), `aliyun`/`default` (not stable: "default" changes meaning; the console brand may change), `alibaba` (too coarse). The display name may change; **the id never changes**.
* Id grammar: `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, 2–40 chars, no underscore (so `-`→`_` env mapping is injective). Reserved: `alicloud-express`, `default`, `all`, `none`, `builtin`, `shortcuts`, `core`, `transport`, `providers`, anything starting `ebx-`, `e2b` and `alicloud-` (reserved for first-party editions).
* The default is **always** `alicloud-express` until the user runs `ebx provider default <id>` / sets `EBX_PROVIDER`. A user who never touches providers sees no change in any output.

### 7.2 Capability matrix (feature flags)

A provider declares which **features** it implements. The SDK/CLI check the feature before calling; an unsupported feature raises `ProviderFeatureNotSupportedError` (`E8004`, subclass of the existing `CapabilityNotSupportedError`) — never an `AttributeError`/HTTP 404.

| Feature id | Meaning | Python SDK surface | CLI commands (need it) |
|---|---|---|---|
| `sandbox.lifecycle` | create / connect / list / info / kill | `Sandbox.create/connect/list/kill_by_id`, `info` | `create`, `list`, `info`, `kill`, `connect` |
| `sandbox.timeout` | change TTL | `set_timeout`, `refresh` | `sandbox timeout` |
| `sandbox.pause` | pause / resume | `pause`, `resume` | `sandbox pause/resume` |
| `exec.run` | run a command, buffered result | `commands.run` | `exec`, `run`, `shell` |
| `exec.stream` | streamed output | `commands.stream` | `shell-stream` |
| `process.manage` | list/kill/signal/stdin of processes | `commands.list/kill/send_*` | `sandbox process ...` |
| `pty` | interactive terminal | `get_terminal` | `connect --pty` |
| `files.rw` | read/write/list/stat/mkdir/remove/move | `files.*` | `files`, `upload`, `download` |
| `files.watch` | watch directories | `files.watch` | — |
| `files.transfer` | signed upload/download URLs | `get_upload_url/get_download_url` | — |
| `code.interpret` | stateful code contexts | `run_code`, `code.*` | `sandbox code` |
| `templates.read` | list/get templates | `Template*` read | `template list/info` |
| `templates.build` | build/deploy/delete templates (image build + register) | `DockerBuilder`, `fc_template` | `template build/deploy/delete`, `deploy`, `install` |
| `ports.url` | public URL for a port | `network.get_url` | `sandbox system ports`, `url` |
| `ports.domain` | custom domains for a sandbox/template | `extensions.DomainConfig` | — |
| `storage.mount` | mount object storage (OSS) | `extensions.OSSMount` | — |
| `network.vpc` | attach a VPC | `extensions.VPCConfig` | `--vpc-id` family |
| `sessions` | sandbox identity survives the process (re-attach by id) | `Sandbox.connect` + `LocalSessionStore` | `session ...` |

`alicloud-express` implements all of them. A sandbox's capabilities stay the **template's capabilities** (unchanged); where the provider lacks the feature behind a capability token (`shell ← exec.run`, `files ← files.rw`, `code ← code.interpret`, `terminal ← pty`, `ports ← ports.url`) the call raises `E8004` at call time. The implementation does not intersect the two sets up front: the template is provider-independent data, and failing at the call with a precise error is simpler and cannot disagree with the provider's behaviour.

### 7.3 Tradeoff analysis: how do plugins load?

Requirement: one plugin should serve **both** the Python SDK and the Node CLI.

| Option | One plugin for both languages | Install-time risk | Run-time isolation | Streaming/perf | Effort | Verdict |
|---|---|---|---|---|---|---|
| **A. Native per language** (Python entry point; npm module) | No — two implementations per provider | pip/npm execute build/setup code at install | In-process: full trust, can crash/hang the host | Best | Low per language | **Keep only as SDK-side advanced path** (`register_provider()`, entry-point group `easy_sandbox.providers`); not installable by `ebx provider install` |
| **B. Executable + JSON-RPC over stdio (EPP/1)** | **Yes** | None (copy + validate; nothing runs) | Separate process: crash/hang/timeouts contained, env scrubbed, can be wrapped by OS sandbox later | Good for control plane; file bytes are base64-in-JSON (use C for heavy data) | Medium (one client per language) | **Primary** |
| **C. REST-compatible `base_url`** (E2B protocol, declarative manifest) | **Yes**, no code at all | None | Nothing to isolate | Native speed (built-in transport) | Lowest | **Primary for E2B-protocol backends** |
| D. gRPC/HTTP plugin server on localhost | Yes | None | Process, but port allocation, auth of the local port, firewall prompts | Best streaming | High (codegen, lifecycle, ports) | Rejected for v1; EPP/2 may add it as an alternative transport |
| E. WASM component | Yes | None | Strong | Limited I/O story today | Very high | Rejected for v1 |

**Decision: B + C, plus A as an SDK-only escape hatch.** Both B and C describe a plugin with a *manifest* (`ebx-provider.toml`); the manifest's `runtime.kind` is `rest` (C) or `exec` (B). The recommended architecture for a new backend is: *implement the E2B envd data-plane protocol* (or reuse it) and ship an `exec` plugin for **only the control plane** (create/connect/list/kill returning `envd_url` + token) — the data plane (exec, files, PTY, code) then flows through the fast native transports in the SDK and CLI. A backend with no envd compatibility implements the data-plane methods (`exec.run`, `files.*`) in the plugin too, accepting base64 overhead.

### 7.4 The provider contract

**Python SDK interface** (`easy_sandbox.providers.base`):

```python
class Provider(ABC):
    id: str
    display_name: str               # "Alibaba Cloud Express Edition"
    display_name_zh: str            # "阿里云极速版"
    version: str
    features: frozenset[ProviderFeature]
    config_fields: tuple[ConfigField, ...]   # provider-scoped schema
    uses_core: frozenset[str]                # core keys it consumes
    kind: Literal["builtin", "rest", "exec", "python"]

    def require(self, feature: ProviderFeature) -> None: ...   # raises ProviderFeatureNotSupportedError
    async def build_infra(self, config: TransportConfig) -> ProviderInfra: ...
```

`ProviderInfra` carries what `Sandbox` needs: `config`, `auth`, `http_client` (may be `None` for non-HTTP providers), and the four protocol objects (`sandbox_protocol`, `process_protocol`, `filesystem_protocol`, `code_interpreter_protocol`). For HTTP/envd providers these are the existing classes; for `exec` providers they are thin adapters that implement the same methods on top of EPP calls. `Sandbox` already accepts those protocol objects in its constructor, so no `Sandbox` internals change.

**Node CLI interface** (spec in the CLI document): the same shape as a TypeScript interface (`id`, `displayName`, `features: Set<ProviderFeature>`, `configFields`, `usesCore`, `buildInfra(config)`), with the wire shapes below kept `snake_case`.

**Wire protocol EPP/1** — JSON-RPC 2.0, newline-delimited UTF-8 JSON on the plugin's stdin/stdout; stderr is free-form log text (captured, shown with `--verbose`, and appended to crash errors). One request/response pair per line, no batching, max line 8 MiB (`max_message_bytes`). The host sends requests; the plugin may send *notifications* only (`log`, `progress`, `exec.output`, `exec.exit`, `pty.output`). Unknown methods → `-32601`; unknown fields must be ignored by both sides.

<a id="epp-methods"></a>

The table below is normative and is also shipped as `client-sdk/tests/fixtures/epp-methods.json` (mirrored byte-identically to `cli/docs/design/fixtures/`): per method, the feature, whether it is `required`, `optional` or an `extension`, whether the host retries it, and each parameter's name, type and presence. A test drives every host adapter through a recording client and fails when an adapter sends a parameter that the table does not list, omits one that it marks required, or never calls a method the table says the host calls. **Support** column: **R** = required for its feature, **O** = optional (the host falls back), **X** = extension (plugins may offer it; the host does not call it yet).

| Method | Params (snake_case; `?` = optional) | Result | Feature | Support |
|---|---|---|---|---|
| `initialize` | `{protocol:"epp/1", host:{name,version}, provider_id, config:{…declared fields}, core:{…declared core keys}, locale, data_dir}` | `{protocol, plugin:{name,version}, features:[…]}` | — | R |
| `shutdown` | `{}` | `{}` | — | R |
| `sandbox.create` | `{template, timeout, metadata, envs, cpu, memory, disk, gpu, request_timeout, secure?, options?}` | `SandboxRecord` | `sandbox.lifecycle` | R |
| `sandbox.get` | `{sandbox_id}` | `SandboxRecord` | `sandbox.lifecycle` | R |
| `sandbox.connect` | `{sandbox_id}` | `SandboxRecord` | `sandbox.lifecycle` | O (may resume; on `-32601` the host calls `sandbox.get`) |
| `sandbox.list` | `{limit, status?, cursor?, metadata?}` | `{sandboxes:[SandboxRecord], next?}` | `sandbox.lifecycle` | R |
| `sandbox.kill` | `{sandbox_id}` | `{}` | `sandbox.lifecycle` | R |
| `sandbox.set_timeout` | `{sandbox_id, timeout}` | `{}` | `sandbox.timeout` | R |
| `sandbox.pause` / `sandbox.resume` | `{sandbox_id}` | `{}` | `sandbox.pause` | R |
| `exec.run` | `{sandbox_id, cmd, args, env, cwd, user, timeout, stdin?}` | `{exit_code, stdout, stderr, stdout_b64?, stderr_b64?}` | `exec.run` | R |
| `exec.start` | same as `exec.run`, plus `detached?` | `{process_id: string}`, then notifications `exec.output{process_id, stream, data}` and exactly one `exec.exit{process_id, exit_code}` | `exec.stream` | R (`detached`: X) |
| `process.list` | `{sandbox_id}` | `{processes:[{pid, command, status, …}]}` | `process.manage` | R |
| `process.kill` / `process.signal` / `process.stdin` | `{sandbox_id, pid, signal? \| data?}` | `{}` | `process.manage` | R (`stdin` may answer `-32003`) |
| `files.read` | `{sandbox_id, path, offset?, length?}` | `{content_b64, size}` | `files.rw` | R (`offset`/`length`: X) |
| `files.write` | `{sandbox_id, path, content_b64, mode?, append?}` | `{}` | `files.rw` | R (`mode`/`append`: X) |
| `files.list` | `{sandbox_id, path}` | `{entries:[{name,path,type,size,mtime?}]}` | `files.rw` | R |
| `files.stat` | `{sandbox_id, path}` | `{name,path,type,size,mtime?}` | `files.rw` | R |
| `files.mkdir` / `files.remove` | `{sandbox_id, path}` | `{}` | `files.rw` | R |
| `files.move` | `{sandbox_id, source, destination, overwrite?}` (plugins may also accept `src`/`dest`) | `{}` | `files.rw` | R |
| `files.search` / `files.chmod` | `{sandbox_id, path, pattern \| mode}` | `{entries}` / `{}` | `files.rw` | X |
| `ports.url` | `{sandbox_id, port}` | `{url, headers?}` | `ports.url` | R (the SDK calls it from `network.resolve()`) |
| `templates.list/get/delete/build/build_status` | | | `templates.read` / `templates.build` | R |
| `pty.open/write/resize/close` | | notification `pty.output` | `pty` | R |

Parameter conventions: `secure` is sent **only** when the caller passed `secure=True/False` to `Sandbox.create` (otherwise absent, so the plugin's own default applies; the built-in provider behaves as `secure=True`). `options` is the caller's `provider_options` (declared config fields only) **minus secret fields**, for per-create settings (network policy, platform, image pull settings); a plugin must whitelist the keys it accepts per create and never let `options` change the server address or credentials. `process_id` (from `exec.start`) is a **string**; the `pid` of `process.*` is an opaque `string | integer`: the integer `pid` of a `process.list` entry or a `process_id`, and the SDK's `ProcessInfo.pid` and `commands.kill/send_signal/send_input` accept both. `sandbox.get` is the only required lookup; `sandbox.connect` is for plugins whose "connect" does more (resume). Unknown parameters must be ignored by both sides.

`SandboxRecord` = `{sandbox_id, template, status("creating"|"running"|"paused"|"stopping"|"stopped"|"error"), region?, created_at?, expires_at?, metadata{}, envd_url?, envd_access_token?, url?}` (status values are the SDK's `SandboxStatus`).

Conventions: all durations are **seconds** on the wire (`timeout`, `request_timeout`) and `*_ms` only in the manifest; `sandbox.list` takes an opaque `cursor` and returns `next` (absent = last page); `exec.run` returns text in `stdout`/`stderr` (invalid UTF-8 replaced) and may add `stdout_b64`/`stderr_b64` for exact bytes; for `exec.start` the plugin sends all `exec.output` notifications of a process in order and exactly one `exec.exit` last; the host retries only **idempotent** methods (`sandbox.get/list/kill/connect`, `files.read/stat/list`, `ports.url`) and only on errors flagged `retryable`; `sandbox.create`, `exec.*`, `files.write` are never retried by the host. A request that is cancelled with `$/cancel {id}` (the host sends it on timeout or when the caller goes away) tells the plugin to stop the work, for example kill the process it spawned for that `exec.start`; it should still answer. A manifest default for a config field is **delivered** in `initialize.config`, so do not give a field a default when it has an alternative (`base_url` vs `domain`): the default would always win. `data.sdk_code` selects the SDK exception class for `-32001/-32002/-32000` (for example `E1001`, `E2000`, `E2001`, `E3001`, `E4001`; the full table is `_SDK_CODE_CLASSES` in `providers/epp.py`); a bare `-32002` for a missing **file** is E8005 (sandbox not found), so file errors should carry `sdk_code: "E4001"`. When `envd_url` is present the host talks to it directly with the native envd transport (the **hybrid** model above); otherwise it uses the data-plane methods.

Errors: JSON-RPC `error = {code, message, data:{sdk_code?, suggestion?, retryable?, details?}}`.

| EPP code | Meaning | Host exception | CLI exit |
|---|---|---|---|
| `-32001` | unauthenticated / bad credentials | `AuthenticationError` (E1xxx; `data.sdk_code` selects the subclass) | 3 |
| `-32002` | not found (sandbox, template, file) | the class named by `data.sdk_code` (E2001, E4001…); default `ProviderResourceNotFoundError` E8005 | 4 |
| `-32003` | feature not supported | `ProviderFeatureNotSupportedError` E8004 | 1 |
| `-32004` | quota exceeded | `QuotaExceededError` E2002 | 6 |
| `-32005` | timeout | `CommandTimeoutError` / `ProviderTimeoutError` E8022 | 5 |
| `-32006` | invalid params / config | `ProviderConfigError` E8002 | 2 |
| `-32000` | other provider failure | `SandboxError` with `sdk_code` or E8000 | 1 |
| `-32600…-32603`, `-32700` | JSON-RPC standard | `ProviderProtocolError` E8020 | 1 |

Because the host maps plugin errors back onto the existing hierarchy and exit codes, the CLI's deterministic exit codes (0–6) hold for every provider.

Lifecycle of a plugin process: spawned lazily on first use, one process per provider session (one SDK `Sandbox` operation scope / one CLI invocation), `initialize` within `startup_timeout` (default 10 s), calls bounded by `call_timeout` (default 60 s, per-call override from `timeout`), cancellation via notification `$/cancel {id}`, `shutdown` then close stdin, SIGTERM after 3 s, SIGKILL (process group / Windows Job Object) after another 3 s. The host never reuses a process across CLI invocations (state is the provider's responsibility), which keeps the plugin trivially stateless to write and crash-safe.

**REST kind limits.** A `rest` provider is the E2B protocol with a different endpoint and a bearer/`X-API-Key` API key. Providers that need request signing (AK/SK), OAuth or a non-E2B API must be `exec`.

**Version negotiation.** `epp/1`; backwards-compatible additions bump only the manifest's `protocol_minor` hint. A host refuses a manifest whose `protocol` is not one it supports (`E8013`). `requires_ebx` (below) gates SDK/CLI versions.

### 7.5 Manifest: `ebx-provider.toml`

TOML (both `tomllib`/`tomli` and `smol-toml` are already dependencies; comments allowed; YAML would add a Python dependency).

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
protocol    = "epp/1"                     # or "e2b-rest/1" for kind = "rest"
requires    = { sdk = ">=0.3,<1", cli = ">=0.3,<1" }   # comparators: >= <= > < == != ~=, comma = AND

[runtime]
kind    = "exec"                          # exec | rest
command = ["python3", "./provider.py"]    # argv, never a shell string; "./x" resolves inside the plugin dir
startup_timeout_ms = 10000
call_timeout_ms    = 60000
platforms = ["linux", "darwin", "win32"]  # optional

[features]
supported = ["sandbox.lifecycle", "exec.run", "files.rw"]

[security]                                # declared, shown at install and update, hashed into the consent record
network      = []                         # hosts the plugin intends to contact ("*" = any)
filesystem   = ["data_dir"]               # "data_dir" | "cwd" | "home" | "any"
env_passthrough = []                      # extra env var names forwarded to the process
spawns_processes = true

[core]
inherit = []                              # subset of sandbox_api_key | sandbox_base_url | sandbox_domain (opt-in, shown at consent, see §4.6)

[auth]                                    # optional: which credential groups make the provider usable
any_of = [["api_key"]]                    # [[a, b], [c]] = (a AND b) OR c; drives `provider doctor` / "missing credentials" errors

[config.fields.workdir_root]              # provider-scoped schema -> `ebx provider config`, validation, env names
type = "path"                             # string | int | float | bool | enum | path | url | csv
required = false
secret = false
credential = false                        # true: missing -> E1003 (exit 3) instead of E8002
default = ""
description = "Directory that holds sandbox working dirs"
description_zh = "沙箱工作目录的根目录"
env = ["LOCAL_PROCESS_ROOT"]              # optional extra (native) env names for this plugin's own field; canonical EBX_LOCAL_PROCESS_WORKDIR_ROOT is automatic. Names starting EBX_, E2B_, ALICLOUD_ are refused.
```

`kind = "rest"` replaces `[runtime] command` with:

```toml
[runtime]
kind = "rest"
[endpoint]
base_url = "https://sandbox.example.com"
domain   = "sandbox.example.com"
auth     = { scheme = "bearer" }          # bearer | header (header = "X-API-Key")
[endpoint.derive]                          # optional
sandbox_base_url = "https://api.{region}.example.com"
```

**Validation rules (both languages)**: `manifest_version == 1`; id grammar and reserved ids; `command` is a non-empty array of strings without NUL; the executable path must resolve **inside** the plugin dir when it starts with `./` or `../` (no escape); `.bat`/`.cmd`/`.ps1` launchers are rejected (they need a shell; Node refuses to spawn them without one) — Windows plugins use an `.exe` or an interpreter + script; `env_passthrough` may not name `EBX_*`, `E2B_*`, `ALICLOUD_*`; `core.inherit` ⊆ {`sandbox_api_key`,`sandbox_base_url`,`sandbox_domain`}; `[auth] any_of` references declared fields only; field keys match `^[a-z][a-z0-9_]*$`, never collide with a core key or `shortcuts*`; `type` known; secrets need no `default`; `features.supported` ⊆ the feature registry; unknown top-level tables are ignored (forward compat); file size ≤ 256 KiB.

### 7.6 Storage layout, install, trust

```text
~/.ebx/providers/
  .lock                       # O_EXCL lock for install/update/uninstall
  .staging/                   # installs are assembled here and renamed atomically
  .trash/                     # previous version kept until the swap succeeded
  <id>/
    ebx-provider.toml
    ... plugin files ...
    .ebx-install.json         # receipt (below)
    data/                     # reserved for the plugin's own state; not hashed, kept on update, a source containing it is rejected
```

The directory is the source of truth; there is no separate index to drift. The default provider lives in `config.toml` `[core] provider`.

Receipt `.ebx-install.json`:

```json
{
  "receipt_version": 1,
  "id": "local-process", "version": "0.1.0",
  "source": {"type": "git", "url": "https://example.com/org/repo.git", "ref": "v0.1.0",
             "commit": "<40-hex>", "subdir": "providers/local-process"},
  "tree_sha256": "<hex>", "manifest_sha256": "<hex>",
  "trust": "pinned",                        // pinned | local | link | unpinned
  "consented": {"runtime": ["python3","./provider.py"], "security": {...}, "features": [...]},
  "installed_at": "2026-10-12T06:00:00Z", "installed_by": {"name": "ebx-cli", "version": "0.3.0"}
}
```

**Tree digest (identical in Python and Node).** `tree_sha256 = SHA-256( for each regular file, sorted by UTF-8 path bytes: path + "\0" + ("x" if executable else "-") + "\0" + SHA-256(file bytes) + "\n" )`, paths POSIX-style relative to the plugin root, excluding `.git/`, `.ebx-install.json` and the top-level `data/` directory. Everything else is hashed, including a plugin's `tests/` directory (it is installed and changes the digest; install a `--subdir` or keep tests small). Symlinks are rejected at install (§8). Both implementations are tested against the same vectors.

**Install algorithm** (`ebx provider install <source>`):

1. Classify `<source>`: existing directory → `local`; `--link` → `link` (symlink to the directory, development only); git URL → `git` (`https://…`, `ssh://…`, `git@host:path`, optional `git+` prefix; `file://`, `ext::`, `git://` and `http://` are **rejected** unless `--allow-insecure-transport`; URLs with embedded credentials are rejected — use a credential helper/SSH agent).
2. Stage: local → copy with the safety rules of §8.2; git → `git clone --depth 1 --no-checkout`, `git checkout <ref>` with **hooks, filters, fsmonitor, submodules, LFS smudge and `core.sshCommand` disabled** and a scrubbed environment (§8.2), then copy the tracked files only. Resolve the ref to a full commit SHA.
3. Parse and validate the manifest (§7.5). Compute `tree_sha256`, `manifest_sha256`.
4. If `--sha256 DIGEST` is given, it must equal `tree_sha256` (`E8011` otherwise) → trust `pinned`. A git source whose `--ref` is a full 40-hex commit is `pinned`; a tag/branch is `unpinned` and refused in non-interactive mode unless `--allow-unpinned`.
5. **Consent**: print id, name, version, source, commit, digest, runtime command, declared security block, features, and the config fields (secrets marked). Interactive: `Install and trust this provider? [y/N]`. Non-interactive/CI: requires `--yes`, otherwise exit 2 (`E8012`).
6. Atomic swap into `<id>/` under the lock; write the receipt. **Nothing from the plugin is executed.** The first execution happens when a command uses it (or `ebx provider doctor`).

**Run-time checks** (every spawn of an `exec` provider): receipt exists; `tree_sha256` of the directory equals the receipt (`E8011` on mismatch, message `provider files changed since install; reinstall or run 'ebx provider update <id>'`) — skipped only for trust `link`/`local-dev`, which print a one-line `warning: provider <id> is a linked development install` on stderr; `requires` satisfied (`E8013`).

**Update** (`ebx provider update [<id>|--all] [--ref R] [--check] [--yes] [--allow-unpinned] [--allow-insecure-transport] [--no-verify]`): re-fetch from the recorded source, show a diff summary (version, commit range, changed runtime/security/features/config fields); **re-consent required whenever runtime command, security block or feature list changed**, otherwise `--yes` suffices; pinned installs only move with an explicit `--ref`; previous version stays in `.trash/` until the new one passes `initialize`; on failure the previous files **and `data/`** are restored exactly. The receipt does not record `--allow-insecure-transport`: a `file://`/`http://`/`git://` source needs the flag on every update (re-asserting a deliberate act). `--check` prints available updates and changes nothing.

**Uninstall** (`ebx provider uninstall <id> [--purge] [--yes]`): removes the directory. If it was the default provider the default falls back to `alicloud-express` and a notice is printed. Stored values (`[providers.<id>]`, `EBX_<ID>_*` in `~/.ebx/.env`) are kept unless `--purge`.

### 7.7 Multi-provider rules

* Resolution per command: §4.4. A command talks to **one** provider.
* Sandbox ids are provider-local. The CLI has two output formats: **legacy format** (bare ids, no `provider` field — byte-identical to today) is used **iff both** the *ambient* provider (§4.4 without the explicit flag: `EBX_PROVIDER` → `./.env` → `~/.ebx/.env` → config → built-in) **and** the *effective* provider (explicit flag or ambient) are `alicloud-express`. In every other situation the CLI uses the **qualified format**: ids are printed as `provider:sandbox_id` (e.g. `local-process:sbx-1`, `alicloud-express:sbx-9`) and `--json` rows gain `"provider": "<id>"` while keeping the bare id in the id field. Rationale: an unqualified id is ambiguous exactly when more than one provider is in play, and a bare id typed later resolves against the ambient provider, which may have changed since the id was printed. Input accepts the qualified form for every provider at all times. A bare id resolves against the effective provider (§4.4).
* If an explicit `--provider P` conflicts with a qualified reference `Q:id`, the command exits 2 (`E8030 ProviderMismatchError`).
* `ebx list --all-providers` lists every *configured* provider (those with the required credentials) and adds a `PROVIDER` column / `provider` key; providers that fail are reported as warnings and skipped (exit 0 if at least one succeeded).
* Template catalogs are provider-scoped; `template build/deploy/install` require `templates.build`; a provider without it fails fast with `E8004` before any Docker work starts.
* Per-provider credentials are isolated (§4.6). `ebx provider config <id> list` shows only that provider's scoped keys plus the core keys it uses.

### 7.8 SDK usage

```python
sb = await Sandbox.create(template="base")                              # unchanged: alicloud-express
sb = await Sandbox.create(template="base", provider="local-process")    # explicit
sb = await Sandbox.create(provider="my-cloud", provider_options={"cluster": "prod"})
sb.provider  # "my-cloud"
sb = await Sandbox.create(provider=my_provider_instance)               # a Provider object is accepted too (tests, programmatic)
sb = await Sandbox.create(provider="my-cloud", secure=False)           # sent to the plugin only because it was passed
url, headers = await sb.network.resolve(8080)                          # asks the plugin's ports.url when declared
```

`provider_options` both configure the provider and, for `exec` plugins, arrive (minus secret fields) as `options` in `sandbox.create`; `secure` is `None` by default and then not sent (the built-in provider treats `None` as `True`). `Sandbox.network.get_url(port)` remains the synchronous local computation; `resolve()`/`resolve_url()` are the provider-aware forms. `ProcessInfo.pid` and `commands.kill(pid)` take `int | str`.

`LocalSessionStore` sessions remember the provider. **Planned, not yet implemented**: `sandbox.yaml` `provider:` / `provider_options:` and `@sandbox(provider=...)` (the declarative layer is owned by another workstream; tracked in the follow-ups).

`EBX_PROVIDER`, `./.env`, `~/.ebx/.env` and `[core] provider` apply as in §4.4. `easy_sandbox.providers` exports `Provider`, `ProviderFeature`, `ConfigField`, `register_provider`, `get_provider`, `list_providers`, `resolve_provider_id`, and the install/store API. `python -m easy_sandbox.providers {list,info,install,uninstall,update,default,test,doctor}` mirrors the CLI for SDK-only users (same layout, same receipts, same digest).

---

## 8. Security model

### 8.1 Threat model

An `exec` plugin is **third-party code run with your user privileges and your credentials for that provider**. Installing it is a trust decision, exactly like `pip install` of a tool you then run. We cannot sandbox it portably. The design therefore concentrates on: (1) not running anything at install, (2) knowing exactly what was installed (pin + digest + consent record), (3) detecting later tampering, (4) minimising what the process receives, (5) containing crashes and hangs, (6) refusing dangerous install inputs.

### 8.2 Install-time hardening

* **No auto-exec, no checkout.** No `setup.py`/`postinstall`/Makefile/hook is run. Git sources are fetched with `git clone --depth 1 --no-checkout --filter=blob:limit=10m --no-recurse-submodules`, then the tree is **enumerated with `git ls-tree -r -z -l <commit>` and validated before any file is written** (only mode `100644`/`100755` blobs; symlinks `120000`, submodules `160000` and anything else are rejected; sizes and counts checked), and the blobs are read with `git cat-file --batch` and written by the installer itself. There is therefore no `git checkout`, so no smudge/clean filters, `.gitattributes` drivers, `core.autocrlf` rewriting, hooks, or case-insensitive-filesystem overwrites. Git runs with `-c core.hooksPath=<empty dir> -c core.fsmonitor=false -c protocol.file.allow=never -c protocol.ext.allow=never -c http.followRedirects=false`, `GIT_TERMINAL_PROMPT=0`, `GIT_ALLOW_PROTOCOL=https:ssh`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL` pointing at an empty file (so `url.<x>.insteadOf` rewrites and credential helpers from the user's git config cannot redirect or leak), a scrubbed environment (no `GIT_SSH_COMMAND`, `GIT_ASKPASS`, `GIT_EXEC_PATH`), and a timeout. Consequence, documented: private HTTPS repositories that need a git credential helper are installed by cloning yourself and installing the directory; SSH sources use the SSH agent as usual. A redirect to another host is refused.
* **Pinning**: the resolved commit SHA and the tree digest are always stored, and the installed content is immutable afterwards (digest checked on every spawn). `trust` records how the user vetted the source: `--ref <40-hex>` or `--sha256` ⇒ `pinned`; a tag/branch ⇒ `unpinned` (the ref could have moved between review and install; the consent screen shows the resolved commit and digest so it can be verified out of band). Unattended runs (non-interactive) refuse `unpinned` unless `--allow-unpinned`. `update` never changes the recorded source URL.
* **Filesystem safety**: entries must be regular files or directories; symlinks, hardlinks, devices, FIFOs are rejected; paths are normalised and must stay inside the plugin root (`..`, absolute, drive-letter and NUL rejected, case-fold collisions rejected); limits: ≤ 2000 files, ≤ 50 MiB total, ≤ 10 MiB per file; the manifest ≤ 256 KiB; directory mode 0700, files 0600 (+x only where the source had it).
* **Credentials in URLs** rejected and **redacted** in receipts/logs.
* **Name safety**: id grammar and reserved ids; an id already installed requires `--force` (and is then an update); a plugin cannot replace the built-in or a first-party id.
* **`--link`** (development symlink install, no copy and no integrity check) requires an interactive confirmation or `--yes`, is recorded as trust `link`, and every use prints `warning: provider <id> is a linked development install` to stderr.
* **Windows**: replacing a provider directory whose plugin process is running fails with `E8010` (`provider 'x' is in use`); the swap is retried once after 1 s.

### 8.3 Run-time hardening

* **Env scrubbing**: the process environment is `PATH`, `HOME`/`USERPROFILE`, `TMPDIR`/`TEMP`, `LANG`/`LC_*`, `SYSTEMROOT`/`ComSpec` (Windows), the manifest's `env_passthrough`, `EBX_PROVIDER_DATA_DIR`, and `PYTHONDONTWRITEBYTECODE=1` (an interpreter must not write `__pycache__` into the digest-verified plugin directory). **No** `EBX_*`, `E2B_*`, `ALICLOUD_*`, `GITHUB_TOKEN`, `OPENAI_*` etc. leak implicitly.
* **Credential delivery**: values are sent only in the `initialize` request, and only the fields the manifest declares (`config.fields` and `core.uses`). Secrets never appear in argv or the environment.
* `cwd` is the provider's data directory (`~/.ebx/providers/<id>/data/`, created 0700), never the user's project.
* Output caps: 8 MiB per protocol line, 64 KiB captured stderr ring; a process that exceeds them or violates framing is killed (`E8020`). Responses with unknown/duplicate ids are ignored; plugin-supplied text (messages, stderr tail, suggestions) is stripped of control characters/ANSI escapes before it is printed, and every value the host sent in `initialize` is redacted (exact match) from captured stderr and from error messages. `initialize` parameters are never logged, not even with `--verbose`.
* Timeouts and process-group kill (Windows Job Object) for hangs (`E8022`).
* Optional OS confinement (bwrap/sandbox-exec/Job limits) is reserved as `security.sandbox = "auto|off|require"` in user config; **not** implemented in v1 and the docs must not claim isolation.
* **Generic-key leakage guard**: §4.6 — a non-builtin provider receives `sandbox_api_key`/`sandbox_base_url`/`sandbox_domain` only through a consented `core.inherit`; `ebx provider doctor` prints the effective inherit list and warns when an inherited generic key is also the effective key of another configured provider.
* **Interpreter/dependency hygiene**: the installer never runs `pip`/`npm`; plugin authors vendor their dependencies. `cwd` is the (empty, 0700) data dir so no executable is picked up from the working directory.

### 8.4 Tamper detection and updates

Digest verification on every spawn (cost O(plugin size), plugins are small by the size limits); update re-consent on risk-relevant diffs; `.trash` rollback; `ebx provider info` shows commit, digest, trust and consent record.

### 8.5 What the guarantees are not

* Same-user file access: a malicious plugin could read `~/.ebx/.env`. Mitigations are consent, pinning, tamper detection and the declared-permissions record; true isolation needs OS keychains + confinement (future work).
* The `security` block (`network`, `filesystem`) is **advisory**: shown to the user and recorded, not enforced in v1.
* The receipt and digest detect accidental or third-party modification; a malicious process running as the same user can rewrite both. Signed receipts/attestations (Sigstore-style) are future work.

---

## 9. Error codes

New category **E8xxx — Provider errors** (all subclass `SandboxError`; see `reference/error-codes.md`):

| Code | Class | Meaning | CLI exit |
|---|---|---|---|
| E8000 | `ProviderError` | base | 1 |
| E8001 | `ProviderNotFoundError` | id unknown / not installed | 4 |
| E8002 | `ProviderConfigError` | unknown/invalid provider option, schema violation | 2 |
| E8003 | `ProviderConflictError` | duplicate or reserved id | 1 |
| E8004 | `ProviderFeatureNotSupportedError` (also a `CapabilityNotSupportedError`) | provider lacks the feature | 1 |
| E8010 | `ProviderInstallError` | source unreachable, size/path limits | 1 |
| E8011 | `ProviderIntegrityError` | digest/pin mismatch, files changed since install | 1 |
| E8012 | `ProviderTrustError` | consent/pin/transport policy not satisfied | 2 |
| E8013 | `ProviderVersionError` | `requires` or protocol unsupported | 1 |
| E8014 | `ProviderManifestError` | invalid manifest | 1 |
| E8020 | `ProviderProtocolError` | malformed JSON-RPC, handshake failure | 1 |
| E8021 | `ProviderProcessError` | spawn failure / crash (stderr tail attached) | 1 |
| E8022 | `ProviderTimeoutError` | startup or call timeout | 5 |
| E8030 | `ProviderMismatchError` | sandbox belongs to another provider | 2 |

Missing *credential* fields (`credential = true`) raise the existing `InvalidCredentialsError` (E1003, exit 3) naming the provider key and all its env names.

---

## 10. Testing strategy

1. **Key registry / alias table**: table-driven tests assert every row of §5 (each alias resolves to the canonical key, in every layer, in the documented order, for `load_config`, `explain_config`, `http_timeout_configured`).
2. **Language-neutral resolution vectors** (`client-sdk/tests/fixtures/config_resolution_vectors.json`, mirrored to `cli/docs/design/fixtures/`): each vector is `{sources:{overrides, environ, dotenv:[{…},{…}], toml}, provider, expect:{key:{value, source, name}}}`. Python tests run them against the Python resolver; the CLI worker runs the same file against the Node resolver. A test asserts the two copies are identical when both repos are present.
3. **Back-compat suite**: the pre-existing 1348 SDK tests must pass unchanged; new tests pin `TransportConfig(api_key=…)`, `.api_key/.api_url/.domain` read/write, `load_config(api_url=…)`, `Sandbox.create(api_key=…)` default-provider path (existing mocks of `load_config/create_auth_provider/HttpClient/SandboxProtocol` keep working).
4. **Manifest**: valid/invalid manifests (every validation rule), version comparator, id grammar, reserved ids.
5. **Store/installer**: local dir, git (local bare repo through `file://` only in tests with the insecure flag), pinned/unpinned, symlink/path-traversal/size-limit rejection, credential-in-URL rejection, tree-digest vectors (shared with Node), integrity failure after tampering, update with re-consent, rollback (including exact restoration of `data/` after a failed handshake or a failed swap), uninstall/purge, default-provider fallback, concurrent-lock behaviour, no code executed at install (a plugin whose `provider.py` writes a canary file proves it).
6. **EPP client** against the reference plugin: handshake, version mismatch, feature gating, error mapping table, timeouts, crash, malformed lines, oversized lines, stderr capture, env scrubbing (the plugin echoes its env), process-group kill, cancel.
7. **Sandbox integration**: `Sandbox.create(provider="local-process")` → `commands.run`, `files.write/read/list/exists/remove`, `kill`, `connect`; unsupported feature → `E8004`; default path untouched.
8. **Contract tests**: `providers/testing.py` ships a reusable `ProviderContractTests` base (18 tests: declaration, lifecycle, idempotent kill, `set_timeout`, pause/resume, exec exit code/stderr/env, stream order and a single exit, timeout enforcement, process list, files text/binary/directories/move/missing → typed not-found, `ports.url`, undeclared feature → E8004, secret redaction). Run it with `python -m easy_sandbox.providers test <id> [--option K=V]` (fails when nothing is collected), with `pytest -p easy_sandbox.providers.testing --pyargs easy_sandbox.providers.contract --provider-under-test <id>`, or by subclassing. Tests for undeclared features expect E8004; declared ones must work.
8a. **Method table**: `epp-methods.json` (above) is checked against the host adapters in both directions, and a recording-client test pins parameter names/types (`files.move` is `source`/`destination`, `process_id` is a string, `pid` is `string|integer`, `secure` only when set, `options` without secrets).
9. **Reference plugins** (`examples/providers/`): `e2b-compatible` (kind `rest`, manifest only) and `local-process` (kind `exec`, Python stdlib, ~200 lines: lifecycle, exec, files). Used by tests and as templates for authors. The Node CLI tests use the same directories.

---

## 11. Implementation map (Python SDK)

| Piece | Module |
|---|---|
| Key registry, alias tables, resolver, schema export | `easy_sandbox/utils/config_keys.py` |
| `TransportConfig`, `load_config`, `explain_config`, `audit_config`, `migrate` | `easy_sandbox/transport/config.py` |
| Provider interface, features, registry | `easy_sandbox/providers/{base,registry}.py` |
| Built-in provider | `easy_sandbox/providers/builtin.py` |
| Manifest + version comparator | `easy_sandbox/providers/manifest.py` |
| Store, installer, digest | `easy_sandbox/providers/{store,installer}.py` |
| EPP client + adapters | `easy_sandbox/providers/exec_provider.py` |
| REST provider | `easy_sandbox/providers/rest_provider.py` |
| Contract-test kit | `easy_sandbox/providers/{testing,contract}.py` |
| `python -m easy_sandbox.providers` | `easy_sandbox/providers/__main__.py` |
| Errors E8xxx | `easy_sandbox/models/errors.py` (appended) |
| `provider=` plumbing | `easy_sandbox/api/sandbox.py` (`_build_infra`, `create/connect/list/kill_by_id`) |

The Node CLI re-implements the same contracts from the spec in `cli/docs/design/providers-and-credentials-cli.md`.
