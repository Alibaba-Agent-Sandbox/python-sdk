# Alibaba Cloud Agent Sandbox, container edition

Container Edition runs sandbox-manager on an ACS or ACK cluster. Use the Python Client SDK source version that includes the built-in `alicloud-container` Provider. Python calls the cluster directly. The CLI uses its own [Node Provider](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container) for operations such as SandboxSet preparation. [中文](../../zh/design/provider-alicloud-container.md)

## Exact interpreter boundary

The adapter implements only persistent `code.default-context.execute`, using Jupyter `POST /execute` on port 49999 with `code`, `language` and optional `env_vars`, then reading buffered NDJSON. This is an explicit adapter path, not the removed inferred envd Connect interpreter RPC. Select `mode="default-context"` explicitly.

Stateless execution, public context management, realtime callbacks and structured-result support are not declared. Context IDs and callbacks fail before code is sent. The adapter never falls back to shell when a runtime or route is missing. A template's Python service does not require this interpreter operation unless the selected workflow actually uses it.

## Configure and create

| Setting | Environment |
| --- | --- |
| Domain | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| Optional management API URL | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| Provider key, header `X-API-Key` | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| `native` or `private` | `ABX_ALICLOUD_CONTAINER_PROTOCOL`, default `native` |

Native API addressing is `https://api.{domain}` with port hosts `https://{port}-{id}.{domain}`. Private API addressing is `https://{domain}/kruise/api`; the envd binding uses `https://{domain}/kruise/{id}/49983` and the Jupyter handler selects port 49999. For private routing, an explicit management URL must end in `/kruise/api`. The SDK uses its origin and prefix for the data plane. The key comes from the cluster's sandbox-manager and is only sent to the control plane. Gateway and envd access tokens are obtained from the sandbox session.

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.create(
        provider="alicloud-container",
        template="code-interpreter",  # Use an existing SandboxSet name from the cluster.
    )
    try:
        result = await sandbox.commands.run("printf container")
        print(result.stdout)
        code = await sandbox.run_code("print(42)", mode="default-context")
        print(code.stdout)
    finally:
        await sandbox.kill()


asyncio.run(main())
```

Use an existing SandboxSet name as `template`. The SDK supports lifecycle, timeout, pause and resume where configured, commands, process operations, files and gateway addresses. `connect()` can resume a paused sandbox or extend its lease. `close()` releases local connections and `kill()` deletes the sandbox. Listing accepts a limit of 1–100 and the `running` and `paused` filters. Offset pagination, per-create compute overrides, interactive PTY, file watching, and volume/network configuration are outside this adapter's scope.

Creating or modifying a SandboxSet requires cluster permissions. See the [container setup guide](https://help.aliyun.com/zh/agent-sandbox/quick-start1/). The built-in Python adapter remains in preview.
