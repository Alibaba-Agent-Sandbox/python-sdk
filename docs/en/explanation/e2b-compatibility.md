# E2B Compatibility

This document explains Easy Sandbox's compatibility strategy with the E2B Python SDK — what is compatible, what is not, and the design rationale behind the decisions.

---

## Design Goals

Easy Sandbox's E2B compatibility strategy is:

> **Allow users of the E2B SDK to migrate to Easy Sandbox with minimal changes, without being constrained by E2B's historical design decisions.**

Specifically:
- Core API signatures remain consistent
- Environment variable names are compatible
- A `compat` module is provided to simplify migration
- New capabilities do not break compatibility

---

## What Is Compatible

### API Signatures

The following APIs are fully compatible with the E2B Python SDK:

| API | Status |
|-----|--------|
| `Sandbox.create(template, timeout, metadata, envs)` | ✅ Compatible |
| `Sandbox.connect(sandbox_id)` | ✅ Compatible |
| `Sandbox.list()` | ✅ Compatible |
| `sandbox.kill()` | ✅ Compatible |
| `sandbox.is_running()` | ✅ Compatible |
| `sandbox.pause()` | ✅ Compatible |
| `sandbox.set_timeout(seconds)` | ✅ Compatible |
| `sandbox.run_code(code, language, timeout)` | ✅ Compatible |
| `sandbox.commands.run(cmd, timeout, env, cwd)` | ✅ Compatible |
| `sandbox.files.read(path)` | ✅ Compatible |
| `sandbox.files.write(path, content)` | ✅ Compatible |
| `sandbox.files.list(path)` | ✅ Compatible |
| `sandbox.files.remove(path)` | ✅ Compatible |
| `async with await Sandbox.create() as sb:` | ✅ Compatible |

### Environment Variables

Each setting has one environment variable. Set these instead of the E2B variable names:

| Setting | Environment variable |
|----------|--------|
| Sandbox API key | `EBX_SANDBOX_API_KEY` |
| Platform API URL | `EBX_SANDBOX_BASE_URL` |
| Data-plane domain | `EBX_SANDBOX_DOMAIN` |

### Compatibility Layer

```python
from easy_sandbox.compat import Sandbox
```

The `compat` module re-exports the `Sandbox` class with no additional wrapping.

---

## What Is Not Compatible

### 1. `Sandbox.kill(id)` Class Method

**E2B**: `Sandbox.kill(id)` is a class method that destroys a sandbox by ID.

**Easy Sandbox**: The class method is renamed to `Sandbox.kill_by_id(id)`, while `kill()` is reserved as an instance method.

**Rationale**: In Python, having both a class method and an instance method with the same name creates ambiguity. Explicitly naming the class method `kill_by_id` is clearer and avoids confusion between `Sandbox.kill("sbx-xxxx")` and `sandbox.kill()`.

### 2. `sandbox.get_host(port)` Direct Method

**E2B**: `sandbox.get_host(port)` is a direct method on the Sandbox instance.

**Easy Sandbox**: Moved to `sandbox.network.get_host(port)` submodule.

**Rationale**: Network-related functionality is consolidated under the `network` submodule, maintaining a consistent organizational structure with `commands`, `files`, and other submodules. Additionally, `network` methods require `ports` capability gating.

### 3. `get_upload_url()` / `get_download_url()`

**E2B**: Returns a signed URL so a browser can upload or download one file.

**Easy Sandbox**: The methods of the same name raise `FileOperationError`. A request to a live Express sandbox showed that envd ignores a query signature and requires `X-Access-Token`. The SDK does not return a URL that would get 403.

### 4. Capability Gating

**E2B**: No capability checking mechanism; all features are always available.

**Easy Sandbox**: Introduces a capability model that checks whether a template declares the required capabilities before an API call.

**Rationale**:
- **Security**: Restricts sandbox functionality scope, following the principle of least privilege
- **Clarity**: Fails immediately at call time (E3004) rather than returning obscure backend errors
- **Extensibility**: Lays the groundwork for future fine-grained permission control

### 5. Certain RPC Paths

Some APIs (`run_code`, `get_terminal`, etc.) have RPC paths reverse-engineered from the E2B SDK. These paths are not publicly documented by Alibaba Cloud and may differ.

---

## Extensions (Non-E2B Features)

Easy Sandbox adds the following features on top of E2B compatibility:

| Feature | Description |
|---------|-------------|
| AK/SK Authentication | Alibaba Cloud AccessKey pair authentication |
| Capability Model | Template-level capability declarations and runtime gating |
| Custom Commands | Parameterized shell commands defined in template.yaml |
| @sandbox Decorator | Declarative remote function execution |
| Image Chaining API | Modal-style image building |
| MCP Server | AI IDE integration (Cursor/Claude/VS Code) |
| Session Management | Named session persistence |
| NL Deployment | Natural language-driven project deployment |
| Secret Management | Environment variables and `.env` file secure storage |

---

## Next Steps

- [Migrate from E2B](../guide/migrate-from-e2b.md) — Step-by-step migration guide
- [Architecture Overview](architecture-overview.md) — System architecture
- [SDK Usage Guide](../guide/sdk-usage.md) — Complete SDK usage
