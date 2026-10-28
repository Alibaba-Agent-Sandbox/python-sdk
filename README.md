# Agent Sandbox Python SDK

**English** | [中文](README.zh-CN.md)

[![CI](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/ci.yml)

Create sandboxes, execute code and commands, and work with remote files from Python. This repository contains the client SDK and the runtime used inside sandbox application images.

[Website](https://www.agent-sandbox.cn/en/) · [Documentation](docs/en/README.md) · [Examples](examples/README.md)

## Installation

Use Python 3.10+ in a virtual environment:

```bash
python -m pip install --index-url https://pypi.org/simple --upgrade --pre agent-sandbox-client
python -m pip check
```

`--pre` opts into preview releases. The package imports as `agent_sandbox` and installs its matching `agent-sandbox-server` dependency. See [installation](docs/en/guide/install-python.md) for a pinned version, optional extras and source setup. The PyPI name `agent-sandbox` belongs to a different project.

## Quick start

Configure your Express Sandbox API key, API URL and sandbox domain using `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN`. Use values for the same account and region; see [authentication](docs/en/guide/authentication.md) and [permissions](docs/en/guide/permissions.md) for their source and setup.

```python
from agent_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create(template="code-interpreter-v1")
try:
    sandbox.files.write("/tmp/input.txt", "hello")
    print(sandbox.commands.run("cat /tmp/input.txt").stdout)
    print(sandbox.run_code("1 + 1").text)
finally:
    sandbox.kill()
```

This example needs an interpreter-enabled template. `kill()` deletes the sandbox when the work finishes, including on failure.

## Choose a client

| Entry point | Use it for |
| --- | --- |
| `from agent_sandbox import Sandbox, AsyncSandbox` | Synchronous or asynchronous Express lifecycle, commands and files |
| `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` | Code execution with persistent interpreter contexts |
| `from agent_sandbox import ProviderSandbox` | Asynchronous provider plugins and template application services |

Use `await` with `AsyncSandbox` and `ProviderSandbox`. Provider operations and interpreter availability depend on the selected backend and template; see [SDK usage](docs/en/guide/sdk-usage.md).

## Other providers and application templates

Express is built in. Installable [provider plugins](https://github.com/Alibaba-Agent-Sandbox/awesome-providers) connect `ProviderSandbox` to other backends. Follow [provider setup](docs/en/guide/providers.md) before using one.

Application templates package browser tools, coding agents and other services. Launch a template with the [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox), then use its returned sandbox ID and the [template startup guide](docs/en/guide/template-workflows.md) to connect from Python. Named application commands require that service to be running.

## In-sandbox runtime

| Package | Runs where | Guide |
| --- | --- | --- |
| [`agent-sandbox-client`](client-sdk/) | Your application | [Client SDK](docs/en/guide/client-sdk.md) |
| [`agent-sandbox-server`](server-sdk/) | Inside a sandbox image | [Server SDK](docs/en/guide/server-sdk.md) |

The server exposes registered application commands over HTTP. Template authors install the server in their images and define the service startup. Client and server packages share a version; see the [server API guide](docs/en/guide/template-server-api.md) for command registration and authentication.

## Documentation

| Task | Guide |
| --- | --- |
| Make your first API calls | [Getting started](docs/en/guide/getting-started.md) |
| Look up methods and models | [API reference](docs/en/reference/api-reference.md) |
| Configure credentials and endpoints | [Authentication](docs/en/guide/authentication.md) |
| Configure file and process behavior | [File and command controls](docs/en/guide/file-and-command-controls.md) |
| Move existing E2B code | [Migration guide](docs/en/guide/migrate-from-e2b.md) |
| Resolve errors | [Troubleshooting](docs/en/guide/troubleshooting.md) |

See the [full documentation index](docs/README.md), [examples](examples/README.md) and [changelog](CHANGELOG.md).

## Related: the abx CLI

The [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) provides terminal operations, template builds and launches. Install it separately when your workflow requires it.

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for the development environment and checks for both packages. Report SDK and runtime issues in [this repository](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues).

## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE) for attribution.
