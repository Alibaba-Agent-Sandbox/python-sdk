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
| `agent-sandbox-client` | `agent_sandbox` | The caller's machine |
| `agent-sandbox-server` | `agent_sandbox.server` | Inside the image, port 9000 |

Install the verified public alpha pair; the client installs its matching server dependency:

```bash
python -m pip install 'agent-sandbox-client==0.3.1a5'
python -m pip check
```

The image needs only `agent-sandbox-server==0.3.1a5`. Installing that package on the host does not update an existing image. Development source installations must use a matching client/server revision.
Do not run `pip install agent-sandbox`. That PyPI name is an unrelated project.

## Credentials

ProviderSandbox reads `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN`. Standard clients also map the E2B environment names according to the [migration contract](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/migrate-from-e2b.md). Preserve the selected entry's configuration; never forward a control-plane key as an application token.

AK/SK, when a call needs them, are `ALICLOUD_ACCESS_KEY_ID` and
`ALICLOUD_ACCESS_KEY_SECRET`. Never print a key, never commit one, and never
put one in a template. Examples use `REPLACE_ME`.

## Standard E2B migration

Root Sandbox is synchronous and AsyncSandbox is asynchronous, following E2B 2.31.0.
The code_interpreter namespace follows interpreter 2.8.1. Existing supported Alibaba
E2B code changes imports and keeps its configured credentials/endpoints:

```python
from agent_sandbox.code_interpreter import Sandbox

sb = Sandbox.create(template="code-interpreter-v1", timeout=300)
try:
    print(sb.commands.run("printf hello").stdout)
    print(sb.run_code("1 + 1").text)
finally:
    sb.kill()
```

Do not add await to synchronous code. Use the async class for async code. Preserve
lazy paginators, standard result/error models, seconds-based timeout arguments and
process handles. Signed file URLs and conditional pause/snapshot/network APIs keep
the reference protocol and backend restrictions; do not apply the ProviderSandbox
limitations below to the standard clients. Pause success requires an enabled
function; snapshots require a supported MicroVM runtime/account. Third-party
hardcoded imports need an adapter injection hook or a maintained small fork.
See the [migration contract](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/docs/en/guide/migrate-from-e2b.md).

## Provider/server extensions

The rest of this skill describes the explicit asynchronous ProviderSandbox API
for custom providers, named server commands, sessions and declarative execution.
Do not import the root standard Sandbox for these examples.


First launch the application template through the CLI. Set `SANDBOX_ID` to its returned instance ID, `ABX_PROVIDER` to its owning provider and `ABX_SERVER_TOKEN` to the application token configured before launch. `base` does not imply a registered `hello` command.

```python
import asyncio
import os
from agent_sandbox import ProviderSandbox

async def main() -> None:
    sb = await ProviderSandbox.connect(
        os.environ["SANDBOX_ID"], provider=os.environ["ABX_PROVIDER"]
    )
    try:
        async with await sb.application_client(
            9000, token=os.environ["ABX_SERVER_TOKEN"], timeout=330
        ) as client:
            print(await client.commands.run("hello", name="Ada"))
    finally:
        await sb.close()  # borrowed instance; its owner deletes it

asyncio.run(main())
```

This binding preserves the provider gateway's headers and full URL/query. Explicit application tokens also use `X-Access-Token` only when that header is free; gateway credentials are never overwritten. Request timeout does not cancel remote work or replay the command.

- `timeout` on `create` is how long the sandbox lives, not the HTTP timeout. `request_timeout` bounds the create HTTP call.
- A shell command is `sb.commands.run`. A function registered in `commands.py` is `sb.run(name, **kwargs)`, which returns the unwrapped `result`.
- `sb.commands.run` wraps an unquoted pipe, redirect, or `&&` in `sh -c`. A variable, backtick, or glob still needs an explicit `sh -c '...'`. Its `timeout` defaults to 60 seconds. `send_signal` accepts only 15 (SIGTERM) and 9 (SIGKILL).
- `sb.run_code(...)` requires the exact provider operation: `code.execute` for stateless mode, `code.default-context.execute` for explicit `mode="default-context"`, or `code.context.execute` for a context ID. An installed interpreter package does not implement these operations. Native `alicloud-express` currently refuses interpreter calls; use the supported standard `agent_sandbox.code_interpreter` client for its separate backend contract.
- Files on `sb.files`: `write`, `read`, `read_bytes`, `list`, `exists`, `remove`, `make_dir`, `upload`, `download`. On Express, `sb.files.upload_url` and `sb.files.download_url` return an envd URL that still needs header `X-Access-Token`. A provider that does not declare `files.transfer` raises `E8004`. `sb.upload_url` and `sb.download_url` always refuse. Do not invent a signature-only URL.
- A ProviderSandbox context manager kills the sandbox. For a newly created instance use `kill()` and `close()` in cleanup; for a borrowed connection use only `close()` unless deletion was authorized.
- ProviderSandbox defaults to alicloud-express. Use its configured provider transport; do not hardcode a local engine socket or spawn a separate provider implementation.
- The only built-in provider is `alicloud-express`. `opensandbox`, `alicloud-container`, `cubesandbox`, and `e2b` are not part of this package. Install them from the catalog with `python -m agent_sandbox.providers install registry:<id> --yes`, then pass that id to `Sandbox.create`. Their notes are in `awesome-providers/<id>/docs/README.md`. Native ProviderSandbox reads canonical `ABX_SANDBOX_API_KEY`; only the standard entry maps `E2B_*` settings.

| id | What it is | Required environment |
|---|---|---|
| `alicloud-express` | Alibaba Cloud Express. The default. Built into the SDK. | `ABX_SANDBOX_API_KEY`; AK/SK separately authorizes control-plane operations |

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

Use strict specification 4. `capabilities` and `tested_on` are retired; installed software does not grant provider operations. This minimal source application follows the current offline fixture:

```yaml
name: my-template
version: "1.0.0"
description: "A hello application"
spec_version: 4
workflow_contract_version: 1
provides:
  app:
    protocol: agent-sandbox-server
    version: 2
    port: 9000
    operations: [commands.list, commands.run]
default_workflow: application
start_cmd: agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
workflows:
  application:
    kind: application
    input: source
    startup: exec
    service: app
    binding:
      transport: http
      endpoint: provider-port
      caller: host
      authentication: service-token
    operation: commands.run
    required_operations: []

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
`<tag>` defaults to `v0.0.49` (`ABX_BASE_IMAGE_TAG` overrides it). Native deploy profiles use the following start command; unified source launch starts the selected application once after creation with its runtime environment:
`agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py`.

```dockerfile
FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
RUN pip install --no-cache-dir 'agent-sandbox-server==0.3.1a5'
WORKDIR /home/user/app
COPY commands.py /home/user/app/commands.py
EXPOSE 9000
```

### Portable Dockerfile for an author-selected build profile

The CLI can prepare the supported official native base recipe for both Express and OpenSandbox. Do not automatically substitute this portable recipe: declare a `build_profiles.portable` profile and select it explicitly when appropriate.

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir 'agent-sandbox-server==0.3.1a5'
WORKDIR /home/user/app
COPY commands.py /home/user/app/commands.py
EXPOSE 9000
CMD ["python3", "commands.py"]
```

`abx template scaffold` writes this same `commands.py` shape. These Dockerfiles
use the pinned public server package and do not require a local wheel. CLI build
may inject an explicitly selected server wheel or resolve its own pinned archive;
that preprocessing does not apply to a direct `docker build`. Generation, reserved ports, group
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
3. Follow the selected provider/build profile. Do not silently replace an author's Dockerfile; official native placeholders are resolved by the CLI preparation path.
4. Keep native provider configuration on `ABX_*`; standard entry configuration may read `E2B_*`. Never substitute Express credentials for another backend.
5. Do not leak credentials. Do not leave sandboxes running.
