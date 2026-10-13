# Migrating from E2B

Agent Sandbox uses E2B-style method names so that most E2B call sites port with an import change. It is not a drop-in replacement: the wire protocol, credentials and several behaviours differ. This page lists what to change.

---

## API Mapping Table

| E2B SDK | Agent Sandbox | Notes |
|---------|-------------|-------|
| `from e2b import Sandbox` | `from agent_sandbox.api.sandbox import Sandbox` | Main class import |
| `Sandbox.create()` | `Sandbox.create()` | ✅ Same call shape |
| `Sandbox.connect(id)` | `Sandbox.connect(id)` | ✅ Same call shape |
| `Sandbox.list()` | `Sandbox.list()` | ✅ Same call shape |
| `sandbox.kill()` | `sandbox.kill()` | ✅ Same call shape |
| `Sandbox.kill(id)` | `Sandbox.kill_by_id(id)` | ⚠️ Different method name |
| `sandbox.is_running()` | `sandbox.is_running()` | ✅ Same call shape |
| `sandbox.pause()` | `sandbox.pause()` | ✅ Same call shape |
| `sandbox.set_timeout(t)` | `sandbox.set_timeout(t)` | ✅ Same call shape |
| `sandbox.commands.run(cmd)` | `sandbox.commands.run(cmd)` | ✅ Same call shape |
| `sandbox.files.read(path)` | `sandbox.files.read(path)` | ✅ Same call shape |
| `sandbox.files.write(path, d)` | `sandbox.files.write(path, d)` | ✅ Same call shape |
| `sandbox.run_code(code)` | `sandbox.run_code(code)` | ✅ Same call shape |
| `sandbox.get_host(port)` | `sandbox.network.get_host(port)` | ⚠️ Requires the network submodule |
| `sandbox.get_upload_url(path)` | `sandbox.get_upload_url(path)` | The call fails. This data plane requires `X-Access-Token` and does not accept a signature-only URL |
| `sandbox.get_download_url(path)` | `sandbox.get_download_url(path)` | Same as upload |

---

## Import Path Replacement

### Change the Import

```python
# E2B
from e2b import Sandbox

# Agent Sandbox (recommended)
from agent_sandbox.api.sandbox import Sandbox
```

### Using the Compatibility Layer

```python
# Compatibility layer import (minimal changes)
from agent_sandbox.compat import Sandbox
```

The compatibility layer `agent_sandbox.compat` re-exports the `Sandbox` class (method names follow the E2B SDK; behaviour differences are listed below).

---

## Compatibility Layer Details

The compatibility module `agent_sandbox.compat.sandbox` provides:

```python
from agent_sandbox.compat import Sandbox
from agent_sandbox.compat import E2BSandbox  # Alias
```

Both are the same `Sandbox` class, only differing in name.

---

## Environment Variables

Agent Sandbox uses one environment variable per setting. Set these when you move a project off E2B:

| Setting | Environment variable |
|---|---|
| Sandbox API key | `ABX_SANDBOX_API_KEY` |
| Platform API URL | `ABX_SANDBOX_BASE_URL` |
| Data-plane domain | `ABX_SANDBOX_DOMAIN` |

---

## Incompatibilities and Solutions

### 1. `Sandbox.kill(id)` → `Sandbox.kill_by_id(id)`

In E2B, the class method `Sandbox.kill(id)` destroys a sandbox by ID. In Agent Sandbox, this is provided by `Sandbox.kill_by_id(id)`; `sandbox.kill()` is an instance method.

```python
# E2B
await Sandbox.kill("sbx-xxxx")

# Agent Sandbox
await Sandbox.kill_by_id("sbx-xxxx")
```

### 2. `get_host(port)` requires the network submodule

```python
# E2B
host = sandbox.get_host(8080)

# Agent Sandbox
host = sandbox.network.get_host(8080)
url = sandbox.network.get_url(8080)
```

> **Note**: `network.get_host()` and `network.get_url()` are local URL-computation helpers. They are logically associated with the `ports` capability but **do not** perform a runtime capability check — calls succeed regardless of the template's capability declaration.

### 3. `get_upload_url()` / `get_download_url()`

E2B's methods return a signed URL a browser can open. The current Express envd does not accept that request: without `X-Access-Token` it returns 403 `X-Access-Token header is required`. Agent Sandbox's methods of the same name raise `FileOperationError` instead of returning a URL that cannot be used.

Move files with `files.write()`, `files.read()`, `files.upload()`, and `files.download()`. The SDK sends the access token on those calls.

### 4. Capability model

Agent Sandbox introduces a capability model. Templates declare capabilities in `template.yaml`. Only the `code` capability is **runtime-enforced (fail-closed)** — `CodeContextModule` methods raise `CapabilityNotSupportedError` (E3004) when the `code` capability is missing. Other modules forward requests without a runtime gate:

- `run_code()` / `code.*` → Requires the `code` capability — **runtime-enforced (E3004)**
- `commands.run()` → Logically associated with `shell` (no runtime gate)
- `files.*` → Logically associated with `files` (no runtime gate)
- `network.*` → Logically associated with `ports` (no runtime gate)
- `get_terminal()` → Logically associated with `terminal` (no runtime gate)

The default capability set `{shell, files, code}` covers most common operations.

### 5. Alibaba Cloud extensions

Agent Sandbox adds Alibaba Cloud AK/SK authentication, which does not exist in E2B:

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
`ABX_HTTP_TIMEOUT` applies.

```python
sandbox = await Sandbox.create(
    template="python-hello",
    timeout=300,            # sandbox lifetime (TTL)
    request_timeout=120,    # HTTP wait for this create call only
)
```

---

## Migration Steps

1. **Replace dependency**: `pip install agent-sandbox` (uninstall `e2b`)
2. **Replace imports**:
   - Minimal changes: `from e2b import Sandbox` → `from agent_sandbox.compat import Sandbox`
   - Recommended: `from agent_sandbox.api.sandbox import Sandbox`
3. **Replace `Sandbox.kill(id)`**: Change to `Sandbox.kill_by_id(id)`
4. **Replace `get_host()`**: Change to `sandbox.network.get_host()`
5. **`get_upload_url` / `get_download_url`**: Use `files.write()` / `files.read()`. This data plane does not accept a signature-only URL
6. **Set environment variables**: `ABX_SANDBOX_API_KEY` for the sandbox API key. Each setting has one variable; see [Configuration](../reference/configuration.md).

---

## Next Steps

- [Authentication](authentication.md) — Learn about all authentication methods
- [SDK Usage Guide](sdk-usage.md) — Complete SDK usage
- [E2B Compatibility Explained](../explanation/e2b-compatibility.md) — Design background and rationale
