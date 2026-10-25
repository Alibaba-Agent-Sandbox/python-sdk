# Authoring Templates

For current SDK installation, use the [paired source installation guide](install-python.md).

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository ([CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox-client`) and the container-side runtime (`agent-sandbox-server`).

This is the **Server SDK**: `commands.py` starts with the image and serves HTTP inside the sandbox. Creating and calling a sandbox from your machine is the [Client SDK](client-sdk.md).

This document explains how to create custom Agent Sandbox templates, including directory structure, field reference, whole-template startup, registered commands, and publishing.

A template is a directory of plain files, written by hand or generated. The `abx template scaffold` command generates one three ways (built-in scaffold, a one-sentence description, or adopting a project that already has source code); that workflow is documented in the CLI repository: [Authoring Templates (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md).

---

## Template Directory Structure

A complete template directory structure is as follows:

```text
my-template/
├── template.yaml      # Required — template definition
├── Dockerfile         # Image build input; no implicit manifest package installer
├── commands.py        # Optional — named commands via @command
└── README.md          # Optional — template description
```

`template.yaml` is the only required file.

---

## template.yaml Basic Example

```yaml
name: my-python-template
version: 1.0.1
description: Scaffold for a new Agent Sandbox template. Not a catalog entry.
author: alibaba-agent-sandbox
license: Apache-2.0
spec_version: 5
base: fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
generation: 2
start_cmd: agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py
ready_cmd: agent-sandbox-server healthcheck --port 9000
resources:
  cpu: 2
  memory: 2048
ports:
- 9000
tags:
- example
- skeleton
priority: P2
wave: other
env:
  ABX_SERVER_TOKEN: ''
smoke:
- command: hello
  args:
    name: Express
  expect: Hello, Express!
provides:
  app:
    protocol: agent-sandbox-server
    version: 2
    port: 9000
    operations:
    - commands.list
    - commands.run
```

---

## Field Reference

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | ✅ | — | Template name |
| `version` | `str` | ❌ | `"1.0.0"` | Semantic version |
| `description` | `str` | ❌ | `""` | Template description |
| `env` | `dict[str, str]` | ❌ | `{}` | Environment variables |
| `cpu_count` | `int` | ❌ | `None` | Default CPU cores |
| `memory_mb` | `int` | ❌ | `None` | Default memory in MB |
| `ports` | `list[int]` | ❌ | `[]` | Exposed port list |
| `author` | `str` | ❌ | `""` | Author |
| `license` | `str` | ❌ | `""` | License |
| `tags` | `list[str]` | ❌ | `[]` | Tags |

For detailed field definitions, see [template.yaml Spec](../reference/template-yaml-spec.md).

---

<a id="capability-declarations"></a>
## Template startup

Use `spec_version: 5` and declare every service in `provides`. `start_cmd` and
`ready_cmd` apply to the complete template, without named workflow selections.
The Provider supplies platform operations; service policy controls application APIs.
Neither layer implies interpreter support. See [launching templates](template-workflows.md).

Server endpoint policies remain independent. The `core` group stays enabled;
`dev_tools`, `browser`, and `agents` require explicit configuration. Declaring an
API in template metadata does not enable its server policy.

---

## Registered Commands

There is one mechanism for named commands: functions registered in the template's server. `template.yaml` has no `custom_commands` key (the client rejects it). Register Python functions with the decorator in `commands.py`:

```python
from agent_sandbox.server import command, start

@command("demo", description="Echo the arguments.")
def demo(x: int, y: str) -> str:
    return f"{y}={x}"

if __name__ == "__main__":
    start(9000)
```

File upload and download are server endpoints (`/files/*`, `/upload`, `/download`) of the `file_ops` group, which is on by default. They are not registered from `commands.py`. Deploy does not apply a `server:` block. Turn an opt-in group on with `default_table().enable_group(CapabilityGroup.DEV_TOOLS)` (a `CapabilityGroup`, not a string) or `ABX_SERVER_ENABLED_GROUPS`. `dev_tools`, `browser`, and `agents` start disabled.

Registered commands are served by the in-sandbox HTTP server (`POST /commands/{name}`). Clients call them with `await sandbox.run("demo", x=1, y="hello")` or `abx run <id> demo --arg x=1 --arg y=hello`, and list them with `sandbox.list_commands()` or `abx sandbox command list <id>`. A bare shell command is a different call: `sandbox.commands.run(cmd)`.

---

## Dockerfile Customization

The `Dockerfile` in the template directory is the image when one is present. `template.yaml` does not install packages. `base` is valid source metadata, but is not an instruction to rewrite `FROM`. Retired manifest package-install fields are rejected; dependencies belong in the effective Dockerfile and native dependency files.

Keep the source Dockerfile unchanged. Resolve base-image placeholders in the source or explicitly select a build configuration; never silently substitute another image based on the provider. The valid `base` metadata field does not replace Dockerfile `FROM`.

## Provider template profile

The server does not select a provider. Port 9000 is the application HTTP listen default; injected envd, interpreter services and reserved ports belong to each backend. Those differences do not imply the application is unusable. A declared `start_cmd` runs once; without it, the image or managed template owns startup. Do not run native startup and a start command twice; actually check a nonempty `ready_cmd`. Build configurations are explicit, and the effective Dockerfile/arguments participate in input identity.

`commands.py` imports only `agent_sandbox.server` and calls `start(port)` from its
main entry; the image explicitly installs the server SDK. For the provider-native
application API in the published 0.3.1a1 alpha, import `ProviderSandbox` from
`agent_sandbox` and connect with `await ProviderSandbox.connect(ID)`. This instance
supports `async with await sandbox.application_client(9000, token=application_token)`;
the standard `Sandbox`/`AsyncSandbox` classes have a different interface.
Application endpoint resolution preserves proxy prefixes and separates gateway and
application credentials. See the [complete connection/close example](template-server-api.md#reaching-the-sandbox);
the sandbox creator owns its final deletion.

---

## Publishing and Deploying Templates

The Python SDK is the runtime client and does not build or deploy templates. Build, push and register a template with the CLI: `abx template build` and `abx template deploy` (or `abx deploy`). See [Build & Deploy](build-and-deploy.md).

To publish a template to GitHub, install one locally or from a registry, adopt an existing project (`abx template scaffold --adopt`), or build and register one from the command line (`abx deploy`, `abx template deploy|create`), use the `abx` CLI; see [Related: the abx CLI](#related-the-abx-cli).

## Next Steps

- [Using Templates](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md) — Install and use templates
- [template.yaml Spec](../reference/template-yaml-spec.md) — Precise definitions for all fields
- [Declarative Usage](declarative-usage.md) — The @sandbox decorator

---

## Related: the abx CLI

The command-line workflow for templates is documented in the CLI repository: [Authoring Templates (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) (`abx template scaffold`, `--adopt`, publishing, `template install`), [Deploy & Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md) (`abx deploy`, `abx template deploy|create`) and [Using Templates](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md).
