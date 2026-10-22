# template.yaml Specification

This document precisely defines all fields of the `template.yaml` file (from the user's perspective).

---

## File Location

The template's `template.yaml` is located at the root of the template directory:

```text
my-template/
├── template.yaml    ← The file defined in this document
├── Dockerfile       # Optional
└── ...
```

After installation, it resides at `~/.abx/templates/<template-name>/template.yaml`.

---

## Complete Field Definitions

### Basic Information

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | ✅ | — | Template name, used with the `--template` parameter |
| `version` | `str` | ❌ | `"1.0.0"` | Semantic version number |
| `description` | `str` | ❌ | `""` | Template description |
| `author` | `str` | ❌ | `""` | Author |
| `license` | `str` | ❌ | `""` | License identifier (e.g., `"MIT"`) |
| `tags` | `list[str]` | ❌ | `[]` | Classification tags |

### Runtime Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `env` | `dict[str, str]` | ❌ | `{}` | Environment variables (generates `ENV` instructions) |
| `ports` | `list[int]` | ❌ | `[]` | Exposed ports (generates `EXPOSE` instructions) |

### Resource Specifications

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cpu_count` | `int` | ❌ | `None` | Default CPU core count |
| `memory_mb` | `int` | ❌ | `None` | Default memory in MB |

### Sandbox Generation

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `generation` | `int` | ❌ | `1` | Sandbox generation: `1` = first-gen (rund), `2` = second-gen (MicroVM, Beta). When set, CLI commands (`template deploy`, `template build`, `template create`) use this value unless overridden by the `--generation` flag. |

### Capability Declarations

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `capabilities` | `list[str] \| null` | ❌ | `null` | Runtime capability list |

**Allowed values** (standard capabilities `STANDARD_CAPABILITIES`):

| Capability | Description |
|------------|-------------|
| `shell` | Shell command execution (`commands.run()`, etc.) |
| `files` | Filesystem operations (`files.read()`, etc.) |
| `code` | Code Interpreter execution (`run_code()`, etc.) |
| `terminal` | PTY terminal sessions (`get_terminal()`) |
| `ports` | Port URL access (`network.get_url()`, etc.) |

**Behavior rules**:
- `null` (undeclared) → Uses the default capability set `{shell, files, code}`
- Explicit list → Only the listed capabilities are enabled (can be a subset or superset of the standard set)
- Values in the list must be from the standard capability set; otherwise, validation fails (raises `TemplateParseError` E2004)

### Removed key: `custom_commands`

`custom_commands` is not a `template.yaml` key. The client rejects a file that contains it (`TemplateParseError`, E2004). Named commands have one mechanism: functions registered in the template's server (`@sandbox.register` in `commands.py`), called with `sandbox.run(name, **kwargs)` or `abx run <id> <name>`. See [Authoring Templates](../guide/authoring-templates.md#registered-commands).

### Server Policy (`server`)

Optional. Declares which SandboxServer endpoints the template exposes and under which restrictions
(design: [fine-grained-capabilities](../design/fine-grained-capabilities.md)). Absent = the server's default
behaviour. The block is validated structurally by `SandboxTemplate` (unknown keys are errors); values are
validated by `agent-sandbox-server check-config`. Tooling compiles it to `/etc/agent-sandbox/server-policy.json`, which the server
loads automatically.

| Key | Type | Description |
|-----|------|-------------|
| `preset` | `str` | `default`, `transfer-only`, `read-only`, `hardened`, `locked` |
| `base_dir` | `str` | Root for relative paths and the default path boundary |
| `groups` | `list[str]` or `map[str, bool]` | Turn capability groups on (`[agents, dev_tools]`) or on/off (`{process: false}`). A group is an alias for its endpoint ids |
| `defaults` | rule | Rule applied to every endpoint before its own rule |
| `endpoints` | `map[str, rule]` | Per-endpoint rules keyed by endpoint id (`files_download_stream`, `shell`, ...) |
| `auth` | map | `tokens` (`id`, `scopes`, `token_env` or `token_sha256`), `allow_anonymous`, `anonymous_scopes` |

A rule has `enabled`, `scopes`, `paths` (`allow`, `deny`, `read_only`, `symlinks`), `limits` (`max_bytes`, `max_request_bytes`, `timeout_seconds`, `rate_per_minute`, ...), `params` (`overwrite`, `deny_extensions`, `allow_commands`, ...) and `audit`.

```yaml
server:
  preset: transfer-only
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out] }
      limits: { max_bytes: 5MB }
    files_upload_stream:
      paths: { allow: [/home/user/in] }
      params: { overwrite: false }
```

---

## Complete Example

```yaml
name: flask-web
version: "2.0.0"
description: "Flask Web Development Environment"
author: "Agent Sandbox Team"
license: "MIT"
tags:
  - python
  - web
  - flask

env:
  PYTHONUNBUFFERED: "1"
  FLASK_ENV: "development"

ports:
  - 5000
  - 8080

cpu_count: 2
memory_mb: 2048

capabilities:
  - shell
  - files
  - code
  - terminal
  - ports

```

---

## Build Notes

`template.yaml` only defines runtime configuration (capabilities, server policy, environment variables, resources). Image building is entirely handled by the `Dockerfile` in the template directory, using language-native dependency files (`requirements.txt` / `package.json`) for dependency management.
