# Explicit template workflows

Template specification 4 separates the software a template provides from the operations a provider adapter and a particular client implement. An application HTTP server does not require a unified code interpreter. A provider's Beta label describes maturity; it does not certify or reject every workflow.

| Layer | Declares or checks |
| --- | --- |
| Template | `provides`, explicit `workflows`, exactly one `default_workflow`, input and startup mode |
| Provider | Operation contract 1, exact operations per consumer, supported inputs and startup modes |
| SDK/CLI | The actual protocol bridge and caller/network binding for the selected operation |
| Verification | Current content identities, minimum profile checks, cleanup and independently approved CI provenance |

The canonical contract, profiles, receipt schema and shared vectors live in [`contracts`](https://github.com/alibaba-agent-sandbox/python-sdk/tree/main/contracts). Static planning has three states: T means implemented requirements, F means an explicit mismatch or missing adapter/client operation, and U means unresolved information. Any F dominates U. T permits local checks; it is not a successful runtime test. A missing project adapter operation does not prove the platform's native API lacks it.

Runtime old-schema translation is removed. `capabilities`, `tested_on` and hand-written provider compatibility claims are rejected in current manifests. Unknown remote references grant no default code capability. Historical records remain historical.

## Python application consumption

For an existing sandbox, resolve application HTTP separately from its internal provider transport:

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.connect(sandbox_id, provider="opensandbox")
try:
    async with await sandbox.application_client(9000, token=application_token) as client:
        result = await client.commands.run("hello", name="Python")
finally:
    await sandbox.close()  # releases this connection; it did not create the sandbox
```

`application_client` asks the selected provider for this sandbox's port endpoint. Gateway headers and the explicit application bearer token have separate audiences. Control-plane API keys are never copied into an application request. Proxy prefixes and signed base-query bytes are preserved; redirects, URL user information, authority overrides and encoded namespace traversal are refused. Operation-signed endpoint types require a provider operation resolver and must not be treated as a prefix URL.

For a new prepared-image workflow:

```python
from agent_sandbox.api import launch_workflow

async with await launch_workflow(
    "template.yaml", provider="opensandbox", workflow_id="application-image",
    reference=immutable_image_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

The selected manifest must actually declare that workflow. Python does not prepare source projects; use the CLI's explicit build profile first and select an immutable prepared `image` workflow; `managed` launch remains blocked until a provider-resolved immutable identity exists. An external application uses a `service` workflow and explicit application URL. The standalone launcher does not execute application deployment hooks or reinterpret deployment topology.

The launcher freezes manifest inputs, checks the provider's actual code digest, persists intent before create, records owned resource IDs, checks application protocol version before invocation, and deletes only its owned sandbox. An uncertain create is not replayed and remains in a journal for reconciliation using its `abx_workflow_run` metadata. Cleanup failure preserves resource IDs and raises. Journals contain no API keys, application tokens, environment secrets or signed endpoint URLs. A journal alone is not a trusted verification receipt.

## Interpreter operations

`ProviderSandbox.code.run(code)` selects stateless `code.execute`. The provider protocol must implement isolation (a native stateless call or temporary context with guaranteed cleanup). `mode="default-context"` explicitly selects persistent `code.default-context.execute`; `context_id=...` selects `code.context.execute`. Creating, listing, restarting and deleting contexts each require their own operation. Realtime callbacks require `code.stream`; a buffered response is not realtime streaming. Rich structured results have a separate operation.

A missing runtime or interpreter HTTP 404 remains an error. It never writes a temporary script and runs a shell instead. To run a Python script through a shell, explicitly use `files.write()` and `commands.run("python script.py")`. The pinned standard `Sandbox`/`AsyncSandbox` and `code_interpreter` clients keep their independent public contract.

## Verification scope

Profiles bind consumer and workflow kind; the context profile also requires the exact context operations. A template may add `required_checks`, not remove the profile minimum. Required failures, skips, missing checks or changed inputs cannot count as verified. Source/manifest/build/artifact/provider/consumer/workflow/binding/contract identities must match. Submitted PASS JSON and a manually filled runner cannot certify themselves; registry trust requires independently checked approved CI provenance and matching artifacts. Guest HTTP, host HTTP, native SDK and unified Python/CLI are separate scopes.

Current project adapters: Express, E2B and REST do not implement unified interpreter operations; their guessed RPC implementation has been deleted. CubeSandbox and container edition implement only the persistent default-context operation. Platform-native and pinned standard clients are separate. Managed workflow launch also requires a provider-resolved immutable reference; unresolved native IDs are refused. Prepared image references must contain an immutable SHA256 digest.
