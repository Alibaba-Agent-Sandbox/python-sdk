---
name: agent-sandbox-sdk
description: Write a Python client or a sandbox template for Agent Sandbox. Use when the task is Sandbox.create, a built-in provider, template.yaml, a Dockerfile, commands.py with @command, or the Agents API on port 9000. Do not use this to run abx, MCP, or an existing sandbox from the shell; that skill is agent-sandbox.
---

# Write an Agent Sandbox client or template

This file is instructions for a coding agent. It is not executed by the SDK.
Operating a sandbox with `abx` or MCP is the `agent-sandbox` skill. This skill
only covers the code you write.

Two packages share one version:

| Package | Import | Where it runs |
|---|---|---|
| `agent-sandbox` | `agent_sandbox` | The caller's machine |
| `agent-sandbox-server` | `agent_sandbox.server` | Inside the image, port 9000 |

`pip install agent-sandbox` installs the client and depends on
`agent-sandbox-server`. The image installs only `agent-sandbox-server`.

## Credentials

The client reads `ABX_SANDBOX_API_KEY` from the process environment, `./.env`,
or `~/.abx/.env`. It does not read `E2B_*` or `SANDBOX_*`.

AK/SK, when a call needs them, are `ALICLOUD_ACCESS_KEY_ID` and
`ALICLOUD_ACCESS_KEY_SECRET`. Never print a key, never commit one, and never
put one in a template. Examples use `REPLACE_ME`.

## Client

```python
import asyncio
from agent_sandbox import Sandbox

async def main() -> None:
    async with await Sandbox.create(template="python-hello", timeout=300) as sb:
        result = await sb.commands.run("python3 --version", timeout=30)
        print(result.stdout)
        print(await sb.run("hello", name="Ada"))

asyncio.run(main())
```

- `timeout` on `create` is how long the sandbox lives, not the HTTP timeout. `request_timeout` bounds the create HTTP call.
- A shell command is `sb.commands.run`. A function registered in `commands.py` is `sb.run(name, **kwargs)`, which returns the unwrapped `result`.
- `sb.commands.run` wraps an unquoted pipe, redirect, or `&&` in `sh -c`. A variable, backtick, or glob still needs an explicit `sh -c '...'`. Its `timeout` defaults to 60 seconds. `send_signal` accepts only 15 (SIGTERM) and 9 (SIGKILL).
- `sb.run_code(...)` checks capability `code` and raises when the template does not declare it. An omitted `capabilities` list means `shell`, `files`, and `code`.
- Files on `sb.files`: `write`, `read`, `read_bytes`, `list`, `exists`, `remove`, `make_dir`, `upload`, `download`. On Express, `sb.files.upload_url` and `sb.files.download_url` return an envd URL that still needs header `X-Access-Token`. A provider that does not declare `files.transfer` raises `E8004`. `sb.upload_url` and `sb.download_url` always refuse. Do not invent a signature-only URL.
- The context manager kills the sandbox. Otherwise call `await sb.kill()`.
- The default provider is `alicloud-express`. Express sends create through a local engine on `~/.abx/engine.sock` (`ABX_ENGINE_SOCKET`). Do not open those backend sockets yourself and do not spawn a provider process. `python -m agent_sandbox.engine` is only a shared engine process.
- The only built-in provider is `alicloud-express`. `opensandbox`, `alicloud-container`, `cubesandbox`, and `e2b` are not part of this package. Install them from the catalog with `python -m agent_sandbox.providers install registry:<id> --yes`, then pass that id to `Sandbox.create`. Their notes are in `awesome-providers/<id>/docs/README.md`. Only Express reads `ABX_SANDBOX_API_KEY`.

| id | What it is | Required environment |
|---|---|---|
| `alicloud-express` | Alibaba Cloud Express. The default. Built into the SDK. | `ABX_SANDBOX_API_KEY`, or AK/SK |

URLs, headers, and calls that raise `E8004` for Express are in `references/providers.md`. The `abx` CLI loads `alicloud-express` plus installed `node`, `exec` and `rest` plugins. The four catalog providers are `node`. After `abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes`, `abx --provider <id>` works. A manifest with `kind = "python"` cannot be installed. An in-code `Provider` subclass still works from the SDK only.

Other client calls:

- `await Sandbox.connect(sandbox_id)` attaches to one that already exists. `await Sandbox.kill_by_id(sandbox_id)` destroys it without connecting. On Express, killing a missing id succeeds.
- `await sb.set_timeout(seconds)` changes the lifetime. `await sb.kill()` destroys the sandbox. `await sb.close()` drops the local client and leaves the sandbox running.
- `sb.network.get_url(port)` is the port URL. Secure mode also needs `sb.network.get_access_headers()` (`X-Access-Token`). `await sb.network.resolve(port)` asks the provider when it publishes port URLs.
- `sb.server` is the typed client for the in-sandbox HTTP server on port 9000. It covers files, process, PTY, browser, and dev tools on that server. It does not cover `/v1/agents/**`.
- `await sb.get_terminal()` opens a PTY. There is no `Sandbox.custom` and no `sb.agent`. An agent session is HTTP on port 9000 after the `agents` group is enabled. See `references/templates.md`.
- `await sb.pause()` and `await sb.resume()` post `/sandboxes/{id}/pause` and `/resume` on a provider that declares `sandbox.pause`. Do not assume Express implements that path.
- `@sandbox` on a client function runs that function in a sandbox. It does not register a template command. Template commands are `@command` in `commands.py`.

## Template

When a `Dockerfile` is present, that file is the image (`--build auto` chooses
it). These `template.yaml` keys are not build inputs: `base`, `system_packages`,
`python_packages`, `node_packages`, `commands`. `custom_commands` is rejected
by the Python client. Deploy does not apply a `server:` block. Do not use it
to turn groups on. Without a Dockerfile, `base.image` and `build:` are platform
steps; that path is in `references/templates.md`. For `alicloud-express`, write
the FC Dockerfile below.

```yaml
name: my-template
version: "1.0.0"
description: "What this sandbox is for"
user: user
workdir: /home/user/app
capabilities:
  - shell
  - files
  - code
ports:
  - 9000
```

`commands.py` — module-level `@command`, then `start()` only under
`if __name__ == "__main__"`. A `start()` call at import time breaks the
platform `--commands` import. Do not use `@sandbox.register` or `@registry.command`.

```python
from __future__ import annotations

import os

from agent_sandbox.server import CapabilityGroup, command, default_table, start

table = default_table()
table.enable_group(CapabilityGroup.DEV_TOOLS)  # only for an opt-in group


@command("hello", description="Say hello.")
def hello(name: str = "World") -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    start(int(os.environ.get("ABX_SERVER_PORT", "9000")))
```

`dev_tools`, `browser`, and `agents` start disabled. Turn one on with
`enable_group(CapabilityGroup.AGENTS)` or `start(policy=...)`.
`ABX_SERVER_ENABLED_GROUPS` only turns groups on. There is no
`ABX_SERVER_DISABLED_GROUPS`.

`POST /commands/hello` takes a flat body `{"name":"Ada"}`. The response is
`{"result":"Hello, Ada!"}`. `sb.run` unwraps `result`.

### Dockerfile for the default provider

`alicloud-express` uses the FC base image. Do not add `CMD` or `ENTRYPOINT`.
Do not listen on 49983, 5000, or 49999. `<region>` defaults to `cn-hangzhou`.
`<tag>` defaults to `v0.0.49` (`ABX_BASE_IMAGE_TAG` overrides it). The platform
starts the server with
`agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py`.

```dockerfile
FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
COPY *.whl /tmp/
RUN if ls /tmp/*.whl 1>/dev/null 2>&1; then \
        pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl; \
    else \
        pip install --no-cache-dir agent-sandbox-server; \
    fi
WORKDIR /home/user/app
COPY commands.py /home/user/app/commands.py
EXPOSE 9000
```

### Dockerfile for any other provider

OpenSandbox and a provider with no `[template]` profile use this image, not the FC image.

```dockerfile
FROM python:3.12-slim
COPY *.whl /tmp/
RUN if ls /tmp/*.whl 1>/dev/null 2>&1; then \
        pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl; \
    else \
        pip install --no-cache-dir agent-sandbox-server; \
    fi
WORKDIR /app
COPY commands.py .
EXPOSE 9000
CMD ["python3", "commands.py"]
```

`abx template init` writes this same `commands.py` shape. `abx template deploy`
injects the server wheel into the build context. Without a wheel, the image
installs `agent-sandbox-server` from PyPI. Generation, reserved ports, group
policy, and platform steps are in `references/templates.md` next to this file.
Copy this directory whole. `references/templates.md` and `references/providers.md` stay beside `SKILL.md`.

## Deploy, test, publish

Deploy and `abx` operation belong to the `agent-sandbox` skill. The commands
this template needs:

```bash
abx template deploy ./my-template --acr-namespace "$ACR_NAMESPACE" --acr-repo my-template --alias my-template --yes
```

`--yes` is required when stdin is not a terminal. Docker must be running for
a Dockerfile build. `codex` and `openclaw` are reserved. Set `template.yaml`
`name` and `--alias` to `openai-codex` or `openclaw-agent`. Sending the
reserved name is rejected.

Local check, from the template directory, with `agent-sandbox-server` installed:

```bash
ABX_SERVER_PORT=9000 python3 commands.py
```

Then `GET /health` and `POST /commands/hello` with `{"name":"Ada"}`.

From a checkout of this repository, `make test` runs both packages. `make e2e`
creates real sandboxes and deletes the ones it tagged. Kill any sandbox you
create yourself.

Publishing the Python packages is a maintainer release of
`alibaba-agent-sandbox/python-sdk`: both `_version.py` files match, `make ci`
passes, and the GitHub Release workflow publishes `agent-sandbox-server` first.
Do not upload from a laptop. Do not put a PyPI token in the repo or in chat.

## Hard rules

1. Client code imports `agent_sandbox`. `commands.py` imports `agent_sandbox.server` only.
2. Named commands are `@command` and `start()` under `if __name__ == "__main__"`.
3. The default provider's Dockerfile is the FC base image, with no `CMD`.
4. Do not read or write `E2B_*`.
5. Do not leak credentials. Do not leave sandboxes running.
