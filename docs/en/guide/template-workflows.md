# Launch and use a template

Use `abx --provider PROVIDER deploy SOURCE --name my-app --yes` to prepare source resources. Start an ordinary Sandbox application with its supplied `run.py`, then connect using the returned Sandbox ID and the same provider. If the platform already provides a template ID, Python can create an instance directly.

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

## Create and start an owned instance

A source template's `abx deploy` prepares reusable Sandbox resources and deploys any
Serving resources. For an ordinary Sandbox template, run its supplied `run.py` with
the returned prepared template ID. The runner creates the instance, starts its
application and saves a private session file. Follow that template's README for
credentials, model settings, endpoints and cleanup. Creating an instance alone does
not start an application that expects this explicit startup step.

If your application manages instances directly, use `ProviderSandbox.create` with the
prepared template ID and the required runtime values. Start its documented process
with `start_server`, resolve its application client, and delete only the instance you
created. Connecting to an existing instance releases a local connection when closed;
it does not confer resource ownership.

## Resource configuration

The current [resource format](../reference/template-yaml-spec.md) has named Sandbox and
Serving resources. The CLI handles its native expressions, builds and deployment.
Python creates instances from prepared IDs and consumes explicit runtime configuration;
it does not evaluate a current named-resource `template.yaml`.

The existing advanced `launch_template` API still accepts its earlier prepared snapshot
format. It does not accept current named-resource source files. Its `TemplateSession`
service/endpoint helpers remain available for that separate interface; do not pass the
current template's `template.yaml` to it. Use the template's runner or the explicit
instance API for the current resource format. Runtime TTL, environment, metadata and
mount overrides belong to instance creation or the application's runtime policy.

For a deployment of the managed Agents API, clients use its Gateway HTTP endpoint;
the template's Worker owns dynamic Sandbox creation and cleanup. See the
[managed API guide](managed-agents-api.md).

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

Existing Volume mounts are borrowed; instance cleanup never deletes those Volumes.

Executing a shell command on `code-interpreter-v1` does not exercise the interpreter API. Express, E2B and REST project adapters currently do not implement unified interpreter operations; use the documented native SDK where applicable. CubeSandbox and container edition support the persistent default-context operation.

For manifest authors and maintainers, the [shared contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts) define the exact operation and evidence formats. Historical test results describe their recorded inputs and invocation paths; they do not prove that every provider or client path has run successfully.

Provider authors may declare `workflow.source_placeholders = ["<region>", "<tag>"]` only when their CLI adapter implements `template.prepare` for source inputs. This optional metadata describes the official base-image substitution; Python validates it but does not gain source preparation support. Other placeholder names are rejected.
