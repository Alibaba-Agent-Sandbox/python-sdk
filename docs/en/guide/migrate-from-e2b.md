# Migrating from E2B

Easy Sandbox is designed to maintain a high degree of API compatibility with the E2B Python SDK. This document provides a migration guide.

---

## API Mapping Table

| E2B SDK | Easy Sandbox | Notes |
|---------|-------------|-------|
| `from e2b import Sandbox` | `from easy_sandbox.api.sandbox import Sandbox` | Main class import |
| `Sandbox.create()` | `Sandbox.create()` | ✅ Fully compatible |
| `Sandbox.connect(id)` | `Sandbox.connect(id)` | ✅ Fully compatible |
| `Sandbox.list()` | `Sandbox.list()` | ✅ Fully compatible |
| `sandbox.kill()` | `sandbox.kill()` | ✅ Fully compatible |
| `Sandbox.kill(id)` | `Sandbox.kill_by_id(id)` | ⚠️ Different method name |
| `sandbox.is_running()` | `sandbox.is_running()` | ✅ Fully compatible |
| `sandbox.pause()` | `sandbox.pause()` | ✅ Fully compatible |
| `sandbox.set_timeout(t)` | `sandbox.set_timeout(t)` | ✅ Fully compatible |
| `sandbox.commands.run(cmd)` | `sandbox.commands.run(cmd)` | ✅ Fully compatible |
| `sandbox.files.read(path)` | `sandbox.files.read(path)` | ✅ Fully compatible |
| `sandbox.files.write(path, d)` | `sandbox.files.write(path, d)` | ✅ Fully compatible |
| `sandbox.run_code(code)` | `sandbox.run_code(code)` | ✅ Fully compatible |
| `sandbox.get_host(port)` | `sandbox.network.get_host(port)` | ⚠️ Requires the network submodule |
| `sandbox.get_upload_url(path)` | `sandbox.get_upload_url(path)` | ✅ Returns a signed upload URL |
| `sandbox.get_download_url(path)` | `sandbox.get_download_url(path)` | ✅ Returns a signed download URL |

---

## Import Path Replacement

### Direct Replacement

```python
# E2B
from e2b import Sandbox

# Easy Sandbox (recommended)
from easy_sandbox.api.sandbox import Sandbox
```

### Using the Compatibility Layer

```python
# Compatibility layer import (minimal changes)
from easy_sandbox.compat import Sandbox
```

The compatibility layer `easy_sandbox.compat` re-exports the `Sandbox` class with an API signature consistent with the E2B SDK.

---

## Compatibility Layer Details

The compatibility module `easy_sandbox.compat.sandbox` provides:

```python
from easy_sandbox.compat import Sandbox
from easy_sandbox.compat import E2BSandbox  # Alias
```

Both are the same `Sandbox` class, only differing in name.

---

## Environment Variables

Easy Sandbox uses one environment variable per setting. Set these when you move a project off E2B:

| Setting | Environment variable |
|---|---|
| Sandbox API key | `EBX_SANDBOX_API_KEY` |
| Platform API URL | `EBX_SANDBOX_BASE_URL` |
| Data-plane domain | `EBX_SANDBOX_DOMAIN` |

---

## Incompatibilities and Solutions

### 1. `Sandbox.kill(id)` → `Sandbox.kill_by_id(id)`

In E2B, the class method `Sandbox.kill(id)` destroys a sandbox by ID. In Easy Sandbox, this is provided by `Sandbox.kill_by_id(id)`; `sandbox.kill()` is an instance method.

```python
# E2B
await Sandbox.kill("sbx-xxxx")

# Easy Sandbox
await Sandbox.kill_by_id("sbx-xxxx")
```

### 2. `get_host(port)` requires the network submodule

```python
# E2B
host = sandbox.get_host(8080)

# Easy Sandbox
host = sandbox.network.get_host(8080)
url = sandbox.network.get_url(8080)
```

> **Note**: `network.get_host()` and `network.get_url()` are local URL-computation helpers. They are logically associated with the `ports` capability but **do not** perform a runtime capability check — calls succeed regardless of the template's capability declaration.

### 3. `get_upload_url()` / `get_download_url()`

These methods return a signed envd file URL. Upload with `POST` and a `multipart/form-data` field named `file`. Download with `GET`. The caller does not send `X-Access-Token`. `use_signature_expiration` is how many seconds the signature stays valid; omit it for a signature that does not expire.

The SDK still moves its own files with `files.write()`, `files.read()`, `files.upload()`, and `files.download()`. The signed URL is for a browser or another client that does not hold the sandbox token.

### 4. Capability model

Easy Sandbox introduces a capability model. Templates declare capabilities in `template.yaml`. Only the `code` capability is **runtime-enforced (fail-closed)** — `CodeContextModule` methods raise `CapabilityNotSupportedError` (E3004) when the `code` capability is missing. Other modules forward requests without a runtime gate:

- `run_code()` / `code.*` → Requires the `code` capability — **runtime-enforced (E3004)**
- `commands.run()` → Logically associated with `shell` (no runtime gate)
- `files.*` → Logically associated with `files` (no runtime gate)
- `network.*` → Logically associated with `ports` (no runtime gate)
- `get_terminal()` → Logically associated with `terminal` (no runtime gate)

The default capability set `{shell, files, code}` covers most common operations.

### 5. Alibaba Cloud extensions

Easy Sandbox adds Alibaba Cloud AK/SK authentication, which does not exist in E2B:

```python
sandbox = await Sandbox.create(
    access_key_id="your-ak",
    access_key_secret="your-sk",
)
```

### 6. Per-request timeout

`Sandbox.create(request_timeout=...)` mirrors E2B's `request_timeout`: it bounds
how long the client waits for the create HTTP response and is independent of
`timeout` (the sandbox TTL). When omitted, the global `http_timeout` /
`EBX_HTTP_TIMEOUT` applies.

```python
sandbox = await Sandbox.create(
    template="python-hello",
    timeout=300,            # sandbox lifetime (TTL)
    request_timeout=120,    # HTTP wait for this create call only
)
```

---

## Migration Steps

1. **Replace dependency**: `pip install easy-sandbox` (uninstall `e2b`)
2. **Replace imports**:
   - Minimal changes: `from e2b import Sandbox` → `from easy_sandbox.compat import Sandbox`
   - Recommended: `from easy_sandbox.api.sandbox import Sandbox`
3. **Replace `Sandbox.kill(id)`**: Change to `Sandbox.kill_by_id(id)`
4. **Replace `get_host()`**: Change to `sandbox.network.get_host()`
5. **`get_upload_url` / `get_download_url`**: The method names match. Optional `use_signature_expiration` is the signature lifetime in seconds
6. **Set environment variables**: `EBX_SANDBOX_API_KEY` for the sandbox API key. Each setting has one variable; see [Configuration](../reference/configuration.md).

---

## Next Steps

- [Authentication](authentication.md) — Learn about all authentication methods
- [SDK Usage Guide](sdk-usage.md) — Complete SDK usage
- [E2B Compatibility Explained](../explanation/e2b-compatibility.md) — Design background and rationale
