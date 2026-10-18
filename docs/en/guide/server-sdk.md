# Server SDK

For current SDK installation, use the [paired source installation guide](install-python.md).

The Server SDK runs **inside the sandbox**. It is the HTTP service the image keeps listening on, port 9000 by default. The package is `agent-sandbox-server`. Import `agent_sandbox.server`. A template's `commands.py` uses it to register commands, turn capabilities on, and call `start(9000)`.

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=server-sdk"
```

```python
from agent_sandbox.server import command, start


@command(description="Say hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}


if __name__ == "__main__":
    start(9000)
```

This code does not create a cloud sandbox and does not read a sandbox API key. Creating the sandbox and calling these routes is the [Client SDK](client-sdk.md) or the `abx` CLI.

## Load commands with the CLI

Keep server startup separate from command registration by using the `serve` subcommand:

```bash
agent-sandbox-server serve --commands ./commands.py --port 9000
```

The file is imported before the HTTP server starts, so its `if __name__ == "__main__"`
block does not run. Files using `from __future__ import annotations` and `@dataclass`
work like normal imports: their module is available in `sys.modules` while decorators
execute. Repeat `--commands` to load several files or importable module names.

Within a process, a file is loaded once per canonical path, including relative,
absolute and symbolic-link aliases. Separate files named `commands.py` remain separate
modules. Restart the server to reload changed files. The file's directory remains on
the import path for sibling imports. If loading raises, the incomplete module entry
and that load's import-path changes are removed, and the exception stops startup.
Other side effects, such as commands already registered before the exception, are
not rolled back; fix the file and restart the server.

## Start here

| Guide | What it covers |
|------|----------------|
| [Authoring templates](authoring-templates.md) | `template.yaml`, the Dockerfile, `commands.py` |
| [Template server HTTP API](template-server-api.md) | The routes the process actually serves |
| [Best practices](best-practices.md) | The server carries no provider; turn groups on only when needed |
| [Fine-grained capabilities](fine-grained-capabilities.md) | Enable routes one endpoint at a time |
| [File and command controls](file-and-command-controls.md) | Limit paths and commands |
| [Agents API](agents-api.md) | HTTP sessions for Codex and Qwen Code inside the sandbox |
| [Hosted agents](hosted-agents.md) | How those routes refuse and what they return |

Reference: [Server HTTP API](../reference/server-http-api.md), [template.yaml](../reference/template-yaml-spec.md), [Agents API reference](../reference/agents-api.md), [Server API design](../design/server-api.md).

## Examples

These `commands.py` files start with the image. See the [example index](../../../examples/README.md#server-sdk-examples):

- `examples/templates/python-hello/commands.py` — the smallest command server
- `examples/templates/agents-cli/commands.py` — only the session Agents routes are open

`examples/templates/python-hello/call_api.py` is not the Server SDK. It runs outside the sandbox and sends HTTP to a server that is already listening. That script is a Client SDK example.
