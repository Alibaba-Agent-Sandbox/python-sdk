# Providers and Credentials — Naming Scheme and Provider Plugin Architecture

> **Status: superseded for catalog providers** wherever this page describes a gRPC or localhost plugin server as the way an SDK reaches a provider. The current design is the Node engine: HTTP, SSE and WebSocket on `127.0.0.1`, protocol `abx-engine/1`. See [cli/docs/en/reference/engine-api.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md) and [Node provider architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/node-provider-architecture.md). The v1 tradeoff table below is kept as history.

> **Status**: Accepted (design reviewed in two adversarial rounds, see [providers-and-credentials-review.md](../archive/providers-and-credentials-review.md)) · **Scope**: Python SDK (`client-sdk`) and the Node.js `abx` CLI · **CLI-facing spec**: `cli/docs/design/providers-and-credentials-cli.md`
>
> **Naming rule**: each configuration key has exactly one environment variable. That variable is the only name a reader accepts, and it is the name `abx config set` writes. There is no second name and no migration command.

---

## 0. Goals, non-goals

**Goals**

1. One coherent naming scheme for every credential / configuration key, in every surface: `config.toml`, `~/.abx/.env`, `abx config set/get`, environment variables, SDK `TransportConfig` fields and `Sandbox.*` keyword arguments, CLI flags.
2. One environment variable per key, documented in §3. A reader stops at the first layer that sets that variable.
3. A provider abstraction so that backends other than Alibaba Cloud can be added later by **plugins**, installed with `abx provider install <path-or-git-url>` (CLI) or `python -m agent_sandbox.providers install ...` (SDK-only users), selectable per command (`--provider`), per process (`ABX_PROVIDER`), per project (`./.env`), per user (config), and per SDK call (`Sandbox.create(provider=...)`).
4. The built-in provider stays the default and is presented as **Alibaba Cloud Express Edition (阿里云极速版)** with the stable id `alicloud-express`.

**Non-goals (v1)**

* Running untrusted plugin code in a hard sandbox (cross-platform it is not achievable; we do consent + pinning + integrity + env scrubbing instead, see §8).
* A public plugin registry / marketplace (the manifest has a reserved `source` slot; v1 installs from a directory or a git URL only).
* Renaming `ABX_SERVER_*`, `ABX_PTY_PORT`, `ABX_MAX_UPLOAD_SIZE` (in-sandbox server variables baked into deployed images).

---

## 1. Inventory

Sources scanned: `transport/config.py`, `transport/auth.py`, `models/config.py`, `models/errors.py`, `api/{sandbox,deploy,docker_builder,image,fc_template}.py` (the build and deploy modules were later removed from the client), `declarative/decorator.py`, `agent/{mcp,mcp_http}.py`, `utils/{github_token,registry,template_index,logging}.py`, the CLI, `agent/qwen_code.py`, `.env.example`, and the docs (`reference/configuration.md`, `guide/environment-variables.md`, `guide/authentication.md`).

### 1.1 Sandbox control plane / transport

| Concept | `abx config` key | config.toml | Environment variable | SDK field / kwarg |
|---|---|---|---|---|
| Sandbox API key | `sandbox_api_key` | secret in `~/.abx/.env` | `ABX_SANDBOX_API_KEY` | `sandbox_api_key` |
| Platform base URL | `sandbox_base_url` | `[transport] sandbox_base_url` | `ABX_SANDBOX_BASE_URL` | `sandbox_base_url` |
| Data-plane domain | `sandbox_domain` | `[transport] sandbox_domain` | `ABX_SANDBOX_DOMAIN` | `sandbox_domain` |
| Region | `region` | `[providers.alicloud-express] region` | `ALIBABA_CLOUD_REGION_ID` | `region` |
| HTTP timeout | `http_timeout` | `[transport] http_timeout` | `ABX_HTTP_TIMEOUT` | `http_timeout` |
| HTTP/2 | `http2` | `http2` | `ABX_HTTP2` | `http2` |
| Max retries | `max_retries` | `max_retries` | `ABX_MAX_RETRIES` | `max_retries` |
| Log level | `log_level` | `log_level` | `ABX_LOG_LEVEL` | `log_level` |
| Default template | `default_template` | `default_template` | `ABX_DEFAULT_TEMPLATE` | `default_template` |
| Provider | `provider` | `[core] provider` | `ABX_PROVIDER` | `provider` |

Sandbox TTL (`Sandbox.create(timeout=)`, `--timeout/-t`) is not an HTTP timeout.

### 1.2 Alibaba Cloud (provider-specific)

| Concept | `abx config` key | Environment variable | Notes |
|---|---|---|---|
| AccessKey ID | `access_key_id` | `ALICLOUD_ACCESS_KEY_ID` | `~/.abx/.env` |
| AccessKey Secret | `access_key_secret` | `ALICLOUD_ACCESS_KEY_SECRET` | `~/.abx/.env` |
| ACR namespace | `acr_namespace` | `ACR_NAMESPACE` | |
| ACR registry | `acr_registry` | `ACR_REGISTRY` | |
| ACR repo | `acr_repo` | `ACR_REPO` | |
| ACR username / password | `acr_username` / `acr_password` | `ACR_USERNAME` / `ACR_PASSWORD` | |
| ACR EE instance | `acr_instance_id` | `ACREE_INSTANCE_ID` | |
| ACR EE network | `acr_vpc_id`, `acr_vswitch_ids`, `acr_security_group_id` | `ACR_VPC_ID`, `ACR_VSWITCH_IDS`, `ACR_SECURITY_GROUP_ID` | |
| Team id | `team_id` | `ABX_ALICLOUD_EXPRESS_TEAM_ID` | Optional. Not required. |

### 1.3 LLM / coding agent (provider-independent)

| Concept | Key | Environment variable |
|---|---|---|
| LLM API key | `llm_api_key` | `ABX_LLM_API_KEY` |
| LLM base URL | `llm_base_url` | `ABX_LLM_BASE_URL` |
| LLM model | `llm_model` | `ABX_LLM_MODEL` |
| Agent tuning | — | `ABX_QWEN_CODE_BIN`, `ABX_QWEN_RESEARCH_TIMEOUT`, `ABX_QWEN_CODEGEN_TIMEOUT` |

### 1.4 Integrations, tooling, UI

| Concept | Key | Environment variable | Notes |
|---|---|---|---|
| GitHub token | `github_token` | `GITHUB_TOKEN` | flag `--token` (template install/search/update). Stored in `~/.abx/.env`. |
| Template index URL | `template_index_url` | `ABX_TEMPLATE_INDEX_URL` | environment only |
| Template dir | `template_dir` | `ABX_TEMPLATE_DIR` | environment only |
| MCP server | `mcp_*` | `ABX_MCP_AUTH_TOKEN`, `ABX_MCP_ALLOWED_ORIGINS`, `ABX_MCP_RUNTIME_DIR` | environment only; sandbox calls use `ABX_SANDBOX_API_KEY` |
| CLI display | — | `ABX_ACTIVITY_LINES`, `ABX_DISCOVER_COMMANDS` | not stored by `abx config` |
| Shortcuts | `shortcuts`, `shortcuts.<name>` | — | `[shortcuts]` table of `config.toml` |
| Secret store | — | — | `~/.abx/secrets.json` (SDK `SecretStore`, 0600) — not a config surface |

### 1.5 In-sandbox server (`agent-sandbox-server`) — out of scope for renames

`ABX_SERVER_TOKEN`, `ABX_SERVER_BASE_DIR`, `ABX_SERVER_ENABLED_GROUPS`, `ABX_PTY_PORT`, `ABX_MAX_UPLOAD_SIZE`. They are runtime variables of container images that already exist in the wild; they follow the `ABX_` prefix and are left unchanged.

### 1.6 External / standard variables the tools honour (never renamed)

`CI`, `GITHUB_ACTIONS`, `GITLAB_CI`, `JENKINS_URL`, `NO_COLOR`, `TERM`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `DOCKER_BUILDKIT`, `HOME`, `APPDATA`, `COMSPEC`.

### 1.7 Other configuration surfaces

| Surface | Names | Treatment |
|---|---|---|
| `sandbox.yaml` (`SandboxDeclarativeConfig`) and `@sandbox(...)` | `template`, `timeout`, `envs`, `cpu`, `memory`, plus `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain` | also `provider`, `provider_options` |
| `GlobalConfig` (`models/config.py`) | the same field names as `TransportConfig` | plain data model |
| Session store (`~/.abx/sessions/*.json`, `SessionInfo`) | `sandbox_base_url`, `sandbox_domain`, `envd_access_token` | optional `provider` (default `""` = built-in) so a re-attached session talks to the same provider |
| `Sandbox.create(secure=, request_timeout=, timeout=)` | per-call options | unchanged (not credentials) |
| Coding-agent backend id (`qwen-code`, `DEFAULT_CODING_AGENT`) | — | a *coding agent* is not a *provider*; kept apart (see glossary) |
| `~/.qwen/settings.json` | agent-owned credential file the Qwen Code CLI reads | external file, never written or renamed by abx |
| Agent variables forwarded into sandboxes | `ANTHROPIC_API_KEY`, `QODER_PERSONAL_ACCESS_TOKEN`, and the agent's own key variables | in-sandbox agent credentials, forwarded as-is; not abx config |

**Glossary (terms that must not be mixed up).** *Provider*: a backend that creates and runs sandboxes (`alicloud-express`, a plugin). *Feature*: something a provider implements (§7.2). *Template capability*: what a sandbox *image* serves (`shell`, `files`, `code`, `terminal`, `ports`; `models/template.py`). *Coding agent*: the LLM CLI used for natural-language template generation (`qwen-code`). *Core key*: provider-independent configuration key. *Scoped key*: declared by one provider.

### 1.8 One name

Every key in §3 has one environment variable. Product settings use `ABX_<KEY>`. A vendor variable that the product adopts is that one name: `ALICLOUD_ACCESS_KEY_ID`, `ALICLOUD_ACCESS_KEY_SECRET`, `ALIBABA_CLOUD_REGION_ID`, `ACR_*`, `ACREE_INSTANCE_ID`, `GITHUB_TOKEN`. `team_id` is optional and uses `ABX_ALICLOUD_EXPRESS_TEAM_ID`. A plugin's own field uses `ABX_<PROVIDER>_<KEY>`.

---

## 2. Naming principles

1. **Keys are `snake_case`, one name per concept, identical in every surface.** The config key, the SDK field, the keyword argument and the flag (kebab-cased) are the same word: `sandbox_base_url` / `--sandbox-base-url`.
2. **Prefix = what the value is about.** `sandbox_*` for the sandbox control/data plane (generic, protocol level); `llm_*` for the LLM profile; `acr_*` for the container registry; `mcp_*` for the MCP server; `http_*` for HTTP client tuning; bare words for provider-scoped keys inside their provider namespace (`region`, `access_key_id`).
3. **One environment variable per key.** Product settings use `ABX_` + `UPPER(key)` (`sandbox_api_key` → `ABX_SANDBOX_API_KEY`). A vendor that already publishes a variable keeps that variable, and that variable is the only name: Alibaba Cloud access keys are `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`, the region is `ALIBABA_CLOUD_REGION_ID`, ACR settings are `ACR_NAMESPACE` and the matching `ACR_*` names, and the GitHub token is `GITHUB_TOKEN`. `team_id` is optional; its variable is `ABX_ALICLOUD_EXPRESS_TEAM_ID`. A plugin field is `ABX_` + `UPPER(provider_id with - → _)` + `_` + `UPPER(key)`.
4. **Provider scoping.** Keys are either *core* (provider-independent: `provider`, `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, `http_*`, `max_retries`, `llm_*`, `github_token`, `mcp_*`, ...) or *provider-scoped* (declared by a provider's config schema: `region`, `access_key_id`, `access_key_secret`, `acr_*`, `team_id` for `alicloud-express`). A provider may also declare that it consumes core keys (`uses_core`) and may **override** them in its own scope (`providers.<id>.sandbox_api_key`), which is how two providers get two different API keys.

---

## 3. The scheme

### 3.1 Core keys

| Key | Type | Secret | Environment variable | Default |
|---|---|---|---|---|
| `provider` | id | no | `ABX_PROVIDER` | `alicloud-express` |
| `sandbox_api_key` | str | **yes** | `ABX_SANDBOX_API_KEY` | none |
| `sandbox_base_url` | url | no | `ABX_SANDBOX_BASE_URL` | provider-derived (see §4.5) |
| `sandbox_domain` | host | no | `ABX_SANDBOX_DOMAIN` | provider-derived |
| `http_timeout` | float ≥ 1 | no | `ABX_HTTP_TIMEOUT` | `30.0` |
| `http2` | bool | no | `ABX_HTTP2` | `true` |
| `max_retries` | int ≥ 0 | no | `ABX_MAX_RETRIES` | `3` |
| `max_connections`, `max_keepalive_connections`, `keepalive_expiry`, `ws_ping_interval`, `retry_base_delay` | num | no | `ABX_<KEY>` | as today |
| `log_level` | enum | no | `ABX_LOG_LEVEL` | `WARNING` |
| `default_template` | str | no | `ABX_DEFAULT_TEMPLATE` | `base` |
| `llm_api_key` | str | **yes** | `ABX_LLM_API_KEY` | none |
| `llm_base_url` | url | no | `ABX_LLM_BASE_URL` | DashScope compatible-mode |
| `llm_model` | str | no | `ABX_LLM_MODEL` | `qwen3-coder-plus` |
| `github_token` | str | **yes** | `GITHUB_TOKEN` | none |
| `template_index_url` | url | no | `ABX_TEMPLATE_INDEX_URL` | built-in index |
| `template_dir` | path | no | `ABX_TEMPLATE_DIR` | none |
| `mcp_auth_token` | str | **yes** | `ABX_MCP_AUTH_TOKEN` | none |
| `mcp_allowed_origins`, `mcp_runtime_dir` | str | no | `ABX_MCP_ALLOWED_ORIGINS`, `ABX_MCP_RUNTIME_DIR` | none |

Env-only tuning that is **not** a persistent config key (documented in the environment-variable guide, unchanged): `ABX_ACTIVITY_LINES`, `ABX_DISCOVER_COMMANDS`, `ABX_QWEN_CODE_BIN`, `ABX_QWEN_RESEARCH_TIMEOUT`, `ABX_QWEN_CODEGEN_TIMEOUT`, and the in-sandbox server variables (§1.5).

`sandbox_domain` and `sandbox_base_url` are generic because every E2B-protocol backend has a control-plane URL and a data-plane domain; providers that have neither simply do not declare them in `uses_core`.

### 3.2 Provider-scoped keys: built-in `alicloud-express`

| Key (scoped) | Type | Secret | Environment variable | Notes |
|---|---|---|---|---|
| `region` | str | no | `ALIBABA_CLOUD_REGION_ID` | Derives base URL/domain (§4.5). Default `cn-hangzhou`. |
| `access_key_id` | str | no (id) | `ALICLOUD_ACCESS_KEY_ID` | `credential` |
| `access_key_secret` | str | **yes** | `ALICLOUD_ACCESS_KEY_SECRET` | `credential` |
| `acr_namespace` | str | no | `ACR_NAMESPACE` | |
| `acr_registry` | str | no | `ACR_REGISTRY` | |
| `acr_repo` | str | no | `ACR_REPO` | |
| `acr_username` | str | no | `ACR_USERNAME` | |
| `acr_password` | str | **yes** | `ACR_PASSWORD` | |
| `acr_instance_id` | str | no | `ACREE_INSTANCE_ID` | |
| `acr_vpc_id` | str | no | `ACR_VPC_ID` | |
| `acr_vswitch_ids` | csv | no | `ACR_VSWITCH_IDS` | |
| `acr_security_group_id` | str | no | `ACR_SECURITY_GROUP_ID` | |
| `team_id` | str | no | `ABX_ALICLOUD_EXPRESS_TEAM_ID` | Optional. Not required. |

The built-in provider is the only one that implicitly consumes the generic `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain` (and, like every provider, the non-secret tuning keys `http_timeout`, `http2`, `max_retries`, ...). Plugins consume generic credentials/endpoints only through the explicit `inherit` opt-in of §4.6.

### 3.3 Where each name lives

**`~/.abx/config.toml`** (hand-edited or written by `abx config set`; read by SDK and CLI):

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

**`~/.abx/.env`** (0600, secrets and credential-like values). `abx config set` writes the one environment variable for the key:

| Key | Stored as |
|---|---|
| `sandbox_api_key` | `ABX_SANDBOX_API_KEY` |
| `access_key_id`, `access_key_secret` | `ALICLOUD_ACCESS_KEY_ID`, `ALICLOUD_ACCESS_KEY_SECRET` |
| `acr_namespace`, `acr_password`, and the other secret or credential-like `acr_*` values | the `ACR_*` / `ACREE_INSTANCE_ID` variable for that key |
| `llm_api_key` | `ABX_LLM_API_KEY` |
| `github_token` | `GITHUB_TOKEN` |
| `team_id` | `ABX_ALICLOUD_EXPRESS_TEAM_ID` (optional) |
| `sandbox_base_url`, `sandbox_domain`, `http_timeout`, `http2`, `max_retries`, `llm_base_url`, `llm_model` | the same key in `[transport]` |
| `region` | `region` in `[providers.alicloud-express]`; environment variable `ALIBABA_CLOUD_REGION_ID` |
| `provider` | `[core] provider` |

**SDK surface**

* `TransportConfig` fields: `provider`, `sandbox_base_url`, `sandbox_domain`, `sandbox_api_key`, `region`, `access_key_id`, `access_key_secret`, `http_timeout`, ..., plus `provider_options: dict[str, Any]`. `model_dump()` emits these names.
* `Sandbox.create/connect/list/kill_by_id/deploy` and `@sandbox(...)`: keyword-only parameters `sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, `region`, `provider`, `provider_options`, `access_key_id`, `access_key_secret`.

**CLI flags** (spec in the CLI doc): `--sandbox-api-key`, `--sandbox-base-url`, `--sandbox-domain`, `--region/-r`, `--provider`, `--opt KEY=VALUE`. `--acr-*` flags match `acr_*`. The environment variable for the enterprise instance is `ACREE_INSTANCE_ID`.

### 3.4 Bare keys vs qualified keys in `abx config`

`abx config get|set|delete KEY` accepts:

1. A **core key** (`sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`, ...).
2. A **qualified provider key** `providers.<id>.<key>` (unambiguous, works for every provider).
3. A **bare provider key** (`region`, `access_key_id`, ...). It resolves against the provider selected by `--provider` for the command, else the **default provider**. If the key does not exist in that provider's schema the command fails with exit 2 and names the qualified form of every installed provider that declares it.
4. `shortcuts` and `shortcuts.<name>` (reserved prefix; provider ids and keys can never start with `shortcuts`).

---

## 4. Precedence

### 4.1 Layers

```text
1. explicit        code kwargs / CLI flags / `--opt`
2. process env     os.environ
3. ./.env          project dotenv (first candidate)
4. ~/.abx/.env     user dotenv (second candidate)
5. ~/.abx/config.toml
6. default         provider-derived or built-in
```

A blank or whitespace-only value is *unset* in every layer (it never hides the next layer). Layers are tried in order. The first layer that sets the key's one variable decides.

### 4.2 One variable inside a layer

For key `K` resolved for provider `P`, the reader looks up exactly one environment variable:

1. a plugin's own field: `ABX_<P>_<K>`
2. a core product setting: `ABX_<K>`
3. a vendor variable that §3 names as the variable for that key (`ALICLOUD_ACCESS_KEY_ID`, `ALIBABA_CLOUD_REGION_ID`, `ACR_NAMESPACE`, `GITHUB_TOKEN`, ...)

There is no second variable for the same key. In `config.toml` the order is `[providers.<P>].<K>`, then `[transport].<K>`.

### 4.3 Layer-first dotenv

`./.env` and `~/.abx/.env` are separate layers. The project file wins for a key it sets. A key it omits still comes from `~/.abx/.env`.

### 4.4 Provider selection precedence

```text
explicit provider= / --provider
  > ABX_PROVIDER (process env)
  > ABX_PROVIDER in ./.env
  > ABX_PROVIDER in ~/.abx/.env
  > [core] provider in ~/.abx/config.toml     (`abx provider default NAME`)
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

Derivation applies only when the base URL was **not** given by an explicit argument or a **process environment** variable. Each derived key is applied with "set default" semantics, so a base URL/domain coming from `.env`/`config.toml` is kept and the other one is still derived from the region. When the URL is explicit by argument/env the domain is not derived (it stays the provider default). Providers without `derive` just use their static defaults.

### 4.6 Provider scoping rules (credential isolation)

* **Scoped beats generic** only while `P` is the active provider: `providers.<P>.<key>` / `ABX_<P>_<KEY>` outrank the generic name of a core key `P` is allowed to read.
* **Credentials and endpoints never cross providers.** Resolving for provider `P` never looks at `ABX_<Q>_*` or `[providers.Q]` for `Q ≠ P`.
* **The generic credential/endpoint keys (`sandbox_api_key`, `sandbox_base_url`, `sandbox_domain`) belong to the built-in provider.** Without this rule, switching the default provider would silently send the Alibaba Cloud key to a third-party plugin (and a plugin's key to the Alibaba endpoint). A non-builtin provider receives them **only** when (a) its manifest lists them in `[core] inherit` **and** (b) the user consented to that at install/update time (the receipt records the consented list; the consent screen prints a warning line naming the keys). The effective list is `manifest.inherit ∩ receipt.consented.inherit`. The reference `e2b-compatible` provider inherits all three, so `ABX_SANDBOX_API_KEY` and `ABX_SANDBOX_BASE_URL` are delivered to it only by that recorded consent.
* Non-secret tuning keys (`http_timeout`, `http2`, `max_retries`, pool/WS/backoff) are shared with every provider.
* LLM, GitHub and MCP keys are not provider credentials and are **never** delivered to a provider.
* A plugin's own credentials are scoped fields it declares (environment variable `ABX_<P>_<KEY>`).
* Plugin values reach a plugin process only through the `initialize` request, never through the environment (§8.3).

---

## 5. One environment variable per key

The tables in §3 are the whole set. `explain_config()` reports the layer and that one variable name. Secrets are masked.

`abx config set` writes the stored name in §3.3. There is no second storage name and no command that rewrites one name into another.

---

## 6. What readers accept

A reader accepts the variable in §3 and the matching config key. `load_config` and `TransportConfig` use `sandbox_api_key`, `sandbox_base_url`, and `sandbox_domain`. `abx config get|set` uses those keys.

---

## 7. Providers

### 7.1 Identity

* Built-in id **`alicloud-express`**, display name **Alibaba Cloud Express Edition** / **阿里云极速版**. Reasons for the id: vendor prefix (`alicloud`, same as `ALICLOUD_*` and the `alicloud` pip extra) + edition (`express`, the product tier the current API implements). Rejected: `e2b` (a *protocol* that many providers will speak), `fc` (a product family that may host other editions), `aliyun`/`default` (not stable: "default" changes meaning; the console brand may change), `alibaba` (too coarse). The display name may change; **the id never changes**.
* Id grammar: `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, 2–40 chars, no underscore (so `-`→`_` env mapping is injective). Reserved: `alicloud-express`, `default`, `all`, `none`, `builtin`, `shortcuts`, `core`, `transport`, `providers`, anything starting `abx-`, `e2b` and `alicloud-` (reserved for first-party editions).
* The default is **always** `alicloud-express` until the user runs `abx provider default <id>` / sets `ABX_PROVIDER`. A user who never touches providers sees no change in any output.

### 7.2 Capability matrix (feature flags)

A provider declares which **features** it implements. The SDK/CLI check the feature before calling; an unsupported feature raises `ProviderFeatureNotSupportedError` (`E8004`, subclass of the existing `CapabilityNotSupportedError`) — never an `AttributeError`/HTTP 404.

| Feature id | Meaning | Python SDK surface | CLI commands (need it) |
|---|---|---|---|
| `sandbox.lifecycle` | create / connect / list / info / kill | `Sandbox.create/connect/list/kill_by_id`, `info` | `create`, `list`, `info`, `kill`, `connect` |
| `sandbox.timeout` | change TTL | `set_timeout`, `refresh` | `sandbox timeout` |
| `sandbox.pause` | pause / resume | `pause`, `resume` | `sandbox pause/resume` |
| `exec.run` | run a command, buffered result | `commands.run` | `exec`, `run`, `shell` |
| `exec.stream` | streamed output | `commands.stream` | `exec --stream` |
| `process.manage` | list/kill/signal/stdin of processes | `commands.list/kill/send_*` | `sandbox process ...` |
| `pty` | interactive terminal | `get_terminal` | `connect --pty` |
| `files.rw` | read/write/list/stat/mkdir/remove/move | `files.*` | `files`, `upload`, `download` |
| `files.watch` | watch directories | `files.watch` | — |
| `files.transfer` | signed upload/download URLs | `upload_url/download_url` (this data plane raises `FileOperationError`) | — |
| `code.interpret` | stateful code contexts | `run_code`, `code.*` | `sandbox code` |
| `templates.read` | list/get templates | `Template*` read | `template list/info` |
| `templates.build` | build/deploy/delete templates (image build + register) | — (CLI only) | `template build/deploy/delete`, `deploy`, `install` |
| `ports.url` | public URL for a port | `network.get_url` | `sandbox system ports`, `url` |
| `ports.domain` | custom domains for a sandbox/template | — (no per-sandbox API) | — |
| `storage.mount` | mount object storage (OSS) | — (no per-sandbox API) | — |
| `network.vpc` | attach a VPC | — (template `vpcConfig` only) | `--vpc-id` family |
| `sessions` | sandbox identity survives the process (re-attach by id) | `Sandbox.connect` + `LocalSessionStore` | `session ...` |

`alicloud-express` implements all of them. A sandbox's capabilities stay the **template's capabilities** (unchanged); where the provider lacks the feature behind a capability token (`shell ← exec.run`, `files ← files.rw`, `code ← code.interpret`, `terminal ← pty`, `ports ← ports.url`) the call raises `E8004` at call time. The implementation does not intersect the two sets up front: the template is provider-independent data, and failing at the call with a precise error is simpler and cannot disagree with the provider's behaviour.

### 7.3 Tradeoff analysis: how do plugins load?

Requirement: one plugin should serve **both** the Python SDK and the Node CLI.

| Option | One plugin for both languages | Install-time risk | Run-time isolation | Streaming/perf | Effort | Verdict |
|---|---|---|---|---|---|---|
| **A. Native per language** (Python entry point; npm module) | No — two implementations per provider | pip/npm execute build/setup code at install | In-process: full trust, can crash/hang the host | Best | Low per language | **Keep only as SDK-side advanced path** (`register_provider()`, entry-point group `agent_sandbox.providers`); not installable by `abx provider install` |
| **B. Executable + JSON-RPC over stdio (EPP/1)** | **Yes** | None (copy + validate; nothing runs) | Separate process: crash/hang/timeouts contained, env scrubbed, can be wrapped by OS sandbox later | Good for control plane; file bytes are base64-in-JSON (use C for heavy data) | Medium (one client per language) | **Primary** |
| **C. REST-compatible `base_url`** (E2B protocol, declarative manifest) | **Yes**, no code at all | None | Nothing to isolate | Native speed (built-in transport) | Lowest | **Primary for E2B-protocol backends** |
| D. gRPC/HTTP plugin server on localhost | Yes | None | Process, but port allocation, auth of the local port, firewall prompts | Best streaming | High (codegen, lifecycle, ports) | Rejected for v1. A later evaluation of gRPC as the SDK-to-provider transport for catalog providers was not adopted; those providers use the Node engine named in the status at the top of this page |
| E. WASM component | Yes | None | Strong | Limited I/O story today | Very high | Rejected for v1 |

**Decision: B + C, plus A as an SDK-only escape hatch.** Both B and C describe a plugin with a *manifest* (`abx-provider.toml`); the manifest's `runtime.kind` is `rest` (C) or `exec` (B). The recommended architecture for a new backend is: *implement the E2B envd data-plane protocol* (or reuse it) and ship an `exec` plugin for **only the control plane** (create/connect/list/kill returning `envd_url` + token) — the data plane (exec, files, PTY, code) then flows through the fast native transports in the SDK and CLI. A backend with no envd compatibility implements the data-plane methods (`exec.run`, `files.*`) in the plugin too, accepting base64 overhead. That paragraph is the v1 loading decision and is kept. Catalog providers since then are `node` (`node/1`): the Node host loads `provider.mjs`. See the status at the top of this page.

### 7.4 The provider contract

**Python SDK interface** (`agent_sandbox.providers.base`):

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
| `pty.open` | `{sandbox_id, cols?, rows?}` | `{process_id}`, then notifications `pty.output{process_id, data_b64}` and one `pty.exit{process_id}` | `pty` | R |
| `pty.write` / `pty.resize` / `pty.close` | `{sandbox_id, process_id, data_b64 \| cols, rows \| —}` | `{}` | `pty` | R |

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

**Version negotiation.** `epp/1`; backwards-compatible additions bump only the manifest's `protocol_minor` hint. A host refuses a manifest whose `protocol` is not one it supports (`E8013`). `requires_abx` (below) gates SDK/CLI versions.

### 7.5 Manifest: `abx-provider.toml`

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

[config.fields.workdir_root]              # provider-scoped schema -> `abx provider config`, validation, env names
type = "path"                             # string | int | float | bool | enum | path | url | csv
required = false
secret = false
credential = false                        # true: missing -> E1003 (exit 3) instead of E8002
default = ""
description = "Directory that holds sandbox working dirs"
description_zh = "沙箱工作目录的根目录"
env = ["LOCAL_PROCESS_ROOT"]              # optional extra (native) env names for this plugin's own field; canonical ABX_LOCAL_PROCESS_WORKDIR_ROOT is automatic. Names starting ABX_, E2B_, ALICLOUD_ are refused.
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

**Validation rules (both languages)**: `manifest_version == 1`; id grammar and reserved ids; `command` is a non-empty array of strings without NUL; the executable path must resolve **inside** the plugin dir when it starts with `./` or `../` (no escape); `.bat`/`.cmd`/`.ps1` launchers are rejected (they need a shell; Node refuses to spawn them without one) — Windows plugins use an `.exe` or an interpreter + script; `env_passthrough` may not name `ABX_*`, `E2B_*`, `ALICLOUD_*`; `core.inherit` ⊆ {`sandbox_api_key`,`sandbox_base_url`,`sandbox_domain`}; `[auth] any_of` references declared fields only; field keys match `^[a-z][a-z0-9_]*$`, never collide with a core key or `shortcuts*`; `type` known; secrets need no `default`; `features.supported` ⊆ the feature registry; unknown top-level tables are ignored (forward compat); file size ≤ 256 KiB.

### 7.6 Storage layout, install, trust

```text
~/.abx/providers/
  .lock                       # O_EXCL lock for install/update/uninstall
  .staging/                   # installs are assembled here and renamed atomically
  .trash/                     # previous version kept until the swap succeeded
  <id>/
    abx-provider.toml
    ... plugin files ...
    .abx-install.json         # receipt (below)
    data/                     # reserved for the plugin's own state; not hashed, kept on update, a source containing it is rejected
```

The directory is the source of truth; there is no separate index to drift. The default provider lives in `config.toml` `[core] provider`.

Receipt `.abx-install.json`:

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

**Tree digest (identical in Python and Node).** `tree_sha256 = SHA-256( for each regular file, sorted by UTF-8 path bytes: path + "\0" + ("x" if executable else "-") + "\0" + SHA-256(file bytes) + "\n" )`, paths POSIX-style relative to the plugin root, excluding `.git/`, `.abx-install.json` and the top-level `data/` directory. Everything else is hashed, including a plugin's `tests/` directory (it is installed and changes the digest; install a `--subdir` or keep tests small). Symlinks are rejected at install (§8). Both implementations are tested against the same vectors.

**Install algorithm** (`abx provider install <source>`):

1. Classify `<source>`: existing directory → `local`; `--link` → `link` (symlink to the directory, development only); git URL → `git` (`https://…`, `ssh://…`, `git@host:path`, optional `git+` prefix; `file://`, `ext::`, `git://` and `http://` are **rejected** unless `--allow-insecure-transport`; URLs with embedded credentials are rejected — use a credential helper/SSH agent).
2. Stage: local → copy with the safety rules of §8.2; git → `git clone --depth 1 --no-checkout`, `git checkout <ref>` with **hooks, filters, fsmonitor, submodules, LFS smudge and `core.sshCommand` disabled** and a scrubbed environment (§8.2), then copy the tracked files only. Resolve the ref to a full commit SHA.
3. Parse and validate the manifest (§7.5). Compute `tree_sha256`, `manifest_sha256`.
4. If `--sha256 DIGEST` is given, it must equal `tree_sha256` (`E8011` otherwise) → trust `pinned`. A git source whose `--ref` is a full 40-hex commit is `pinned`; a tag/branch is `unpinned` and refused in non-interactive mode unless `--allow-unpinned`.
5. **Consent**: print id, name, version, source, commit, digest, runtime command, declared security block, features, and the config fields (secrets marked). Interactive: `Install and trust this provider? [y/N]`. Non-interactive/CI: requires `--yes`, otherwise exit 2 (`E8012`).
6. Atomic swap into `<id>/` under the lock; write the receipt. **Nothing from the plugin is executed.** The first execution happens when a command uses it (or `abx provider doctor`).

**Run-time checks** (every spawn of an `exec` provider): receipt exists; `tree_sha256` of the directory equals the receipt (`E8011` on mismatch, message `provider files changed since install; reinstall or run 'abx provider update <id>'`) — skipped only for trust `link`/`local-dev`, which print a one-line `warning: provider <id> is a linked development install` on stderr; `requires` satisfied (`E8013`).

**Update** (`abx provider update [<id>|--all] [--ref R] [--check] [--yes] [--allow-unpinned] [--allow-insecure-transport] [--no-verify]`): re-fetch from the recorded source, show a diff summary (version, commit range, changed runtime/security/features/config fields); **re-consent required whenever runtime command, security block or feature list changed**, otherwise `--yes` suffices; pinned installs only move with an explicit `--ref`; previous version stays in `.trash/` until the new one passes `initialize`; on failure the previous files **and `data/`** are restored exactly. The receipt does not record `--allow-insecure-transport`: a `file://`/`http://`/`git://` source needs the flag on every update (re-asserting a deliberate act). `--check` prints available updates and changes nothing.

**Uninstall** (`abx provider uninstall <id> [--purge] [--yes]`): removes the directory. If it was the default provider the default falls back to `alicloud-express` and a notice is printed. Stored values (`[providers.<id>]`, `ABX_<ID>_*` in `~/.abx/.env`) are kept unless `--purge`.

### 7.7 Multi-provider rules

* Resolution per command: §4.4. A command talks to **one** provider.
* Sandbox ids are provider-local. The CLI has two output formats: **legacy format** (bare ids, no `provider` field — byte-identical to today) is used **iff both** the *ambient* provider (§4.4 without the explicit flag: `ABX_PROVIDER` → `./.env` → `~/.abx/.env` → config → built-in) **and** the *effective* provider (explicit flag or ambient) are `alicloud-express`. In every other situation the CLI uses the **qualified format**: ids are printed as `provider:sandbox_id` (e.g. `local-process:sbx-1`, `alicloud-express:sbx-9`) and `--json` rows gain `"provider": "<id>"` while keeping the bare id in the id field. Rationale: an unqualified id is ambiguous exactly when more than one provider is in play, and a bare id typed later resolves against the ambient provider, which may have changed since the id was printed. Input accepts the qualified form for every provider at all times. A bare id resolves against the effective provider (§4.4).
* If an explicit `--provider P` conflicts with a qualified reference `Q:id`, the command exits 2 (`E8030 ProviderMismatchError`).
* `abx list --all-providers` lists every *configured* provider (those with the required credentials) and adds a `PROVIDER` column / `provider` key; providers that fail are reported as warnings and skipped (exit 0 if at least one succeeded).
* Template catalogs are provider-scoped; `template build/deploy/install` require `templates.build`; a provider without it fails fast with `E8004` before any Docker work starts.
* Per-provider credentials are isolated (§4.6). `abx provider config <id> list` shows only that provider's scoped keys plus the core keys it uses.

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

`ABX_PROVIDER`, `./.env`, `~/.abx/.env` and `[core] provider` apply as in §4.4. `agent_sandbox.providers` exports `Provider`, `ProviderFeature`, `ConfigField`, `register_provider`, `get_provider`, `list_providers`, `resolve_provider_id`, and the install/store API. `python -m agent_sandbox.providers {list,info,install,uninstall,update,default,test,doctor}` mirrors the CLI for SDK-only users (same layout, same receipts, same digest).

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

* **Env scrubbing**: the process environment is `PATH`, `HOME`/`USERPROFILE`, `TMPDIR`/`TEMP`, `LANG`/`LC_*`, `SYSTEMROOT`/`ComSpec` (Windows), the manifest's `env_passthrough`, `ABX_PROVIDER_DATA_DIR`, and `PYTHONDONTWRITEBYTECODE=1` (an interpreter must not write `__pycache__` into the digest-verified plugin directory). **No** `ABX_*`, `E2B_*`, `ALICLOUD_*`, `GITHUB_TOKEN`, `OPENAI_*` etc. leak implicitly.
* **Credential delivery**: values are sent only in the `initialize` request, and only the fields the manifest declares (`config.fields` and `core.uses`). Secrets never appear in argv or the environment.
* `cwd` is the provider's data directory (`~/.abx/providers/<id>/data/`, created 0700), never the user's project.
* Output caps: 8 MiB per protocol line, 64 KiB captured stderr ring; a process that exceeds them or violates framing is killed (`E8020`). Responses with unknown/duplicate ids are ignored; plugin-supplied text (messages, stderr tail, suggestions) is stripped of control characters/ANSI escapes before it is printed, and every value the host sent in `initialize` is redacted (exact match) from captured stderr and from error messages. `initialize` parameters are never logged, not even with `--verbose`.
* Timeouts and process-group kill (Windows Job Object) for hangs (`E8022`).
* Optional OS confinement (bwrap/sandbox-exec/Job limits) is reserved as `security.sandbox = "auto|off|require"` in user config; **not** implemented in v1 and the docs must not claim isolation.
* **Generic-key leakage guard**: §4.6 — a non-builtin provider receives `sandbox_api_key`/`sandbox_base_url`/`sandbox_domain` only through a consented `core.inherit`; `abx provider doctor` prints the effective inherit list and warns when an inherited generic key is also the effective key of another configured provider.
* **Interpreter/dependency hygiene**: the installer never runs `pip`/`npm`; plugin authors vendor their dependencies. `cwd` is the (empty, 0700) data dir so no executable is picked up from the working directory.

### 8.4 Tamper detection and updates

Digest verification on every spawn (cost O(plugin size), plugins are small by the size limits); update re-consent on risk-relevant diffs; `.trash` rollback; `abx provider info` shows commit, digest, trust and consent record.

### 8.5 What the guarantees are not

* Same-user file access: a malicious plugin could read `~/.abx/.env`. Mitigations are consent, pinning, tamper detection and the declared-permissions record; true isolation needs OS keychains + confinement (future work).
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

1. **Key registry**: table-driven tests assert every row of §3 (the one environment variable resolves to the key, in every layer, for `load_config`, `explain_config`, `http_timeout_configured`).
2. **Language-neutral resolution vectors** (`client-sdk/tests/fixtures/config_resolution_vectors.json`, mirrored to `cli/docs/design/fixtures/`): each vector is `{sources:{overrides, environ, dotenv:[{…},{…}], toml}, provider, expect:{key:{value, source, name}}}`. Python tests run them against the Python resolver; the CLI worker runs the same file against the Node resolver. A test asserts the two copies are identical when both repos are present. `name` is the one variable from §3.
3. **Constructor suite**: tests pin `TransportConfig(sandbox_api_key=…)`, `load_config(sandbox_base_url=…)`, and `Sandbox.create(sandbox_api_key=…)` on the default-provider path (existing mocks of `load_config/create_auth_provider/HttpClient/SandboxProtocol` keep working).
4. **Manifest**: valid/invalid manifests (every validation rule), version comparator, id grammar, reserved ids.
5. **Store/installer**: local dir, git (local bare repo through `file://` only in tests with the insecure flag), pinned/unpinned, symlink/path-traversal/size-limit rejection, credential-in-URL rejection, tree-digest vectors (shared with Node), integrity failure after tampering, update with re-consent, rollback (including exact restoration of `data/` after a failed handshake or a failed swap), uninstall/purge, default-provider fallback, concurrent-lock behaviour, no code executed at install (a plugin whose `provider.py` writes a canary file proves it).
6. **EPP client** against the reference plugin: handshake, version mismatch, feature gating, error mapping table, timeouts, crash, malformed lines, oversized lines, stderr capture, env scrubbing (the plugin echoes its env), process-group kill, cancel.
7. **Sandbox integration**: `Sandbox.create(provider="local-process")` → `commands.run`, `files.write/read/list/exists/remove`, `kill`, `connect`; unsupported feature → `E8004`; default path untouched.
8. **Contract tests**: `providers/testing.py` ships a reusable `ProviderContractTests` base (18 tests: declaration, lifecycle, idempotent kill, `set_timeout`, pause/resume, exec exit code/stderr/env, stream order and a single exit, timeout enforcement, process list, files text/binary/directories/move/missing → typed not-found, `ports.url`, undeclared feature → E8004, secret redaction). Run it with `python -m agent_sandbox.providers test <id> [--option K=V]` (fails when nothing is collected), with `pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract --provider-under-test <id>`, or by subclassing. Tests for undeclared features expect E8004; declared ones must work.
8a. **Method table**: `epp-methods.json` (above) is checked against the host adapters in both directions, and a recording-client test pins parameter names/types (`files.move` is `source`/`destination`, `process_id` is a string, `pid` is `string|integer`, `secure` only when set, `options` without secrets).
9. **Reference plugins** (`examples/providers/`): `e2b-compatible` (kind `rest`, manifest only) and `local-process` (kind `exec`, Python stdlib, ~200 lines: lifecycle, exec, files). Used by tests and as templates for authors. The Node CLI tests use the same directories.

---

## 11. Implementation map (Python SDK)

| Piece | Module |
|---|---|
| Key registry, resolver, schema export | `agent_sandbox/utils/config_keys.py` |
| `TransportConfig`, `load_config`, `explain_config` | `agent_sandbox/transport/config.py` |
| Provider interface, features, registry | `agent_sandbox/providers/{base,registry}.py` |
| Built-in provider | `agent_sandbox/providers/builtin.py` |
| Manifest + version comparator | `agent_sandbox/providers/manifest.py` |
| Store, installer, digest | `agent_sandbox/providers/{store,installer}.py` |
| EPP client + adapters | `agent_sandbox/providers/exec_provider.py` |
| REST provider | `agent_sandbox/providers/rest_provider.py` |
| Contract-test kit | `agent_sandbox/providers/{testing,contract}.py` |
| `python -m agent_sandbox.providers` | `agent_sandbox/providers/__main__.py` |
| Errors E8xxx | `agent_sandbox/models/errors.py` (appended) |
| `provider=` plumbing | `agent_sandbox/api/sandbox.py` (`_build_infra`, `create/connect/list/kill_by_id`) |

The Node CLI re-implements the same contracts from the spec in `cli/docs/design/providers-and-credentials-cli.md`.

---

## 12. Amendments (2026-10-13 review)

These rules were added after driving a real OpenSandbox server through the abstraction (see [2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md)). They apply identically to the Python SDK and the Node CLI.

1. **One "sandbox not found".** A `-32002` from `sandbox.get`, `sandbox.connect`, `sandbox.set_timeout`, `sandbox.pause` or `sandbox.resume` is raised as `SandboxNotFoundError` (E2009, exit 4), the same class the built-in provider raises. `data.sdk_code = "E2009"` is accepted from a plugin. `sandbox.kill` of an unknown id stays a no-op. Every other `-32002` keeps the old mapping (`sdk_code` class, else E8005).
2. **Features are enforced for every kind.** `exec` adapters and the new `feature_gate` (for `rest`) raise `ProviderFeatureNotSupportedError` (E8004) for a method whose feature is not in `[features] supported`, before any request is made. The gate table is `SANDBOX_RULES`, `PROCESS_RULES`, `FILESYSTEM_RULES`, `CODE_RULES`; a method needs at least one of its listed features.
3. **Listing shows features.** `provider list` returns `features` (ordered by the registry) per provider; the text form groups them (`sandbox(lifecycle,pause) exec(run,stream) pty`).
4. **Unpinned installs.** `--yes` does not accept a branch, tag or missing ref. Accepting one needs an interactive review (a `confirm` callback, no `--yes`) or `--allow-unpinned`. The refusal (E8012) names the head commit to pin. `update` follows the same rule.
5. **Plugin records carry no built-in defaults.** `region` is empty unless the plugin reports it, and `timeout` is `expires_at - created_at` when both are given.
6. **`[template]` is for authoring.** It never changes what the create-time `template` string means; that is plugin-defined (OpenSandbox: an image URI).
7. **Manifest name.** The manifest is `abx-provider.toml`. A plugin root without it fails with E8014 ("file not found at the plugin root") and points at `owner/repo//subdir` / `--subdir`.
8. **Conformance.** The contract kit expects `SandboxNotFoundError` (E2009) for an unknown id.
