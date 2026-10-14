# Authoring Templates

> **Note:** The `abx` commands shown on this page are provided by the Node.js CLI in the `cli` repository (`npm install -g @agent-sandbox/cli`). CLI-specific documentation (CLI design, tutorial, reference) lives there too; this repository documents the Python SDK (`agent-sandbox`) and the container-side runtime (`agent-sandbox-server`).

This is the **Server SDK**: `commands.py` starts with the image and serves HTTP inside the sandbox. Creating and calling a sandbox from your machine is the [Client SDK](client-sdk.md).

This document explains how to create custom Agent Sandbox templates, including directory structure, field reference, capability declarations, registered commands, and publishing.

A template is a directory of plain files, written by hand or generated. The `abx template init` command generates one three ways (built-in scaffold, a one-sentence description, or adopting a project that already has source code); that workflow is documented in the CLI repository: [Authoring Templates (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md).

---

## Template Directory Structure

A complete template directory structure is as follows:

```text
my-template/
├── template.yaml      # Required — template definition
├── Dockerfile         # Optional — custom Docker build (takes priority over build steps in template.yaml)
├── commands.py        # Optional — register commands via @sandbox.register
└── README.md          # Optional — template description
```

`template.yaml` is the only required file.

---

## template.yaml Basic Example

```yaml
name: my-python-template
version: "1.0.0"
description: "Python data analysis environment with pre-installed pandas and matplotlib"
author: "Your Name"
tags:
  - python
  - data-analysis

env:
  PYTHONUNBUFFERED: "1"
  APP_DIR: "/app"

capabilities:
  - shell
  - files
  - code
  - terminal

ports:
  - 8080
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
| `capabilities` | `list[str]` | ❌ | `None` | Capability declarations (see below) |

For detailed field definitions, see [template.yaml Spec](../reference/template-yaml-spec.md).

---

## Capability Declarations

Declare the runtime capabilities supported by the template via the `capabilities` field:

```yaml
capabilities:
  - shell      # Shell command execution
  - files      # Filesystem operations
  - code       # Code Interpreter
  - terminal   # PTY terminal
  - ports      # Port network access
```

**Standard capability set**: `shell`, `files`, `code`, `terminal`, `ports`

**Default capability set** (when `capabilities` is not declared): `shell`, `files`, `code`

`terminal` and `ports` must be explicitly declared in the template to be used. Capability tokens are used at the template resolution layer (`resolve_capabilities()`) which is fail-closed: if a template’s YAML is malformed or missing, the resolver raises `TemplateParseError` (E2004) rather than silently granting capabilities. All API methods remain callable regardless of declared capabilities; capability declarations serve as metadata for template validation and model inference.

The process started by `commands.py` serves a fixed HTTP API on port 9000. The Dockerfile base image varies by template; the routes do not. The server registers nine capability groups. `core` stays on. `dev_tools`, `browser`, and `agents` start disabled. The `agents` routes are registered and stay off until `ABX_SERVER_ENABLED_GROUPS` includes `agents`. The routes each group turns on, and how to call them, are in [Template server HTTP API](template-server-api.md).

---

## Registered Commands

There is one mechanism for named commands: functions registered in the template's server. `template.yaml` has no `custom_commands` key (the client rejects it). Register Python functions with the decorator in `commands.py`:

```python
from agent_sandbox.declarative import sandbox

@sandbox.register
def demo(x: int, y: str) -> str:
    return f"{y}={x}"
```

File upload and download are server endpoints (`/files/*`, `/upload`, `/download`) of the `file_ops` group, which is on by default. They are not registered from `commands.py`; turn a group on or off with `server.groups` in `template.yaml`.

Registered commands are served by the in-sandbox HTTP server (`POST /commands/{name}`). Clients call them with `await sandbox.run("demo", x=1, y="hello")` or `abx run <id> demo --arg x=1 --arg y=hello`, and list them with `sandbox.list_commands()` or `abx command list <id>`. A bare shell command is a different call: `sandbox.commands.run(cmd)`.

---

## Dockerfile Customization

The actual build process uses `Dockerfile` directly along with language-native dependency files (`requirements.txt` / `package.json`):

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    curl git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    pandas matplotlib numpy

WORKDIR /app

ENV PYTHONUNBUFFERED=1
```

The `Dockerfile` in the template directory is the sole source for building images. `template.yaml` only defines runtime configuration (capabilities, commands, environment variables, resources) and does not contain build instructions.

## Provider template profile

The server SDK does not select a sandbox provider, and `agent_sandbox.server` does not import one. Port 9000 stays the server listen default. The FC reserved ports (49983, 5000, 49999) are the `alicloud-express` template profile, not properties of the HTTP API.

The CLI owns the image contract. It resolves the provider with `--provider` / `ABX_PROVIDER` / the default `alicloud-express`, then renders that one profile into the Dockerfile and the template prompt:

- `alicloud-express`: `FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>`, no `CMD` or `ENTRYPOINT`, platform `start_cmd` / `ready_cmd`, user `user`, workdir `/home/user/app`.
- Every other provider: the generic profile (`FROM python:3.12-slim`, `CMD ["python3", "commands.py"]`, `WORKDIR /app`, image-default user) unless the plugin declares `[template]` in `abx-provider.toml`. A missing profile is announced and is not the FC image.

`template.yaml` records the same defaults as `user` and `workdir`. The Dockerfile `WORKDIR` matches `workdir`. `USER` is written only when `user` is non-empty, because `python:3.12-slim` has no `user` account. A later command can pass its own working directory; these two fields are the sandbox default, the same idea as E2B's template user and workdir.

`commands.py` imports only `agent_sandbox.server` and calls `serve(port=9000)` under `if __name__ == "__main__"`. The image installs `agent-sandbox-server`.

---

## Publishing and Deploying Templates

The Python SDK is the runtime client and does not build or deploy templates. Build, push and register a template with the CLI: `abx template build` and `abx template deploy` (or `abx deploy`). See [Build & Deploy](build-and-deploy.md).

To publish a template to GitHub, install one locally or from a registry, adopt an existing project (`abx template init --adopt`), or build and register one from the command line (`abx deploy`, `abx template deploy|create`), use the `abx` CLI; see [Related: the abx CLI](#related-the-abx-cli).

## Next Steps

- [Using Templates](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md) — Install and use templates
- [template.yaml Spec](../reference/template-yaml-spec.md) — Precise definitions for all fields
- [Declarative Usage](declarative-usage.md) — The @sandbox decorator

---

## Related: the abx CLI

The command-line workflow for templates is documented in the CLI repository: [Authoring Templates (CLI)](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) (`abx template init`, `--adopt`, publishing, `template install`), [Deploy & Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md) (`abx deploy`, `abx template deploy|create`) and [Using Templates](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md).
