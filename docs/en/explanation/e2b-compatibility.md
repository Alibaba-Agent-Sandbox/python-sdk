# E2B Compatibility

This document explains how Agent Sandbox relates to the E2B Python SDK: which method shapes are shared, what differs, and why. Agent Sandbox is **not** a drop-in replacement for E2B. It is a different service with E2B-shaped method names so that migration needs few edits.

---

## Design Goals

The migration strategy is:

> **Allow users of the E2B SDK to migrate to Agent Sandbox with minimal changes, without being constrained by E2B's historical design decisions.**

Specifically:
- Core method signatures stay close to E2B
- Environment variables are different (`ABX_*`); E2B's `E2B_*` variables are not read
- A small `compat` module re-exports `Sandbox` to simplify migration
- Coverage is partial: two methods raise (see below) and some behaviours differ

---

## What Is Shared

### API Signatures

These methods have the same name and call shape as the E2B Python SDK:

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
| Sandbox API key | `ABX_SANDBOX_API_KEY` |
| Platform API URL | `ABX_SANDBOX_BASE_URL` |
| Data-plane domain | `ABX_SANDBOX_DOMAIN` |

### Compatibility Layer

```python
from agent_sandbox.compat import Sandbox
```

The `compat` module is a migration helper. It re-exports the `Sandbox` class with no additional wrapping (plus the alias `E2BSandbox`). It does not make E2B code run unchanged.

---

## What Differs

### 1. `Sandbox.kill(id)` Class Method

**E2B**: `Sandbox.kill(id)` is a class method that destroys a sandbox by ID.

**Agent Sandbox**: The class method is renamed to `Sandbox.kill_by_id(id)`, while `kill()` is reserved as an instance method.

**Rationale**: In Python, having both a class method and an instance method with the same name creates ambiguity. Explicitly naming the class method `kill_by_id` is clearer and avoids confusion between `Sandbox.kill("sbx-xxxx")` and `sandbox.kill()`.

### 2. `sandbox.get_host(port)` Direct Method

**E2B**: `sandbox.get_host(port)` is a direct method on the Sandbox instance.

**Agent Sandbox**: Moved to `sandbox.network.get_host(port)` submodule.

**Rationale**: Network-related functionality is consolidated under the `network` submodule, maintaining a consistent organizational structure with `commands`, `files`, and other submodules. Additionally, `network` methods require `ports` capability gating.

### 3. `upload_url()` / `download_url()`

**E2B**: `sandbox.upload_url(path)` / `sandbox.download_url(path)` (JavaScript: `uploadUrl` / `downloadUrl`) return a URL with a `signature`. A browser can upload or download one file with that URL alone, without `X-Access-Token`.

**Agent Sandbox**: The methods of the same name raise `FileOperationError`. This data plane does not honor that signature. A `/files` request without `X-Access-Token` is 403 `access denied: X-Access-Token header is required`, and the file is not written. The header is what authorizes the call; the `signature` query parameter does not. `get_upload_url()` / `get_download_url()` are aliases. The URL from `files.upload_url()` still requires the header.

### 4. Capability Gating

**E2B**: No capability checking mechanism; all features are always available.

**Agent Sandbox**: Introduces a capability model that checks whether a template declares the required capabilities before an API call.

**Rationale**:
- **Security**: Restricts sandbox functionality scope, following the principle of least privilege
- **Clarity**: Fails immediately at call time (E3004) rather than returning obscure backend errors
- **Extensibility**: Lays the groundwork for future fine-grained permission control

### 5. Certain RPC Paths

Some APIs (`run_code`, `get_terminal`, etc.) have RPC paths reverse-engineered from the E2B SDK. These paths are not publicly documented by Alibaba Cloud and may differ.

---

## Extensions (Non-E2B Features)

Agent Sandbox adds the following features that E2B does not have:

| Feature | Description |
|---------|-------------|
| AK/SK Authentication | Alibaba Cloud AccessKey pair authentication |
| Capability Model | Template-level capability declarations and runtime gating |
| Registered commands | Functions registered in the sandbox server (`@sandbox.register`) and called with `sandbox.run(name, **kwargs)` |
| @sandbox Decorator | Declarative remote function execution |
| MCP Server | AI IDE integration (Cursor/Claude/VS Code) |
| Session Management | Named session persistence |
| Secret Management | Environment variables and `.env` file secure storage |

---

## Next Steps

- [Migrate from E2B](../guide/migrate-from-e2b.md) — Step-by-step migration guide
- [Architecture Overview](architecture-overview.md) — System architecture
- [SDK Usage Guide](../guide/sdk-usage.md) — Complete SDK usage
