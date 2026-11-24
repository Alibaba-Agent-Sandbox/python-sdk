# Alibaba Cloud Agent Sandbox, container edition

Container Edition runs sandbox-manager on an ACS or ACK cluster. Use the Python Client SDK source version that includes the built-in `alicloud-container` Provider. Python calls the cluster directly. The CLI uses its own [Node Provider](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container) for operations such as SandboxSet preparation. [中文](../../zh/design/provider-alicloud-container.md)

## Install the Client SDK

From a checkout containing the built-in Container Edition Provider, run `python -m pip install ./client-sdk`. PyPI `0.4.0a7` predates this Provider.

## Connect to the cluster

Set the cluster's sandbox-manager key and at least one of the domain or management URL. Use an existing SandboxSet from the same cluster.

| Setting | Environment |
| --- | --- |
| Cluster gateway domain | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| Explicit management API URL | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| Cluster sandbox-manager API key | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| Gateway routing | `ABX_ALICLOUD_CONTAINER_PROTOCOL`, defaults to `native`, or `private` |

With `native` routing, the default management URL is `https://api.{domain}` and sandbox ports use `https://{port}-{id}.{domain}`. With `private` routing, the default management URL is `https://{domain}/kruise/api` and sandbox ports use the `/kruise/{id}/{port}` path. An explicit private management URL must end in `/kruise/api`. Its origin and any preceding path prefix also apply to the data plane. The management key goes to the cluster API. The session supplies credentials for the sandbox gateway and envd.

```python
import asyncio

from agent_sandbox import ProviderSandbox


async def main():
    sandbox = await ProviderSandbox.create(
        provider="alicloud-container",
        template="base",  # Use an existing SandboxSet name from the cluster.
    )
    try:
        result = await sandbox.commands.run("printf container")
        print(result.stdout)
        await sandbox.files.write("/tmp/container-demo.txt", result.stdout)
        print(await sandbox.files.read("/tmp/container-demo.txt"))
    finally:
        await sandbox.kill()


asyncio.run(main())
```

## Run Python in an existing interpreter context

For a SandboxSet with the Jupyter service on port `49999`, use this call inside the sandbox's `try` block. The default context persists across calls. `run_code` buffers the service output and returns an execution result.

```python
result = await sandbox.run_code("print(42)", mode="default-context")
print(result.stdout)
```

## Bind an explicit cluster target

Use [`ProviderClient`](../guide/provider-runtime.md) when a service should supply its own cluster configuration. Set `ProviderLock(provider="alicloud-container", version=...)` to the installed `agent-sandbox-client` version. Pass `api_key`, `domain` or `base_url`, and, if needed, `protocol` in `TransportConfig.provider_options`. A matching built-in Provider is selected by that lock.

## Capabilities

The client operates existing SandboxSets. It supports lifecycle, lease updates, commands and streaming, process operations, file operations, and gateway port addresses. Pause and resume depend on the cluster. `connect()` can resume a sandbox or extend its lease. `close()` releases local connections, and `kill()` deletes the sandbox. Listing returns one page of 1–100 entries and accepts the `running` and `paused` filters.

The adapter has no support for separate interpreter contexts, real-time interpreter callbacks, PTY, file watching, per-instance compute overrides, or volume and network configuration. See the [Alibaba Cloud setup guide](https://help.aliyun.com/zh/agent-sandbox/quick-start1/) for creating or modifying a SandboxSet. The built-in Python Provider is in preview.
