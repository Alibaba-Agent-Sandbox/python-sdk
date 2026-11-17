# Authoring Templates

A template contains application source, a Dockerfile and one `template.yaml`. Use `specVersion: 1`; the [field reference](../reference/template-yaml-spec.md) describes named resource and native Serving configuration; dynamic instance values belong to runtime code. Optional `registry.yaml` carries catalog descriptions and initialization questions. Dependencies belong in the Dockerfile and native dependency files.

For Python application endpoints, install `agent-sandbox-server` in the image and register actual business functions:

```python
from agent_sandbox.server import command, start

@command("hello", description="Greet a user")
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    start(9000)
```

Provide the application's create-time startup and readiness in its runtime code, such as the supplied `run.py`. Resource YAML declares reusable Sandbox templates and native Serving props. YAML declarations do not register functions or enable opt-in server groups. Server policy is independent runtime configuration; install its file in the image or use the documented server configuration input. See [the server API](template-server-api.md).

Use [CLI authoring](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/authoring-templates.md) to prepare and publish source. Python [launches a prepared template](template-workflows.md) or connects to an existing Sandbox. Choose one startup owner; a native template entrypoint and Python startup command must not launch the same service twice.

Call registered functions through `client.commands.run("hello", name="Python")` after explicitly resolving `client` with `sandbox.application_client`. Application tokens, gateway headers and Sandbox API credentials have separate audiences. Shell execution remains `sandbox.commands.run(...)` and does not imply a business API or interpreter operation.
