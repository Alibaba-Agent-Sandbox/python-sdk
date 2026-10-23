# Alibaba Cloud Agent Sandbox, container edition

Container edition is the OpenKruise Agents sandbox-manager on ACS or ACK. It is a separate provider from Express, with its own domain, credentials and runtime setup. The CLI and Python `ProviderSandbox` use the [catalog adapter](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container) through the local engine. The Node.js server HTTP client does not manage this provider. [中文](../../zh/design/provider-alicloud-container.md).

Install with `abx provider install alibaba-agent-sandbox/awesome-providers//alicloud-container --allow-unpinned --yes`, or `python -m agent_sandbox.providers install registry:alicloud-container --yes`. Pin a reviewed complete commit for reproducible use.

## Exact interpreter boundary

The adapter implements only persistent `code.default-context.execute`, using Jupyter `POST /execute` on port 49999 with `code`, `language` and optional `env_vars`, then reading buffered NDJSON. This is an explicit adapter path, not the removed inferred envd Connect interpreter RPC. Select `mode="default-context"` explicitly.

Stateless execution, public context management, realtime callbacks and structured-result support are not declared. Context IDs and callbacks fail before code is sent. The adapter never falls back to shell when a runtime or route is missing. A template's Python service does not require this interpreter operation unless the selected workflow actually uses it.

## Configure and create

| Setting | Environment |
| --- | --- |
| Domain | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| Optional API origin | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| Provider key, header `X-API-Key` | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| `native` or `private` | `ABX_ALICLOUD_CONTAINER_PROTOCOL`, default `native` |

Native API addressing is `https://api.{domain}` with port hosts `https://{port}-{id}.{domain}`. Private API addressing is `https://{domain}/kruise/api`; the envd binding uses `https://{domain}/kruise/{id}/49983` and the Jupyter handler selects port 49999. Express keys are not inherited.

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(
    provider="alicloud-container",
    template="YOUR_NATIVE_SANDBOXSET",
    provider_options={
        "domain": "sbx.example.com",
        "api_key": "REPLACE_ME",
        "protocol": "native",
    },
)
try:
    result = await sandbox.run_code("print(42)", mode="default-context")
finally:
    await sandbox.kill()
```

The manifest declares lifecycle/timeout/pause/resume, exec, process management, files and ports independently. The exact operation lists determine workflow support. PTY, file watch/transfer, template inventory, storage mounts, VPC and named-command service availability are not inferred from these groups. Named-command application workflows require an actual matching HTTP service and binding.

## Source preparation and evidence

CLI preparation builds and pushes an explicit compatible source/profile, then clones a configured base SandboxSet's runtime injection, volumes and probes into an owned zero-pool resource. It does not modify the base object or rewrite Dockerfile instructions. This requires Docker/registry access and Kubernetes permissions; an ordinary sandbox-manager key alone cannot register SandboxSets. Python consumes prepared references and does not declare `template.prepare`.

Container edition remains Beta. Local fake-API tests exercise adapter mapping and refusal behavior. A real create requires an ACS/ACK deployment, a valid native SandboxSet, domain/key and runtime services. No native acceptance was completed in this environment. Source registration, application HTTP and interpreter evidence have different scopes; successful mocks or historical receipts do not certify the current workflow.
