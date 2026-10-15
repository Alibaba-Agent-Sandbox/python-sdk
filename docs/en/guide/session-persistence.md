# Session Persistence

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @agent-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

A session associates a sandbox with a human-readable name, making it easy to reconnect to the same sandbox from different terminals or at different times.

---

## Session Concept

A session is a mapping between a sandbox ID and a name. With sessions, you can:

- Use a name instead of a sandbox ID to operate on a sandbox
- Connect to the same sandbox from different terminal windows
- Reconnect after a temporary disconnection

### Session Data Model

Each session contains the following information (`SessionInfo`):

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Session name |
| `sandbox_id` | `str` | Associated sandbox ID |
| `template` | `str` | Template used |
| `created_at` | `datetime` | Creation time |
| `metadata` | `dict` | Metadata |

---

## Local Storage

Sessions use local filesystem storage by default, implemented by `LocalSessionStore`.

### Storage Location

```text
~/.abx/sessions/
├── my-project.json       # Session "my-project"
├── my-project.json.lock  # Concurrency lock file
├── dev-env.json          # Session "dev-env"
└── ...
```

Each session is saved as a JSON file, with the filename derived from the session name (non-alphanumeric/hyphen/underscore characters are replaced with `_`).

### Concurrency Protection

File reads and writes are protected by file locks:
- Prefers the `filelock` library (if installed)
- Falls back to POSIX `fcntl` locks (macOS/Linux)

---

## CLI Usage

> **Note**: The `abx session` CLI command group has been removed from the CLI. Session functionality is now provided entirely through the SDK API. The examples below are for reference only; please use the Python SDK in practice.

### SDK Alternative

```python
from agent_sandbox.session import SessionManager

manager = SessionManager()

# Start a session
await manager.start("my-project", template="base", timeout=600)

# Connect to a session
sb = await manager.connect("my-project")

# List sessions
sessions = await manager.list()

# Stop a session
await manager.stop("my-project")
```

---

## SDK Usage

```python
from agent_sandbox.session.local import LocalSessionStore
from agent_sandbox.models.session import SessionInfo

# Create a store instance
store = LocalSessionStore()  # Default ~/.abx/sessions/

# Save a session
session = SessionInfo(
    name="my-project",
    sandbox_id="sbx-xxxx",
    template="base",
)
await store.save("my-project", session)

# Load a session
session = await store.load("my-project")
if session:
    print(f"Sandbox: {session.sandbox_id}")

# List all sessions
sessions = await store.list_all()

# Delete a session
await store.delete("my-project")
```

---

## Custom Storage Location

```python
store = LocalSessionStore(base_dir="/path/to/custom/sessions")
```

---

## Next Steps

- [CLI Tutorial](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/cli-tutorial.md) — Complete CLI tutorial
- [Configuration Reference](../reference/configuration.md) — Config file locations
