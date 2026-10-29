# Declarative Usage (@sandbox Decorator)

The `@sandbox` decorator lets you declaratively execute Python functions in a remote sandbox without manually managing the sandbox lifecycle.

---

## Basic Usage

```python
from agent_sandbox.declarative import sandbox

@sandbox(template="code-interpreter-v1")
def analyze(data):
    import pandas as pd
    df = pd.DataFrame(data)
    return df.describe().to_dict()

# When called, it automatically: creates sandbox → uploads function → executes → returns result → destroys sandbox
result = analyze({"col1": [1, 2, 3], "col2": [4, 5, 6]})
print(result)
```

---

## Parameter Configuration

```python
@sandbox(
    template="code-interpreter-v1",  # Template name (default "code-interpreter-v1")
    timeout=300,                      # Sandbox timeout in seconds (default 300)
    envs={"MY_KEY": "value"},         # Environment variables
    packages=["pandas", "numpy"],     # pip packages to pre-install remotely
    serializer="json",                # Serialization method (default "json")
    sandbox_id=None,                  # Reuse an existing sandbox ID (skips creation when not None)
    keep_alive=False,                 # When True, the sandbox is not destroyed after execution
    sandbox_api_key=None,             # API Key override
    sandbox_base_url=None,            # Platform API URL override
    sandbox_domain=None,              # Domain override
    cpu=None,                         # CPU cores
    memory=None,                      # Memory in MB
)
def my_func():
    pass
```

### Parameter Details

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `template` | `str` | `"code-interpreter-v1"` | Sandbox template name |
| `timeout` | `int` | `300` | Sandbox timeout in seconds |
| `envs` | `dict` | `None` | Injected environment variables (envd scope; see [Environment Variables Guide](environment-variables.md)) |
| `packages` | `list[str]` | `None` | pip packages to pre-install remotely |
| `serializer` | `str` | `"json"` | Serialization mode (only `json` is supported) |
| `sandbox_id` | `str` | `None` | Reuse an existing sandbox ID |
| `keep_alive` | `bool` | `False` | Do not destroy the sandbox after execution |
| `sandbox_api_key` | `str` | `None` | API Key override |
| `sandbox_base_url` | `str` | `None` | Platform URL override |
| `sandbox_domain` | `str` | `None` | Platform domain |
| `cpu` | `int` | `None` | CPU cores |
| `memory` | `int` | `None` | Memory in MB |

---

## Serialization Rules

The `serializer` parameter controls how function arguments and return values are serialized. Currently only JSON mode is supported.

| Mode | Extra Dependencies | Supported Types | Description |
|------|-------------------|-----------------|-------------|
| `json` (default) | None | JSON-serializable types | Safest, cross-language compatible |

**JSON mode**: Arguments are serialized via `json.dumps`, and results are deserialized via `json.loads`. Unsupported types fall back to `default=str`.

---

## Using with async

The decorator automatically detects whether the decorated function is asynchronous:

```python
@sandbox(template="code-interpreter-v1")
async def async_analyze(data):
    import pandas as pd
    df = pd.DataFrame(data)
    return df.describe().to_dict()

# Async call
result = await async_analyze({"col": [1, 2, 3]})
```

Synchronous decorated functions block until their remote result is available. In an asynchronous application, decorate an `async def` function and await it.

---

## Reusing a Sandbox

Create the instance explicitly so you retain its ID and control when it is deleted.
The decorator connects to that instance and closes its borrowed client after execution.

```python
import asyncio
from agent_sandbox import ProviderSandbox
from agent_sandbox.declarative import sandbox

async def main():
    instance = await ProviderSandbox.create(template="base")
    try:
        @sandbox(sandbox_id=instance.id)
        async def calculate():
            import math
            return math.factorial(6)

        print(await calculate())
    finally:
        await instance.kill()

asyncio.run(main())
```

`keep_alive=True` on an automatically created instance retains the remote sandbox, but the decorator returns only the function result. Prefer the explicit ownership pattern above when you need to reconnect or clean up.

## Registered application commands

Register application commands inside the template image and start its service:

```python
# commands.py inside the template image
from agent_sandbox.server import command, start

@command()
def demo(x: int, y: str) -> str:
    return f"{y}={x}"

if __name__ == "__main__":
    start(9000)
```

Launch the template using the [CLI template guide](template-workflows.md), then connect to the returned sandbox ID. Set `application_token` to the same application token used at launch:

```python
from agent_sandbox import ProviderSandbox

instance = await ProviderSandbox.connect(sandbox_id)
try:
    async with await instance.application_client(9000, token=application_token) as client:
        print(await client.commands.run("demo", x=1, y="hello"))
finally:
    await instance.close()
```

Local `sandbox.register` registration does not upload a function to a remote sandbox. Template deployment and a running application service are required for named HTTP commands. Use the function decorator above for direct function execution.

## Limitations

1. **Parameter serialization**: Function arguments and return values must be JSON-serializable (non-serializable types fall back to `str`)
2. **Function source code**: The decorator obtains function source via `inspect.getsource()` — lambdas and dynamically generated functions are not supported
3. **Imports**: Libraries needed in the remote sandbox must be pre-installed via the `packages` parameter or already included in the template
4. **Registered command parameter types**: `@sandbox.register` supports `str`, `int`, `float`, `bool` and `list[str]`; arbitrary object types are not supported
5. **Closure variables**: External variables referenced in the function are not automatically serialized — use explicit parameter passing instead
6. **Execution environment isolation**: The decorated function runs in an independent remote Python process and does not share state with the local process

---

## Next Steps

- [SDK Usage Guide](sdk-usage.md) — Use the Sandbox API directly
- [Authoring Templates](authoring-templates.md) — Create custom templates
- [API Reference](../reference/api-reference.md) — Complete API signatures
