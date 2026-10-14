# Template notes that do not fit in SKILL.md

The skill file is the procedure. This note is the extra detail.

## What deploy actually reads

`abx template deploy` uses the Dockerfile as the image. From `template.yaml` it
reads `name`, `resources.cpu`, `resources.memory`, and `generation`. Omitted
resources become 2 CPU and 2048 MB. It does not install `python_packages` or
`system_packages`, and it does not apply a `server:` block.

`generation` defaults to 1. On generation 1 a `--start-cmd` you pass is not the
process that runs. The FC profile's platform start command is
`agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py`.
That imports `commands.py`. If `start()` runs at import time, the import hangs
or serves during the import. Keep `start()` under `if __name__ == "__main__"`.

## Groups

`core` cannot be turned off. `commands`, `file_ops`, `process`, `terminal`, and
`system` start enabled. `dev_tools`, `browser`, and `agents` start disabled.

```python
from agent_sandbox.server import CapabilityGroup, ServerPolicy, default_table, start

table = default_table()
table.enable_group(CapabilityGroup.BROWSER)

if __name__ == "__main__":
    start(9000, policy=ServerPolicy.only("agents_sessions_create"))
```

`enable_group` takes a `CapabilityGroup`, not a string. An exact policy rule
also opens an endpoint in an opt-in group. `ABX_SERVER_ENABLED_GROUPS=agents`
is the environment form, and it only enables.

## Calling a named command

```python
await sb.run("hello", name="Ada")
```

```bash
abx run SANDBOX_ID hello --arg name=Ada
abx sandbox command list SANDBOX_ID
```

HTTP body is `{"name":"Ada"}`. Response is `{"result":"Hello, Ada!"}`.

## Platform steps

`--build auto` uses the Dockerfile when one exists. `--build steps`, or `auto`
with no Dockerfile, does not build locally and does not push to ACR. It sends
`base.image` as the image and expands `build:`:

| Key | Sent as |
|---|---|
| `apt_install` | one `RUN` of `apt-get update && apt-get install -y …` |
| `pip_install` | one `RUN` of `pip install --no-cache-dir …` |
| `npm_install` | one `RUN` of `npm install -g …` |
| `env` | one `ENV` per variable |
| `run` | one `RUN` per command |
| `steps` | copied as `{type, args}` |

`steps` requires `base.image`. `COPY` is not generated. A Dockerfile and a
`build:` block together: `auto` builds the Dockerfile and does not send the
steps. For `alicloud-express`, prefer the FC Dockerfile in `SKILL.md`. Do not
point `base.image` at `python:3.12-slim` for that provider.

## Agents API

There is no `sb.agent` and no `abx agent`. The routes are real HTTP on port 9000, and the `agents` group starts disabled.

```python
from agent_sandbox.server import CapabilityGroup, default_table

default_table().enable_group(CapabilityGroup.AGENTS)
```

`ABX_SERVER_ENABLED_GROUPS=agents` is the environment form. A token, when set, is `Authorization: Bearer` (`ABX_SERVER_TOKEN`).

`POST /v1/agents/sessions` with `{"agent": {"model": "codex", "instructions": "..."}}` creates a session. The next call is `POST /v1/agents/sessions/{id}/events`. `GET /v1/agents/runtimes` reports `implemented` and `installed` for each runtime.

Local execution exists for `codex` and `qwen-code`. `claude-code`, `cursor`, and `command` answer `404` with `agents.not_implemented_locally`. Do not remove those routes and do not invent a Python method that hides them.

## Reserved template names

`codex` and `openclaw` are reserved by the platform. The directory can keep
that name. `template.yaml` `name` and `abx template deploy --alias` must be
`openai-codex` or `openclaw-agent`.
