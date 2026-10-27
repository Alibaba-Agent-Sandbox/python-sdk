# Express features and permissions

The shared provider implementation and complete task-to-RAM-Action/resource policy tables are maintained in the [CLI permissions guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/permissions.md). It includes API-key preparation/reuse/renewal, Team/template/Volume/Quota/Template Cache operations, ACR, storage execution roles and administrator policy steps.

Existing API-key users need no additional AccessKey. Explicit keys always win. AK/SK-only SDK calls resolve a previously prepared key; they never interactively prompt or silently create/renew a credential. Install a matching `abx` CLI (or set `ABX_BIN`) for this optional AK/SK path. Direct API-key SDK use does not need the CLI.

Grant `sandbox:CreateApiKey`, `sandbox:DescribeApiKey` and `sandbox:UpdateApiKey` on `acs:sandbox:<region>:<account-id>:teams/<team-id>/apikeys/*`, then explicitly authorize preparation:

```python
from agent_sandbox.providers.alicloud_express import prepare_api_key_sync
from agent_sandbox import Sandbox

prepare_api_key_sync(confirm=True)  # creates/renews a private 30-day managed key
sandbox = Sandbox.create(template="base")
try:
    print(sandbox.commands.run("echo ready").stdout)
finally:
    sandbox.kill()
```

Async code uses `await prepare_api_key(confirm=True)` and may then use `AsyncSandbox` or `ProviderSandbox`. Default `confirm=False` rejects before engine/cloud I/O. Preparation returns metadata, never plaintext. Reuse checks cloud status. Near-expiry keys need fresh explicit preparation; already constructed clients do not renew in the background. Disabling or deleting a key is respected. The engine owns expiry and shared private storage, with no duplicated cloud SDK in Python.

The optional `team_id=` selector must match subsequent engine selection. For persistent selection use `abx config set team_id <TEAM_ID>` so CLI and SDK share the same context; otherwise both use the API's default Team. In CI, `abx --ci sandbox list --format json` explicitly authorizes preparation before starting the SDK application. See the owner guide for recovery after uncertain writes and exact cleanup permissions.
