# Verification: released SDK and public catalog base manifest

- Date: 2026-10-25
- Result: PASS — one owned sandbox, expected output, independently confirmed absence.
- SDK: public PyPI client/server 0.4.0a1, freshly installed outside the source checkout.
- Catalog: <https://registry.agent-sandbox.cn/catalog.json>, schema 3.
- TTL requested: 300 seconds.

## Input and boundary

The catalog response identified templates `45eb6c4`, CLI `408e618`, Python SDK
`11e7e93`, providers `48f0910`, Node SDK `f473f7d` and Registry `7986493`. Its fetched
bytes had SHA-256 `ffd21eb7058f35137fed1125dae4268a360e5d2ebc427fa78c2021baa9c297ac`.
The base entry's published manifest digest was
`sha256:8fcb10e223a4e592d3f4fa44069dcc966eeb91799cd768ce106470368f7acdd9`.

The test selected the public catalog's `base` entry for `alicloud-express` and passed
its complete `manifest` mapping unchanged to `launch_template`. That manifest declares
specification 5, `template_id: base` and an empty `provides` map. No local substitute,
source checkout, manifest override or catalog cache was used.

An earlier local invocation of `launch_template('base', ...)` returned
`FileNotFoundError` for `base` before creating any resource. This was an incorrect
test assumption: Python's documented string input is a local YAML path; bare-name
catalog resolution belongs to the CLI. The corrected experiment explicitly resolves
the public catalog manifest before calling Python. This observation is retained as
an input-contract boundary, not classified as a product defect or a successful cloud test.
No new registry resolver or patch release was introduced.

## Result

Elapsed times below start immediately before launch, after fetching the catalog:

| Operation | Elapsed | Result |
| --- | --- | --- |
| `launch_template(manifest, provider='alicloud-express', timeout=300)` | 1.070 s | PASS; zero declared application services, as specified by base. |
| `session.sandbox.commands.run('printf 42', timeout=30)` | 1.463 s | PASS; exit 0, stdout exactly `42`. |
| `session.close()` in `finally` | 1.647 s | PASS. |
| Independent `ProviderSandbox.get_info_by_id` | 1.984 s | PASS; `SandboxNotFoundError` confirms owned resource absent. |

The complete scenario took 2.049 seconds. The run journal ended with
`cleanup-intent`, `deleted`, `cleanup-complete`. Only one sandbox was created;
no full CLI acceptance suite or template matrix was rerun. No interpreter API,
application health/discovery or arbitrary service behavior is claimed by this
base shell-operation check.

## Reproduce

Use the exact public installation from the
[release record](2026-10-25-python-040a1-public-release.md) and configure the Express
account through `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN`.
Then run outside the source checkout:

```python
import asyncio
import json
import urllib.request

from agent_sandbox import ProviderSandbox
from agent_sandbox.api import launch_template
from agent_sandbox.models.errors import SandboxNotFoundError

with urllib.request.urlopen("https://registry.agent-sandbox.cn/catalog.json") as response:
    catalog = json.load(response)
assert catalog["schema"] == 3
entry = next(row for row in catalog["templates"]
             if row["name"] == "base" and row.get("native_provider") == "alicloud-express")
manifest = entry["manifest"]
assert manifest["spec_version"] == 5

async def main():
    session = await launch_template(manifest, provider="alicloud-express", timeout=300)
    sandbox_id = session.sandbox.id
    try:
        result = await session.sandbox.commands.run("printf 42", timeout=30)
        assert result.exit_code == 0 and result.stdout == "42"
    finally:
        await session.close()
        try:
            await ProviderSandbox.get_info_by_id(sandbox_id, provider="alicloud-express")
        except SandboxNotFoundError:
            pass
        else:
            raise AssertionError("Owned sandbox still exists")

asyncio.run(main())
```

The public catalog can advance; record its revision metadata and response digest
when reproducing. The earlier CLI diagnostic limitation remains independently
tracked in https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/109. This
narrow success does not erase that historical result.
