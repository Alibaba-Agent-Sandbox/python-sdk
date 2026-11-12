# Authoring Templates

A template contains application source, a Dockerfile and one `template.yaml`. Use `specVersion: 1`; the [field reference](../reference/template-yaml-spec.md) describes resource, instance and native Serving configuration. Optional `registry.yaml` carries catalog descriptions and initialization questions. Dependencies belong in the Dockerfile and native dependency files.

For Python application endpoints, install `agent-sandbox-server` in the image and register actual business functions:

```python
from agent_sandbox.server import command, start

@command("hello", description="Greet a user")
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    start(9000)
```

Declare the application's startup/readiness in `sandbox.start` / `sandbox.ready` and endpoints in `sandbox.services`. YAML declarations do not register functions or enable opt-in server groups. Server policy is independent runtime configuration; install its file in the image or use the documented server configuration input. See [the server API](template-server-api.md).

Use [CLI authoring](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) to prepare and publish source. Python [launches a prepared template](template-workflows.md) or connects to an existing Sandbox. Choose one startup owner; a native template entrypoint and Python startup command must not launch the same service twice.

Call registered functions through `session.servers["app"].commands.run("hello", name="Python")` or an explicitly resolved `sandbox.application_client`. Application tokens, gateway headers and Sandbox API credentials have separate audiences. Shell execution remains `sandbox.commands.run(...)` and does not imply a business API or interpreter operation.
