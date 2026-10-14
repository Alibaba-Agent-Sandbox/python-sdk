# Alibaba Cloud Agent Sandbox, container edition

> Status: current. This is not Express (`alicloud-express`). The source is `awesome-providers/alicloud-container`. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//alicloud-container --allow-unpinned --yes` (or `python -m agent_sandbox.providers install registry:alicloud-container --yes`). The manifest is `kind = "node"`: the Node.js host loads `provider.mjs`, so the CLI and, through the local engine, every SDK can use it. Its own notes are `awesome-providers/alicloud-container/docs/README.md`.

Container edition is the OpenKruise Agents sandbox-manager on ACS or ACK. It speaks E2B-shaped HTTP. It is not the Express hosted endpoint.

```python
sb = await Sandbox.create(
    provider="alicloud-container",
    template="code-interpreter",
    provider_options={
        "domain": "sbx.example.com",
        "api_key": "...",
        "protocol": "native",
    },
)
```

| Setting | Environment |
|---|---|
| Domain | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| API origin, optional | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| API key, header `X-API-Key` | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| `native` or `private` | `ABX_ALICLOUD_CONTAINER_PROTOCOL`, default `native` |

Native API is `https://api.{domain}` and the data plane is `https://{port}-{id}.{domain}`. Private API is `https://{domain}/kruise/api` and the data plane is `https://{domain}/kruise/{id}/49983`. `ABX_SANDBOX_API_KEY` is not read.

Declared: `sandbox.lifecycle`, `sandbox.timeout`, `sandbox.pause`, `exec.run`, `exec.stream`, `process.manage`, `files.rw`, `code.interpret`, `ports.url`. `pty` is not declared: sandbox-manager has no `/terminal`.

`E8004`: pause, file watch, file URLs, templates, storage mounts, VPC, named commands. The product docs also leave presigned uploads, logs, metrics, and volumes outside the container edition's E2B surface.

The unit test uses a local fake API. `e2e/test_08_providers.py` creates a real sandbox when `ABX_ALICLOUD_CONTAINER_DOMAIN` and `ABX_ALICLOUD_CONTAINER_API_KEY` are set. Without them it only checks that create refuses before any request, and it does not send the Express key. This environment has no ACS/ACK cluster, so that live create did not run. Chinese: [provider-alicloud-container.md](../../zh/design/provider-alicloud-container.md).
