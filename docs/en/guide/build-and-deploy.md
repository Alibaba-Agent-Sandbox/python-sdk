# Build and Deploy

The Python SDK (`agent-sandbox-client`) is the **runtime** client. It creates, uses and kills sandboxes. It does not build images or register templates. Building and deploying a template is the job of the `abx` CLI.

| Step | Command | Notes |
|------|---------|-------|
| Author | `abx template scaffold` | Writes `Dockerfile`, `template.yaml`, `commands.py` |
| Build | `abx template build` | Build the selected Dockerfile or explicit cloud steps |
| Publish | `abx template deploy` (or `abx deploy`) | Publish the selected build path; check the returned status before creating |
| Launch | `abx create <TEMPLATE_ID>` or `Sandbox.create(template=...)` | Runtime; this is where the SDK starts |

The full workflow, every option and the AI-assisted authoring steps are documented in the CLI's [Deploy and Build](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/guide/deploy-and-build.md) guide.

## Cloud steps and readiness

Dockerfile deployment requires local Docker and the configured image registry.
`abx template deploy --build steps` uses explicit steps in `template.yaml` and
requires neither local Docker nor an ACR push. It does not translate a Dockerfile
or upload local `COPY` files automatically. For the catalog's `python-hello`, use
[the public steps preparation guide](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/platform-steps.md#quick-start-python-hello-without-docker).

In CLI 0.4.11, a direct steps deployment may return `Status: submitted` and a
`TemplateID`. Submission is not readiness: poll `abx --json template info ID` until
its state is `ready`, with a finite deadline; stop and clean up on failure. That
version returns `status` as a string containing a Python dictionary, so automation
must parse the outer JSON and use `ast.literal_eval` for that string, never `eval`.
Only then call `abx create ID --detach` or `ProviderSandbox.create(template=ID)`.
Retain each exact resource ID for cleanup (`abx kill SANDBOX_ID`, then
`abx template delete TEMPLATE_ID -y`) and verify that subsequent exact-ID reads
report not-found. A successful submit exit or an empty list alone is insufficient.

## Using the result from Python

```python
from agent_sandbox import ProviderSandbox as Sandbox

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
