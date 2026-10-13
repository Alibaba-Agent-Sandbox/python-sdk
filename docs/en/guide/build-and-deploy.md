# Build and Deploy

The Python SDK (`agent-sandbox`) is the **runtime** client. It creates, uses and kills sandboxes. It does not build images or register templates. Building and deploying a template is the job of the `abx` CLI.

| Step | Command | Notes |
|------|---------|-------|
| Author | `abx template init` | Writes `Dockerfile`, `template.yaml`, `commands.py` |
| Build | `abx template build` | `docker build` the template directory |
| Publish | `abx template deploy` (or `abx deploy`) | Build, push to Alibaba Cloud ACR, register the template, wait until it is ready |
| Launch | `abx create --template <TEMPLATE_ID>` or `Sandbox.create(template=...)` | Runtime; this is where the SDK starts |

The full workflow, every option and the AI-assisted authoring steps are documented in the CLI's [Deploy and Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md) guide.

## Using the result from Python

```python
from agent_sandbox import Sandbox

async with await Sandbox.create(template="<TEMPLATE_ID or alias>") as sandbox:
    print(await sandbox.run("hello", name="Ada"))      # a command registered in the template's server
    proc = await sandbox.commands.run("python3 --version")
```

Templates that ship an `agent-sandbox-server` are described in [Authoring Templates](authoring-templates.md) and [Template server HTTP API](template-server-api.md).

## What changed

The earlier SDK carried its own copy of the build pipeline (`Sandbox.deploy`, `Image`, `DockerBuilder`, `TemplateManager`, the `[alicloud]` extra, and the E7xxx build errors). They are removed: one pipeline in one tool. If your code called them, replace the call with the CLI commands above (a script can run `abx template deploy --yes`).

## Next Steps

- [Authoring Templates](authoring-templates.md) — Define templates via template.yaml
- [SDK Usage Guide](sdk-usage.md) — Runtime usage of the SDK

## Related: the abx CLI

The command-line template lifecycle is documented in the [`cli` repository](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md).
