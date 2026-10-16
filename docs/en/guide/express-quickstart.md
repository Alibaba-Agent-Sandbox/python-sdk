# Express quickstart

Verified 2026-10-15 on Alibaba Cloud Express (`alicloud-express`) with `agent-sandbox-client` 0.3.0. The template is generation 2. Its start command runs `agent-sandbox-server`.

## Deploy

```bash
abx template scaffold --template python --name hello-x
cd hello-x
abx template deploy . -y --generation 2 \
  --start-cmd 'agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py' \
  --ready-cmd 'agent-sandbox-server healthcheck --port 9000'
```

The python scaffold registers `hello(name="World")`, which returns `Hello, {name}!`. Copy the template id from the deploy output.

`--start-cmd` and `--ready-cmd` require `--generation 2`. If a generation-1 template already uses the name, delete it first (`abx template delete <id> -y`). If deploy reports `base must be a mapping`, set `template.yaml` to:

```yaml
base:
  image: "fc-e2b-registry.cn-hangzhou.cr.aliyuncs.com/runtime/base:v0.0.49"
```

Use your region and the current runtime base tag in place of those two values.

## Call it

```python
import asyncio

from agent_sandbox import ProviderSandbox as Sandbox

TEMPLATE = "<template-id>"


async def main() -> None:
    sb = await Sandbox.create(template=TEMPLATE, timeout=300)
    try:
        echoed = await sb.commands.run("echo hi")
        assert echoed.stdout == "hi\n" and echoed.exit_code == 0
        assert await sb.run("hello", name="Bob") == "Hello, Bob!"
        url = sb.network.get_url(9000)
        headers = sb.network.get_access_headers()
        # GET {url}/health with headers. /health answers 200.
    finally:
        await sb.kill()


asyncio.run(main())
```

`sandbox.run` does not send the sandbox access token. `get_access_headers()` is `X-Access-Token` for the platform gateway.

Generation 1 still supports `commands.run` and `files` (verified the same day on the platform template `base`, envd 0.5.2). The image entrypoint is fixed, so a generation-1 template cannot start `agent-sandbox-server` itself. Named commands need the generation-2 start and ready commands above.

## Clean up

`sb.kill()` removes the sandbox. Delete the template when you are done:

```bash
abx template delete <template-id> -y
```
