# Adopt Agent Sandbox on an existing Express account

This changes your client/tooling, not your cloud provider. Keep your account, region,
Team, API key, template IDs/aliases, Volumes and RAM roles. Existing resources do not
need to be recreated just to use the client. Review the native API calls your application actually uses.

This guide covers Python and the CLI. The public
[Node SDK](https://github.com/Alibaba-Agent-Sandbox/nodejs-sdk/blob/main/README.md)
currently provides `ServerClient` and configuration names, not cloud sandbox lifecycle.
Changing an E2B JavaScript import to that package is not a supported migration.

This page adopts the explicit native ProviderSandbox extensions and their ABX configuration. For the standard sync/async E2B-compatible root entries and import-only supported migration, read the [standard migration guide](migrate-from-e2b.md). Existing backend/runtime restrictions still apply.

## What changes

| Existing Express application | Agent Sandbox client |
| --- | --- |
| `from e2b import Sandbox` | `from agent_sandbox import ProviderSandbox as Sandbox` |
| Implicit `E2B_API_KEY`, `E2B_API_URL`, `E2B_DOMAIN` | Explicit `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL`, `ABX_SANDBOX_DOMAIN`; old names are not silently read. |
| `Sandbox.kill(id)` | `Sandbox.kill_by_id(id)` |
| `sandbox.get_host(port)` | `sandbox.network.get_host(port)` |
| Signed upload/download URL assumptions | Use authenticated file methods; see [E2B migration differences](migrate-from-e2b.md). |
| Existing API/result/error handling | Audit methods, streaming, exceptions and sync/async behavior; matching method names are not full compatibility. |

For a shell already configured for the **same Express account**, explicitly map
only the selected settings without printing their values:

```sh
export ABX_SANDBOX_API_KEY="$E2B_API_KEY"  # example: use the existing Express value
export ABX_SANDBOX_BASE_URL="$E2B_API_URL"
export ABX_SANDBOX_DOMAIN="$E2B_DOMAIN"
```

Do not use shell tracing or copy this mapping from a native E2B account. Use the
existing template ID/alias and the original regional endpoints. No AK/SK is needed
for ordinary sandbox-key lifecycle, exec and file calls. Cloud management/template
publication has separate AK/SK and registry prerequisites. Use the canonical `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` arguments.

## Verify a new, test-owned sandbox

After installing a compatible client/server release using the
[installation guide](getting-started.md), use an existing template:

```python
import asyncio
import os
from agent_sandbox import ProviderSandbox as Sandbox

async def main():
    sandbox = await Sandbox.create(
        provider="alicloud-express",
        template=os.environ["EXISTING_TEMPLATE_ID"],
        timeout=300,
    )
    try:
        result = await sandbox.commands.run("printf migration-ok")
        assert result.exit_code == 0 and result.stdout == "migration-ok"
    finally:
        await sandbox.kill()  # only the sandbox this example created

asyncio.run(main())
```

To inspect an existing live sandbox, connect with its ID and same-Team key. Do not
add it to an automatic deletion ledger merely because you connected to it. Preserve
its timeout and workload unless the owner explicitly authorizes changes.

Ordinary native lifecycle/exec/files do not require installing this project's
port-9000 server into an existing image. Project named commands, agents routes and
their template capabilities are additional runtime requirements; an arbitrary
pre-existing template need not provide them. Provider plugins and management APIs
also need the compatible Node engine, unlike the native Express lifecycle path.

## Limits, evidence and upgrades

Create-time `volume_mounts={"/mnt/workspace": "existing-volume-name"}` reuses
same-Team Volume metadata and its storage role. It does not provision storage or
prove permissions. The [recorded real OSS run](../../../.agents/evidence/verify/2026-10-16-provider-volume-live.md)
passed mount/read/write, sandbox recreation and owned-resource cleanup for its
tested base template/region. It is not evidence of all Express capabilities.
Domain management, dynamic mount/attach, STS management tokens, newer JuiceFS fields
and real `volume.update` state transitions remain unsupported or unverified as
documented by the [shared host matrix](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/design/alicloud-provider-commands.md).

External plugins update from their recorded source. The bundled provider follows
the SDK release: `python -m agent_sandbox.providers --json update alicloud-express --check`
returns `bundled` and guidance, not a latest-version check or a software update.
Upgrade matching client/server versions with your original install method; upgrade
abx separately for Node management. Restart only engines you own. The host's
[ownership/update design](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/c5a6a3c75921cfb4359f1c23041ec847ce63c932/docs/en/design/provider-portability-and-updates.md)
defines consent, pinning, rollback and the pending template-adapter work.
