# Launch and use a template

Use the CLI to prepare a source template, then connect with Python. If the platform already provides a template ID, Python can create it directly.

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

The client also sends the explicit application token in the server's existing `X-Access-Token` header when that header is unused. This keeps authentication working through proxies that strip `Authorization`, including OpenSandbox 1.1.1. Existing gateway headers, including defaults on an injected HTTP client, are never replaced. Bearer authentication remains available for services that require it.

To start the complete template from a prepared provider reference:

```python
from agent_sandbox.api import launch_template

async with await launch_template(
    "template.yaml", provider="opensandbox",
    reference=prepared_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

There is no workflow selection. Python creates one sandbox, runs `start_cmd` once,
checks `ready_cmd`, and resolves every service in `provides`. SandboxServer protocol v2 services
receive health/discovery checks before use. Other service protocols use the template's
readiness command; their endpoints are returned without guessing protocol routes.
`session.services` contains every service client, while `session.servers` contains
SandboxServer clients. `session.server` and `session.run_command` are conveniences
only when there is exactly one SandboxServer. With several, call
`session.servers["service-name"].commands.run(...)` to choose the invocation target.
Choosing a client never changes which template services were started.

Python does not build sources. Prepare them with the CLI and pass the resulting
provider reference, or connect to the sandbox returned by the CLI. A manifest may
also declare a fixed digest-pinned `image`, or `provider` plus `template_id` for a
platform-managed template. References are interpreted by that Provider; native IDs
need no artificial version. For an existing external HTTP service, use `ServerClient`
directly. Application deployment hooks still belong to the deployment orchestrator.

The launcher freezes the manifest, records intent and owned IDs, and deletes only its
own sandbox. Uncertain creation is not retried and remains recorded for reconciliation
using `abx_template_run` metadata. Every resolved client is closed on failure, including
failure of a later service. Journals exclude tokens, environment values and signed URLs;
they do not constitute verified cloud receipts. One effective `ABX_SERVER_TOKEN` value
is used both for the sandbox environment and the application clients.

## Migrating specification 4

Use `spec_version: 5`; remove `workflow_contract_version`, `default_workflow`, and
`workflows`. Retain the full `provides` map and the template's actual `start_cmd` and
`ready_cmd`. Remove CLI `--workflow` and replace Python `launch_workflow` with
`launch_template` without `workflow_id`. Old manifests fail with a migration error;
they are not silently reduced to their former default. Historical specification 4
receipts remain history and do not prove the specification 5 startup path.

## Interpreter operations

`ProviderSandbox.code.run(code)` selects stateless `code.execute`. The provider protocol must implement isolation (a native stateless call or temporary context with guaranteed cleanup). `mode="default-context"` explicitly selects persistent `code.default-context.execute`; `context_id=...` selects `code.context.execute`. Creating, listing, restarting and deleting contexts each require their own operation. Realtime callbacks require `code.stream`; a buffered response is not realtime streaming. Rich structured results have a separate operation.

A missing runtime or interpreter HTTP 404 remains an error. It never writes a temporary script and runs a shell instead. To run a Python script through a shell, explicitly use `files.write()` and `commands.run("python script.py")`. The pinned standard `Sandbox`/`AsyncSandbox` and `code_interpreter` clients keep their independent public contract.

## Platform-managed templates

For a native template such as Express `base`, the direct SDK API is sufficient:

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(template="base", provider="alicloud-express")
try:
    result = await sandbox.commands.run("python3 --version")
    print(result.stdout)
finally:
    await sandbox.kill()  # this code created and owns the sandbox
```

With a specification 5 manifest containing `provider: alicloud-express`,
`template_id: base` and `provides: {}`, `launch_template(manifest,
provider="alicloud-express")` offers the same owned cleanup through its async context
manager. No workflow declaration or selector is required.

Executing a shell command on `code-interpreter-v1` does not exercise the interpreter API. Express, E2B and REST project adapters currently do not implement unified interpreter operations; use the documented native SDK where applicable. CubeSandbox and container edition support the persistent default-context operation.

For manifest authors and maintainers, the [shared contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts) define the exact operation and evidence formats. Historical test results describe their recorded inputs and invocation paths; they do not prove that every provider or client path has run successfully.

Provider authors may declare `workflow.source_placeholders = ["<region>", "<tag>"]` only when their CLI adapter implements `template.prepare` for source inputs. This optional metadata describes the official base-image substitution; Python validates it but does not gain source preparation support. Other placeholder names are rejected.
