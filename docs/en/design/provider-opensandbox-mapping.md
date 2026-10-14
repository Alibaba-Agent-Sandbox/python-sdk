# OpenSandbox provider

> **Status**: current adapter. The research and the 2026-10-13 exec-plugin record are [provider-opensandbox-research.md](../archive/provider-opensandbox-research.md).
>
> Chinese page: [zh](../../zh/design/provider-opensandbox-mapping.md). The same table in code is the `FEATURES` list and the method tables in `awesome-providers/opensandbox/provider.mjs`.

## Current adapter (2026-10-14)

OpenSandbox is a catalog provider. The source is `awesome-providers/opensandbox`, id `opensandbox`. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//opensandbox --allow-unpinned --yes` (or `python -m agent_sandbox.providers install registry:opensandbox --yes`). After install, `Sandbox.create(provider="opensandbox")` and `abx --provider opensandbox` both work. They talk to OpenSandbox HTTP, execd SSE, and the execd WebSocket from the Node host process that loads `provider.mjs`. The Python SDK reaches that module through the local engine (`abx provider engine serve`, started on demand; `abx` must be on `PATH` or in `ABX_BIN`) using `EngineProvider`. Sandbox URLs from that provider look like `engine://opensandbox/<sandbox-id>`.

The manifest is `kind = "node"` and `protocol = "node/1"`: a dependency-free ES module (`provider.mjs`). The host runs its EPP/1 methods in-process. `node provider.mjs` still serves EPP/1 on stdio. The terminal needs the global `WebSocket` of Node 22+. Before install, `abx --provider opensandbox sandbox create` exits 4 with `E8001`. Its own notes are `awesome-providers/opensandbox/docs/README.md`.

| Setting | Environment |
|---|---|
| Lifecycle URL, without `/v1` | `ABX_OPENSANDBOX_BASE_URL`, alias `OPENSANDBOX_BASE_URL`. Default `http://127.0.0.1:8080` |
| Header `OPEN-SANDBOX-API-KEY` | `ABX_OPENSANDBOX_API_KEY`, aliases `OPEN_SANDBOX_API_KEY` and `OPENSANDBOX_API_KEY` |

`template="base"` uses the image `python:3.12-slim` and the entrypoint `tail -f /dev/null`. A template that contains `:` or `/` is used as an image URI.

The tables record real calls on 2026-10-14 against OpenSandbox 1.1.1 (`127.0.0.1:8080`, Docker, `opensandbox/execd:latest`) and Alibaba Cloud Express in `cn-hangzhou`. The comparison did not all pass.

### Both sides, and the adapter calls OpenSandbox

| Capability | Tool id | OpenSandbox | What the call returned |
|---|---|---|---|
| Create, connect, get, list, kill | `sandbox.lifecycle` | `POST` / `GET` / `DELETE /v1/sandboxes` | OpenSandbox created, listed and killed twice. Alicloud SDK and CLI created and killed |
| Change lifetime | `sandbox.timeout` | `POST /v1/sandboxes/{id}/renew-expiration` | OpenSandbox accepted 240s. Alicloud SDK accepted 420s |
| Pause and resume | `sandbox.pause` | `POST …/pause` and `…/resume` | OpenSandbox went `PAUSED` then `RUNNING`. Alicloud `POST /pause` returned HTTP 400 |
| Run a command | `exec.run` | execd `POST /command` (SSE) | OpenSandbox stdout `osb-exec ok`. Alicloud SDK `sdk-exec ok`. CLI `cli-exec ok` |
| Stream a command | `exec.stream` | same SSE | Both sides printed the streamed marker |
| Process list and signal | `process.manage` | no process API; list is `ps`, signal is `kill` | OpenSandbox listed 4 pids. Alicloud CLI saw `sleep` pid 4 and delivered signal 15. Alicloud SDK `commands.list()` returned 0 |
| Terminal | `pty` | `POST /pty` and WebSocket `/pty/{id}/ws`; the engine strips the `0x00` frame prefix | OpenSandbox printed `42`. Alicloud envd `/terminal` returned WebSocket 404 |
| File read, write, list, move, remove | `files.rw` | execd `/files` and `/directories` | Both sides read back what was written. CLI upload then download returned `cli-upload` |
| Port URL | `ports.url` | `GET /v1/sandboxes/{id}/endpoints/{port}` | OpenSandbox returned `http://127.0.0.1:<port>`. Alicloud SDK computed the `8080-sbx-…` gateway host |

`commands.send_input` is not a separate feature. OpenSandbox `/command` has no stdin, so the call returns `E8004`.

### The tool has it, OpenSandbox does not

The adapter refuses these with `E8004`.

| Capability | Tool id | What the call returned |
|---|---|---|
| Watch a directory | `files.watch` | OpenSandbox refused. Alicloud SDK received `MODIFIED` |
| File URL | `files.transfer` | OpenSandbox has no envd `/files` URL |
| Read templates | `templates.read` | Docker `GET /templates` is 501 (fsb microVMs only). Alicloud `template list` returned 26 account templates; `template info base` returned a real template |
| Build and publish a template | `templates.build` | Not invoked. OpenSandbox Docker cannot build a template |
| Domain-style port host | `ports.domain` | Only Alicloud computes `{port}-{id}.{domain}` |
| Mount storage | `storage.mount` | No mount call is made |
| VPC | `network.vpc` | Alicloud platform option. It is not sent to OpenSandbox |
| Named commands on SandboxServer | `sessions` | Alicloud `GET /commands` on the `base` image returned 502. That image has no SandboxServer |

### OpenSandbox has it, this tool does not call it

These are not in `features`.

| OpenSandbox API | Note |
|---|---|
| `POST /code` | Only a code-interpreter image has Jupyter. `python:3.12-slim` does not. `run_code` returns `E8004` |
| `POST /session` and `/session/{id}/run` | Stateful shell. `cd` and `export` survive across runs |
| `GET /command/{id}/logs` | Tail of a background command. `exec.stream` uses the foreground SSE |
| `POST /v1/sandboxes/{id}/snapshots` | Sandbox snapshot |
| `/v1/sandboxes/{id}/networkpolicy` | Egress policy. Needs the egress sidecar |
| `PATCH /v1/sandboxes/{id}/metadata` | Metadata after create. Create still sends metadata |
| diagnostics, execd `GET /metrics` | Diagnostics and metrics |

### Alicloud calls that did not pass

- Pause: the platform returned HTTP 400.
- Terminal: envd `/terminal` WebSocket 404.
- SDK process list: returned 0. The CLI saw the background `sleep` on its own sandbox.
- `abx sandbox list` immediately after create: `No sandboxes found.` `abx sandbox info` read that sandbox at the same time.
- `abx sandbox system ports`: exit 1. The base image has neither `ss` nor `netstat`.
- Named commands: `GET /commands` returned 502.

Alicloud `run_code("print(6*7)")` got HTTP 404 from the code interpreter and fell back to the shell. stdout was `42`. That path is not OpenSandbox.

### Registering more capabilities

The OpenSandbox-only APIs stay out of the fixed 18 feature ids. Putting them there would add them to `alicloud-express` and to the contract tests. A Python `Provider` subclass registers them on `Provider.extensions`. The installed catalog provider is `EngineProvider` (`kind = "node"`); its `extensions` tuple is empty. The tables below describe a subclass that sets `extensions`. They do not describe the installed `opensandbox` provider.

Registration means the provider knows about the operation. `implemented=False` still raises `E8004` on a call. Seeing an extension and calling it are different.

**When it is visible**

| Place | What you see |
|---|---|
| `provider.describe()["extensions"]`, and later `provider info` | Every extension this provider registered. The image and the sandbox do not matter |
| `extensions_for(sandbox_id=...)` | Only the extensions whose condition matches this sandbox |
| Another provider, such as `alicloud-express` | None of these ids. Its `extensions` is empty |
| CLI `abx --provider opensandbox` | After install, the CLI loads this provider and create works. `abx provider list` prints `features` only. These extension ids are not on the `node` provider. An id that is not installed still exits 4 with `E8001` |

**When a sandbox does not show it**

`extensions_for` returns `()` when `sandbox_id` is empty. After a sandbox id exists:

| Extension | Shown on the sandbox when | Callable now |
|---|---|---|
| `session`, `snapshot`, `metadata.patch`, `diagnostics`, `metrics` | Any sandbox id | No. `require_extension` returns `E8004` |
| `code` | The image name contains `code-interpreter`. Hidden on `python:3.12-slim` | No |
| `networkpolicy` | This create asked for the egress sidecar | No |
| `command.logs` | The caller already has a background command id | No |

`abx provider list` prints `features` only. Extensions appear on the provider detail.

**How to register**

A Python provider sets `extensions` on the class:

```python
from agent_sandbox.providers.base import Extension, Provider

class Example(Provider):
    extensions = (
        Extension(
            id="session",
            summary="Stateful shell.",
            summary_zh="有状态 shell。",
            implemented=False,
            when="sandbox",
        ),
    )
```

`when` is one of `sandbox`, `code_interpreter_image`, `egress`, `command`. An earlier Python provider kept OpenSandbox's eight entries on `opensandbox_provider.EXTENSIONS`. That module is gone. The current catalog provider does not register them.

An exec or rest manifest will use the block below. The parser does not accept it yet:

```toml
[features.extensions.session]
summary = "Stateful shell."
summary_zh = "有状态 shell。"
implemented = false
when = "sandbox"
```

Do not put these ids in `[features] supported`. That list accepts only the fixed 18 ids.

**How to use**

```python
from agent_sandbox.providers.registry import get_provider

provider = get_provider("opensandbox")  # after `registry:opensandbox` is installed
provider.kind                              # "node"
provider.describe()["extensions"]          # () on EngineProvider
provider.extensions_for(sandbox_id="sb-1") # ()
```

A Python subclass that sets `extensions` still filters with `extensions_for` and raises `E8004` from `require_extension` while `implemented` is false. When an entry is implemented, set `implemented=True` and add the HTTP call in `awesome-providers/opensandbox/provider.mjs`.

The research that produced the first plugin, including the 2026-10-13 exec-plugin record, is [provider-opensandbox-research.md](../archive/provider-opensandbox-research.md). It is not the adapter above.
