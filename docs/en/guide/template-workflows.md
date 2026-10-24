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

For a new prepared-image workflow:

```python
from agent_sandbox.api import launch_workflow

async with await launch_workflow(
    "template.yaml", provider="opensandbox", workflow_id="application-image",
    reference=immutable_image_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

The selected manifest must declare that workflow. Python does not build source projects. Use the CLI to prepare them first; connect to its returned sandbox ID, or use an `image` workflow with the resulting SHA256 image reference. A `managed` workflow accepts the native template ID belonging to its declared provider; it does not require a platform version number. An external application uses a `service` workflow and explicit application URL. The standalone launcher does not execute application deployment hooks or reinterpret deployment topology.

The launcher freezes manifest inputs, checks the provider's actual code digest, persists intent before create, records owned resource IDs, checks application protocol version before invocation, and deletes only its owned sandbox. An uncertain create is not replayed and remains in a journal for reconciliation using its `abx_workflow_run` metadata. Cleanup failure preserves resource IDs and raises. Journals contain no API keys, application tokens, environment secrets or signed endpoint URLs. A journal alone is not a trusted verification receipt.

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

If you already have a manifest declaring `input: managed`, use `launch_workflow(manifest, provider="alicloud-express", reference="base")` instead. Its async context manager deletes the sandbox it creates. The workflow still checks the provider, required operations and startup mode. A native ID without a content digest is usable; its journal records the artifact digest as unknown and makes no immutable-content claim.

Executing a shell command on `code-interpreter-v1` does not exercise the interpreter API. Express, E2B and REST project adapters currently do not implement unified interpreter operations; use the documented native SDK where applicable. CubeSandbox and container edition support the persistent default-context operation.

For manifest authors and maintainers, the [shared contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts) define the exact operation and evidence formats. Historical test results describe their recorded inputs and invocation paths; they do not prove that every provider or client path has run successfully.

Provider authors may declare `workflow.source_placeholders = ["<region>", "<tag>"]` only when their CLI adapter implements `template.prepare` for source inputs. This optional metadata describes the official base-image substitution; Python validates it but does not gain source preparation support. Other placeholder names are rejected.
