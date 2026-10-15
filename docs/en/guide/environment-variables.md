# Environment Variables in Sandboxes

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @agent-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

This guide explains how environment variables work inside Agent Sandbox, covering the two distinct process scopes, injection methods, the direct-exec execution model, and recommended patterns.

> **Design decision:** There is no `sandbox.set_env()` API. The envd process tree and the SandboxServer `os.environ` are two separate, non-unifiable scopes. Attempting to provide a single "set env" abstraction would be misleading. Use the scope-specific injection methods described below instead.

---

## Two Process Scopes

Inside every sandbox there are **two independent process trees**, each with its own environment:

```text
┌─────────────────────────────────────────────────────┐
│                   Sandbox Container                  │
│                                                      │
│  ┌────────────────────┐   ┌───────────────────────┐  │
│  │  envd (PID 1)      │   │  SandboxServer        │  │
│  │  ├─ commands.run()  │   │  (optional, port 9000)│  │
│  │  ├─ run_code()      │   │  ├─ GET/POST /env     │  │
│  │  └─ terminal PTY    │   │  ├─ POST /commands/*  │  │
│  │                     │   │  └─ child processes    │  │
│  └────────────────────┘   └───────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

| Scope | Process owner | How env vars propagate |
|-------|--------------|----------------------|
| **envd scope** | The `envd` daemon (PID 1) | Variables are set at sandbox creation or passed per-call; every process started via `commands.run()`, `run_code()`, or a PTY terminal inherits from envd. |
| **Server scope** | The `SandboxServer` Python process | `POST /env` modifies `os.environ` of the Server process; only child processes spawned by the Server (e.g. `POST /commands/{name}` handlers) inherit those changes. |

**Key boundary:** `POST /env` on the SandboxServer **does not** affect processes started through the SDK's `commands.run()` or `run_code()` — those go through envd, which has its own environment. The two scopes are completely independent.

---

## envd Scope — SDK & CLI Injection

### At Creation Time

Variables passed at creation are injected into the envd root process and inherited by **all** subsequent commands:

**SDK:**

```python
sandbox = await Sandbox.create(
    template="base",
    envs={"DATABASE_URL": "postgres://...", "APP_ENV": "staging"},
)
```

**CLI:**

```bash
abx create --template base --env DATABASE_URL=postgres://... --env APP_ENV=staging
```

**`@sandbox` decorator:**

```python
@sandbox(template="base", envs={"DATABASE_URL": "postgres://..."})
def my_task():
    import os
    return os.environ["DATABASE_URL"]
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
# stdout: "/root"

# ✅ CORRECT — use printenv to read a single variable
result = await sandbox.commands.run("printenv HOME")
# stdout: "/root"
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

### Read Variables

```python
import httpx

url = sandbox.network.get_url(9000)
headers = sandbox.network.get_access_headers()

resp = httpx.get(f"{url}/env", headers=headers)
print(resp.json()["variables"])
# Only non-sensitive variables are returned (names containing
# TOKEN, SECRET, KEY, PASSWORD, CREDENTIAL are redacted)
```

### Set Variables

```python
resp = httpx.post(
    f"{url}/env",
    headers={**headers, "Content-Type": "application/json"},
    json={"vars": {"MY_CONFIG": "new_value"}},
)
print(resp.json()["updated"])  # ["MY_CONFIG"]
```

### Server Scope Boundaries

- `POST /env` modifies **only** `os.environ` of the SandboxServer process.
- Child processes spawned by the Server (e.g. custom command handlers via `POST /commands/{name}`) inherit these changes.
- Processes started via `commands.run()`, `run_code()`, or PTY terminals are **not affected** — they run under envd, which has a separate environment.

### Protected Variables

The Server rejects attempts to overwrite:

- System variables: `PATH`, `HOME`, `USER`, `SHELL`
- SDK internals: any variable starting with `ABX_` (including `ABX_SERVER_TOKEN`)

---

## Recommended Patterns

### Pattern 1: Inject at Creation (Most Common)

Best for variables that should be available throughout the sandbox's lifetime:

```python
sandbox = await Sandbox.create(
    template="base",
    envs={
        "DATABASE_URL": db_url,
        "API_KEY": api_key,
        "APP_ENV": "production",
    },
)

# All subsequent commands see these variables
result = await sandbox.commands.run("printenv DATABASE_URL")
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

### Pattern 4: Server-Scoped Config (SandboxServer Only)

When using a SandboxServer with custom commands, use `POST /env` for runtime config that only the Server needs:

```python
import httpx

url = sandbox.network.get_url(9000)
headers = sandbox.network.get_access_headers()

httpx.post(
    f"{url}/env",
    headers={**headers, "Content-Type": "application/json"},
    json={"vars": {"FEATURE_FLAG_X": "enabled"}},
)

# This variable is now visible to Server command handlers:
result = await sandbox.run("my_handler")
```

---

## Client Configuration Variables Are Not Sandbox Variables

The variables that configure the SDK and CLI on **your** machine (`ABX_SANDBOX_API_KEY`, `ABX_PROVIDER`, `ALIBABA_CLOUD_REGION_ID`, ...) are read by the client and are never copied into a sandbox. To make a value visible inside a sandbox, pass it explicitly with `envs=` / `--env`. Each client setting has one variable. Names and precedence are in the [Configuration Reference](../reference/configuration.md#environment-variables).

Two consequences:

- Inside the Server, every name starting with `ABX_` is protected (see above). Do not use `ABX_*` for your own sandbox variables.
- [Provider plugins](providers.md) do not inherit your shell environment either. An `exec` plugin process starts with a scrubbed environment; the configuration values it needs are sent in its `initialize` request. A `node` provider is not that process: the Python SDK sends the resolved options on each call to the local engine.

---

## Security Considerations

1. **Secrets in envs**: Environment variables passed via `envs=` at creation time are transmitted to the platform API. Ensure your transport uses HTTPS (the default). Avoid logging env dicts that contain secrets.

2. **`GET /env` redaction**: The Server's `GET /env` endpoint automatically redacts variables whose names contain `TOKEN`, `SECRET`, `KEY`, `PASSWORD`, or `CREDENTIAL`.

3. **Protected Server variables**: `POST /env` blocks writes to `PATH`, `HOME`, `USER`, `SHELL`, and all `ABX_*` variables to prevent accidental breakage.

4. **No cross-scope leakage**: Variables set via `POST /env` on the Server are invisible to envd processes, and vice versa. This is a security feature, not a bug.

5. **Prefer `printenv`** over `echo $VAR`: Since envd uses direct exec, `echo $VAR` prints the literal string `$VAR`. Use `printenv VAR` or `sh -c 'echo $VAR'` instead.

---

## Quick Reference

| Method | Parameter | Scope | Lifetime |
|--------|-----------|-------|----------|
| `Sandbox.create(envs=)` | `envs` | envd | Sandbox lifetime |
| `commands.run(env=)` | `env` | envd | Single command |
| `run_code(envs=)` | `envs` | envd | Single execution |
| `@sandbox(envs=)` | `envs` | envd | Decorator call |
| CLI `--env KEY=VAL` | `--env` | envd | Sandbox lifetime |
| `POST /env` | `vars` | Server | Server process lifetime |

---

## See Also

- [SDK Usage Guide](sdk-usage.md) — `commands.run()` and `run_code()` usage
- [Declarative Usage](declarative-usage.md) — `@sandbox(envs=)` decorator
- [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md) — `abx create --env`
- [Configuration Reference](../reference/configuration.md) — SDK/CLI environment variables (one name per key)
- [Providers](providers.md) — selecting and installing sandbox providers
