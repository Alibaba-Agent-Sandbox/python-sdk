# easy-sandbox-server

Container-side **server SDK** for Easy Sandbox templates. It is the persistent HTTP service that
runs *inside* a sandbox image (default port 9000) and exposes files, processes, system info,
a PTY terminal, optional dev tools / browser automation, and your own registered commands to the
[client SDK](../client-sdk/README.md) and the `ebx` CLI.

The HTTP server is stdlib-only. `websockets` is installed for the PTY terminal endpoint.
Import path: `easy_sandbox.server` (a namespace shared with `easy-sandbox`).

## Install

```bash
pip install easy-sandbox-server
```

The opt-in browser capability group imports Playwright lazily; install `playwright` in the
image yourself if you enable it (without it the browser endpoints answer `503`).

## Use inside a template's `commands.py`

```python
from easy_sandbox.server import CapabilityGroup, default_registry, start

@default_registry.command(description="Say hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}

start(9000)
```

Capability groups: `CORE`, `COMMANDS`, `FILE_OPS`, `PROCESS`, `SYSTEM`, `TERMINAL` (enabled by
default), `DEV_TOOLS`, `BROWSER` (opt-in). See `docs/en/design/server-api.md` in the
[python-sdk docs](../docs/en/design/server-api.md).

## Develop

```bash
pip install -e "./server-sdk[dev]"
cd server-sdk && pytest && ruff check src tests && mypy src/easy_sandbox/server
```

Licensed under Apache-2.0.
