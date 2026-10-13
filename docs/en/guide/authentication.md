# Authentication

> **Note:** The `ebx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @easy-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`easy-sandbox`) and the container-side runtime (`easy-sandbox-server`).

Easy Sandbox supports two authentication modes: **API Key** and **AK/SK (Alibaba Cloud AccessKey)**.

Credentials belong to a [provider](providers.md). The built-in provider is **Alibaba Cloud Express Edition (阿里云极速版)**, id `alicloud-express`, and it is the default. The sandbox key is `EBX_SANDBOX_API_KEY`. Alibaba Cloud access keys use the official names `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`. The region is `ALIBABA_CLOUD_REGION_ID`. Each key has one name.

> **Historical note**: the `ebx auth` CLI command group (`login`/`logout`/`status`/`switch`) was removed before the first stable release (`0.1.0`). Credentials are configured with the environment variables and `ebx config set sandbox_api_key` shown below; check the effective state with `ebx config list`.

---

## Authentication Overview

Easy Sandbox provides three authentication paths for different scenarios:

- **API Key mode**: The most common approach. Accesses the platform API via the `Authorization: Bearer {api_key}` header. Suitable for personal development, CI/CD, SDK calls, and most other scenarios.
- **AK/SK mode (Alibaba Cloud AccessKey) 🧪 Experimental**: Uses an Alibaba Cloud AccessKey pair to obtain a temporary API Key via token exchange. The framework is implemented but the token exchange endpoint is pending FC platform confirmation; the recommended approach is still API Key mode. Suitable for Alibaba Cloud ecosystem integration and enterprise environments using RAM role authorization.
- **envd internal authentication**: After sandbox creation, the SDK communicates with the in-sandbox envd service using `envdAccessToken` (obtained from the creation response). This is an internal mechanism managed automatically by the SDK — no manual handling required.

---

## API Key Authentication

API Key is the most common authentication method, sent to the platform API via the `Authorization: Bearer {api_key}` header.

### Configuration Methods

#### 1. Environment variable (wins over `~/.ebx`)

```bash
export EBX_SANDBOX_API_KEY="your-api-key"
```

Set `EBX_SANDBOX_API_KEY`. That is the only environment variable for the sandbox API key.

#### 2. Persisted file (`~/.ebx/.env`)

The SDK also reads `~/.ebx/.env`, which the `ebx` CLI writes (`ebx config set sandbox_api_key ...`, file mode 600; see the [CLI Authentication guide](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/authentication.md)). The key is stored as `EBX_SANDBOX_API_KEY`. Access keys are stored as `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.

#### 3. .env file

Create a `.env` file in the project root directory:

```dotenv
EBX_SANDBOX_API_KEY=your-api-key
```

The SDK reads both `.env` files as separate layers. `./.env` wins for a key it sets. A key it omits still comes from `~/.ebx/.env`.

1. `.env` in the current directory
2. `~/.ebx/.env`

#### 4. config.toml file

Prefer `~/.ebx/.env` (mode 600) for the sandbox API key. `ebx config set sandbox_api_key` writes `EBX_SANDBOX_API_KEY` there. Non-secret connection settings belong in `~/.ebx/config.toml`:

```toml
[transport]
sandbox_base_url = "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
sandbox_domain = "cn-hangzhou.e2b.fc.aliyuncs.com"
```

#### 5. Code parameter (wins over the environment and over `~/.ebx`)

```python
from easy_sandbox.api.sandbox import Sandbox

# Pass directly when creating
sandbox = await Sandbox.create(sandbox_api_key="your-api-key")

# Pass directly when connecting
sandbox = await Sandbox.connect("sbx-xxxx", sandbox_api_key="your-api-key")
```

---

## AK/SK Alibaba Cloud Extended Authentication 🧪

> **⚠️ Experimental Feature**: The AK/SK → API Key token exchange framework is implemented in the SDK (`transport/auth.py`), but the token exchange endpoint’s action name (`CreateApiKey`) and response field parsing **are still pending FC platform team confirmation**. TTL (3600s) and the 300s early refresh are placeholders until the platform confirms the endpoint. Use it for local debugging; **API Key authentication is still recommended for production**.

AK/SK mode uses an Alibaba Cloud AccessKey pair to obtain a temporary API Key via token exchange (designed TTL 3600 seconds, auto-refreshed 300 seconds before expiry).

### Configuration Methods

#### 1. Environment Variables

```bash
export ALICLOUD_ACCESS_KEY_ID="your-access-key-id"
export ALICLOUD_ACCESS_KEY_SECRET="your-access-key-secret"
```

These are the only environment variables for the AccessKey pair. The region is `ALIBABA_CLOUD_REGION_ID`.

#### 2. Persisted file (`~/.ebx/.env`)

Written by `ebx config set access_key_id ...` / `access_key_secret ...` (file mode 600; see the [CLI Authentication guide](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/authentication.md)) and stored as `ALICLOUD_ACCESS_KEY_ID=...` / `ALICLOUD_ACCESS_KEY_SECRET=...` in `~/.ebx/.env`, which the SDK reads.

#### 3. Code Parameters

```python
sandbox = await Sandbox.create(
    access_key_id="your-ak-id",
    access_key_secret="your-ak-secret",
)
```

### How AK/SK Works

1. The SDK uses the AK/SK to call the token exchange endpoint at `https://fcsandbox.{region}.aliyuncs.com` via Alibaba Cloud RPC (POP) V1 HMAC-SHA1 signing to obtain a temporary API Key
2. The temporary key is cached in memory (not persisted to disk)
3. Designed validity of 3600 seconds; the SDK auto-refreshes 300 seconds before expiry (actual parameters subject to FC platform final confirmation)
4. Subsequent requests use the temporary key as a Bearer Token

> **Note**: The above parameters (TTL, endpoint action name, etc.) are based on the ACR token exchange pattern and may be adjusted before production release.

---

## Configuration Priority Chain

Credentials are resolved in the following priority order (highest to lowest):

```mermaid
flowchart TD
    A["1. Code parameters (sandbox_api_key= / access_key_id= / llm_api_key=)"] --> B["2. Process environment"]
    B --> C["3. ./.env (per key; missing keys fall through)"]
    C --> D["4. ~/.ebx (.env, then config.toml)"]
    D --> E["5. Built-in default, or InvalidAPIKeyError E1001 when a sandbox key is required"]
```

LLM keys, the GitHub token, and the region use this same chain. A blank or whitespace-only value is skipped. Each key has one environment variable. The names and defaults are listed in [Credential resolution](../reference/configuration.md#credential-resolution).

### Credentials and providers

The generic sandbox key (`sandbox_api_key`, environment variable `EBX_SANDBOX_API_KEY`) and the Alibaba Cloud AK/SK belong to the built-in provider. If you switch to a [provider plugin](providers.md), the plugin does **not** receive them unless its manifest asks for them and you consented at install time. A plugin has its own scoped credential keys, for example `EBX_MY_CLOUD_API_KEY` for a provider `my-cloud`. This prevents a key for one cloud from being sent to another.

Within the same level, API Key takes precedence over AK/SK:
- If both `sandbox_api_key` and `access_key_id` are provided, API Key is used
- If both `EBX_SANDBOX_API_KEY` and `ALICLOUD_ACCESS_KEY_ID` are set, `EBX_SANDBOX_API_KEY` is used

---

## Secret Storage (File-Based)

Secrets are stored in `~/.ebx/secrets.json`, a plaintext JSON file protected by `chmod 600` file permissions. This is suitable for local development only.

> **⚠️ Warning**: `secrets.json` stores secrets in **plaintext**. It relies solely on POSIX file permissions (`chmod 600`) for access control. For production environments, use a dedicated secrets management service.

Manage secrets via environment variables or the `.env` files, or pass `envs={"MY_TOKEN": "..."}` to `Sandbox.create()` to inject secrets into one sandbox:

```bash
# Set API Key via environment variable (recommended)
export EBX_SANDBOX_API_KEY="your-api-key"
```

The CLI equivalents (`ebx config set`, `ebx create --env`) are in the [CLI Authentication guide](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/authentication.md).

> **Historical note**: macOS Keychain integration was removed in the overdesign cleanup (ADR 2026-09-23). The `ebx secret` CLI command group has also been removed. All secret management is now done through environment variables, `.env` files, or `ebx config set` (a CLI command).

---

## envd Authentication (In-Sandbox Communication)

After sandbox creation, communication with the in-sandbox envd service uses `envdAccessToken` (obtained from the creation response). This is an internal mechanism managed automatically by the SDK — no manual handling required.

envd authentication requires the following HTTP headers (set automatically by the SDK):

| Header | Value |
|--------|-------|
| `X-Access-Token` | envdAccessToken |
| `E2b-Sandbox-Id` | Sandbox ID |
| `E2b-Sandbox-Port` | `49983` |
| `Authorization` | `Basic dXNlcjo=` (base64 of "user:") |

---

## Common Issues

### InvalidAPIKeyError (E1001)

```text
[E1001] API key cannot be empty
  Suggestion: Check your EBX_SANDBOX_API_KEY environment variable or pass sandbox_api_key.
```

**Solution**: Ensure a valid API Key is configured via any of the methods above.

### InvalidCredentialsError (E1003)

```text
[E1003] AccessKey ID and Secret cannot be empty
  Suggestion: Check ALICLOUD_ACCESS_KEY_ID and ALICLOUD_ACCESS_KEY_SECRET environment variables.
```

**Solution**: Ensure both AK ID and AK Secret are set.

### TokenExpiredError (E1002)

```text
[E1002] The SDK should auto-refresh tokens. If this persists, check system clock synchronization.
```

**Solution**: Check that the system clock is accurate. The SDK auto-refreshes tokens; if this error persists, the clock skew may be too large.

---

## Related: the ebx CLI

Setting credentials from the command line (`ebx config set` / `list` / `get`, `ebx create --env`) is documented in the CLI repository: [CLI Authentication](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/authentication.md).
