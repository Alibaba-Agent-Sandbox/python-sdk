# Environment Variables in Sandboxes

This guide describes asynchronous `ProviderSandbox` provider extensions. Root `Sandbox` and `AsyncSandbox` follow the pinned standard migration contract; see [Migrate from E2B](migrate-from-e2b.md).

For current SDK installation, use the [installation guide](install-python.md).

> **Note:** The `abx` commands shown on this page are provided by the CLI in the `agent-sandbox` repository ([CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

This guide distinguishes creation-time environment input, per-process overrides and the environment of an already running application. The examples use the asynchronous `ProviderSandbox`; snippets after the first example assume a live `sandbox` inside an async function.

## Where Values Apply

| Input | Applies to |
|-------|------------|
| `ProviderSandbox.create(envs=...)` | Creation input interpreted by the selected provider and runtime. Ordinary variables can reach subsequent processes, but the runtime may retain the platform `PATH`. |
| `sandbox.commands.run(..., env=...)` | That process and its children. It does not update other running processes. |
| Application `POST /env` | The running application's `os.environ` and subsequently created children. It does not update its parent or sibling processes. |

An application can be a child process started through envd. Each process has its own environment; later changes do not rewrite existing parent or sibling processes. There is no global `sandbox.set_env()` API. For a required process `PATH`, pass an explicit per-call `env` rather than assuming creation-time replacement.

---

## Creation and Per-Process Environment

### At Creation Time

Use creation-time `envs` for ordinary application variables.

**SDK:**

```python
import asyncio
from agent_sandbox import ProviderSandbox

async def main():
    sandbox = await ProviderSandbox.create(
        template="base", envs={"APP_ENV": "staging"}, timeout=300,
    )
    try:
        result = await sandbox.commands.run("printenv APP_ENV")
        print(result.stdout.strip())
    finally:
        await sandbox.kill()  # This function owns the instance.

asyncio.run(main())
```

On the default Express CLI path, `abx create base --env KEY=value` sets the new interactive terminal's environment; it is not a sandbox-lifetime creation-env API and has no terminal to configure with `--detach`. Use `ProviderSandbox.create(envs=...)` for the creation input above. For template applications, declare runtime defaults in the template and configure required values before `abx template launch`. See the [CLI guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md).

When attaching to an instance you do not own, release the local connection with `await sandbox.close()` instead of deleting the instance.

**`@sandbox` decorator:**

```python
from agent_sandbox import sandbox as sandboxed

@sandboxed(template="base", envs={"APP_ENV": "staging"})
def my_task():
    import os
    return os.environ["APP_ENV"]
```

### Per-Execution Override

Each execution call can pass additional env vars that apply **only to that invocation**:

```python
# commands.run — use `env=` (singular, dict)
result = await sandbox.commands.run(
    "printenv MY_VAR",
    env={"MY_VAR": "hello"},
)

# run_code — use `envs=` (plural, dict)
result = await sandbox.run_code(
    "import os; print(os.environ['MY_VAR'])",
    envs={"MY_VAR": "hello"},
)
```

`run_code()` is a real interpreter API and requires the selected provider to declare `code.execute` for this mode; an ordinary Express `base` instance does not establish that support. Interpreter environment behavior belongs to that provider, rather than universally to envd.

> **Note the parameter naming difference:** `commands.run()` uses `env=` (singular); `run_code()` uses `envs=` (plural). This follows the E2B naming convention.

---

## Direct-Exec Semantics

Commands sent through envd are executed via **direct `exec`** by default. However, `commands.run()`, `commands.stream()`, and `commands.start()` **automatically detect unquoted shell operators** (`|`, `;`, `&&`, `||`, `>`, `<`, `(...)`, `$(...)`) and transparently wrap the command in `sh -c`.

### Automatic Shell-Operator Wrapping

Pipes, redirects, semicolons, and logical operators now work **without** manual `sh -c`:

```python
# ✅ Works — pipe is auto-detected and wrapped
result = await sandbox.commands.run("ls /tmp | grep log")

# ✅ Works — redirect is auto-detected and wrapped
result = await sandbox.commands.run("echo hello > /tmp/hello.txt")

# ✅ Works — && is auto-detected and wrapped
result = await sandbox.commands.run("cd /app && python main.py")

# ✅ Works — semicolon is auto-detected and wrapped
result = await sandbox.commands.run("mkdir -p /tmp/out; cp file.txt /tmp/out/")
```

### Variable Expansion Still Requires Manual Wrapping

Shell variable expansion (`$VAR`, `${VAR}`) is **not** auto-detected because `$` is not a shell operator character. Use explicit `sh -c`:

```python
# ❌ WRONG — $HOME is passed as a literal string (no auto-wrap triggered)
result = await sandbox.commands.run("echo $HOME")
# stdout: "$HOME" (literal)

# ✅ CORRECT — use sh -c for variable expansion
result = await sandbox.commands.run("sh -c 'echo $HOME'")
# stdout: the selected process user's home directory

# ✅ CORRECT — use printenv to read a single variable
result = await sandbox.commands.run("printenv HOME")
# stdout: the selected process user's home directory
```

### Glob Expansion Still Requires Manual Wrapping

```python
# ❌ WRONG — * is passed literally (no auto-wrap triggered)
result = await sandbox.commands.run("ls *.py")

# ✅ CORRECT
result = await sandbox.commands.run("sh -c 'ls *.py'")
```

### Rule of Thumb

**Automatically wrapped** (no manual `sh -c` needed):
- Pipes (`|`)
- Redirects (`>`, `>>`, `<`)
- Logical operators (`&&`, `||`)
- Command separators (`;`)
- Subshells (`(...)`)
- Command substitution (`$(...)`)

**Still require explicit `sh -c '...'`**:
- Variable expansion (`$VAR`, `${VAR}`)
- Backtick substitution (`` `cmd` ``)
- Glob patterns (`*`, `?`, `[...]`)

If you only need to **read** a single environment variable's value, prefer `printenv VAR` — it is simpler and avoids shell quoting issues.

---

## Server Scope — `GET/POST /env`

When a `SandboxServer` is running inside the sandbox (typically on port 9000), the `/env` endpoints manage the **Server process's** `os.environ`:

### Read and Set Variables

The application must enable and authorize the environment endpoints in its policy. Bind the application with its explicit token; provider gateway access and the application token are distinct credentials.

```python
import os

async with await sandbox.application_client(
    9000, token=os.environ["ABX_SERVER_TOKEN"]
) as application:
    print(await application.system.env(["APP_ENV"]))
    print(await application.system.set_env({"FEATURE_FLAG_X": "enabled"}))
    print(await application.system.env(["FEATURE_FLAG_X"]))
```

These existing typed methods call `GET /env` and `POST /env`, preserving provider URL prefixes, signed query parameters and authentication. Direct HTTP callers can use `application.auth_headers()`; `network.get_url()` and `get_access_headers()` are real provider APIs, but gateway headers alone do not supply an application token. See the [application binding guide](template-workflows.md).

The changes affect the application process and future children; they do not modify envd or sibling processes. Settings already read and cached at startup, including model configuration, are not automatically reinitialized by `POST /env`.

### Protected Variables

The Server rejects attempts to overwrite:

- System variables: `PATH`, `HOME`, `USER`, `SHELL`
- SDK internals: any variable starting with `ABX_` (including `ABX_SERVER_TOKEN`)

---

## Recommended Patterns

### Pattern 1: Inject at Creation (Most Common)

Best for variables that should be available throughout the sandbox's lifetime:

```python
async with await ProviderSandbox.create(
    template="base",
    envs={"DATABASE_URL": db_url, "APP_ENV": "production"},
) as sandbox:
    result = await sandbox.commands.run("printenv APP_ENV")
```

### Pattern 2: Per-Call env Dict (Scoped Overrides)

Best for variables that vary between invocations:

```python
env = {"BATCH_ID": "batch-001", "DRY_RUN": "true"}

result = await sandbox.commands.run("sh -c 'python process.py'", env=env)
```

### Pattern 3: Reuse an env Dict Object

Keep a shared dict and pass it to each call:

```python
shared_env = {"DATABASE_URL": db_url, "LOG_LEVEL": "DEBUG"}

await sandbox.commands.run("sh -c 'python migrate.py'", env=shared_env)
await sandbox.commands.run("sh -c 'python seed.py'", env=shared_env)
await sandbox.run_code("import os; print(os.environ['LOG_LEVEL'])", envs=shared_env)
```

### Pattern 4: Application-Scoped Configuration

Use the authenticated application binding above for values read by a running application. Set startup-only values before launching that application.

---

## Client Configuration Variables Are Not Sandbox Variables

The variables that configure the SDK and CLI on **your** machine (`ABX_SANDBOX_API_KEY`, `ABX_PROVIDER`, `ALIBABA_CLOUD_REGION_ID`, ...) are read by the client and are not automatically copied into a sandbox. To make a value visible inside a sandbox, pass it explicitly through the applicable creation or per-process API. Each client setting has one variable. Names and precedence are in the [Configuration Reference](../reference/configuration.md#environment-variables).

Two consequences:

- Inside the Server, every name starting with `ABX_` is protected (see above). Do not use `ABX_*` for your own sandbox variables.
- An [`exec` provider plugin](providers.md) starts with an allowlisted environment plus any explicitly declared `env_passthrough` names. Its resolved configuration is sent through the existing `initialize` request. A `node` provider uses the CLI local engine; the SDK sends resolved options with its requests.

---

## Security Considerations

1. **Secrets in envs**: Environment variables passed via `envs=` at creation time are transmitted to the platform API. Ensure your transport uses HTTPS (the default). Avoid logging env dicts that contain secrets.

2. **`GET /env` redaction**: The Server's `GET /env` endpoint automatically redacts variables whose names contain `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, or `CREDENTIAL`.

3. **Protected Server variables**: `POST /env` blocks writes to `PATH`, `HOME`, `USER`, `SHELL`, and all `ABX_*` variables to prevent accidental breakage.

4. **Process inheritance**: `POST /env` does not rewrite parent or sibling environments. Do not treat this ordinary process boundary as a security-isolation guarantee.

5. **Prefer `printenv`** over `echo $VAR`: Since envd uses direct exec, `echo $VAR` prints the literal string `$VAR`. Use `printenv VAR` or `sh -c 'echo $VAR'` instead.

---

## Quick Reference

| Method | Parameter | Scope | Lifetime |
|--------|-----------|-------|----------|
| `ProviderSandbox.create(envs=)` | `envs` | Instance creation input | Sandbox lifetime |
| `commands.run(env=)` | `env` | envd | Single command |
| `run_code(envs=)` | `envs` | Provider interpreter, when supported | Single execution |
| `@sandbox(envs=)` | `envs` | Provider creation input | Decorator-owned sandbox |
| `POST /env` | `vars` | Server | Server process lifetime |

---

## See Also

- [SDK Usage Guide](sdk-usage.md) — `commands.run()` and `run_code()` usage
- [Declarative Usage](declarative-usage.md) — `@sandbox(envs=)` decorator
- [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md) — CLI terminal environment
- [Configuration Reference](../reference/configuration.md) — SDK/CLI environment variables (one name per key)
- [Providers](providers.md) — selecting and installing sandbox providers
