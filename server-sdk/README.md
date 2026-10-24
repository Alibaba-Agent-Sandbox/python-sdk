# agent-sandbox-server

This package is the opt-in **0.3.1a1 alpha** candidate. Use its exact PyPI version after verified publication; before that, use the [tested paired source recipe](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/install-python.md). Alpha publication does not establish every provider or template as production-ready.

**Server SDK.** This package runs *inside* a sandbox image. It is the HTTP service the image starts (default port 9000). It does not create the sandbox. Creating and calling the sandbox is the [client SDK](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/client-sdk/README.md) or the `abx` CLI. Guide: [Server SDK](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/docs/en/guide/server-sdk.md).

It exposes files, processes, system info, a PTY terminal, optional dev tools / browser automation, and your own registered commands.

The HTTP server is stdlib-only. `websockets` is installed for the PTY terminal endpoint.
Import path: `agent_sandbox.server` (a namespace shared with `agent-sandbox-client`).

## Install

```bash
python -m pip install 'agent-sandbox-server==0.3.1a1'
python -m pip check
```

The opt-in browser capability group imports Playwright lazily; install `playwright` in the
image yourself if you enable it (without it the browser endpoints answer `503`).

## Use inside a template's `commands.py`

```python
from agent_sandbox.server import command, start


@command(description="Say hello")
def hello(name: str = "world") -> dict:
    return {"message": f"Hello, {name}!"}


start(9000)
```

Every endpoint is one row of `agent_sandbox.server.endpoints.ENDPOINTS`. A capability group
(`commands`, `file_ops`, `process`, `terminal`, `system`, `dev_tools`, `browser`, `agents`) is a
name for the endpoints that declare it. `core` is always on, the groups through `terminal` and
`system` start on, and `dev_tools`, `browser` and `agents` start off. Turn one on with
`default_table().enable_group(CapabilityGroup.DEV_TOOLS)` in `commands.py`, with a policy
`groups: [dev_tools]`, or with `ABX_SERVER_ENABLED_GROUPS=dev_tools` in the environment. See the
[server API design](https://github.com/alibaba-agent-sandbox/python-sdk/blob/main/docs/en/design/server-api.md).

Command registration supports `list[str]` with strict native JSON arrays. See the [bilingual server API guide](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/template-server-api.md#string-array-command-arguments).

## Develop

```bash
pip install -e "./server-sdk[dev]"
cd server-sdk && pytest && ruff check src tests && mypy src/agent_sandbox/server
```

Licensed under Apache-2.0.
