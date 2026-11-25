# Install the Python packages

The commands below select the matching **0.5.0a0 preview** packages. Available
versions are listed in [releases](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases).
To validate a checkout, use the source installation below. Use Python 3.10 or
newer and a virtual environment:

```bash
python -m venv .venv
# Linux or macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.5.0a0'
python -m pip check
```

The base client supports standard `Sandbox` / `AsyncSandbox`, `ProviderSandbox`,
`ServerClient`, template YAML and the remote `@sandbox(...)` decorator. It does not
install a local server runtime. The import namespace is `agent_sandbox`; the PyPI
distribution named `agent-sandbox` belongs to another project.

Check the installed client version:

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'))"
```

Install the [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)
separately. CLI commands vary by release; check the installed help and configure
the selected provider before deployment.

Project configuration uses `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and
`ABX_SANDBOX_DOMAIN` for all project entries, including standard Sandbox /
AsyncSandbox and ProviderSandbox. Public keyword parameters follow each entry's
documented contract; the standard `api_key=` parameter remains valid.

## Local command registration and server startup

For local `@sandbox.register` or `sandbox.server`, install the matching runtime:

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[server]==0.5.0a0'
python -m pip check
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

The `[server]` extra pins `agent-sandbox-server` to exactly the client version.
Registration belongs in the application server program; it does not upload a
local function to an existing sandbox.

## Optional dependencies

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[all]==0.5.0a0'
```

`[all]` and `[dev]` include the matching `[server]` runtime. Use `[mcp]`, `[session]`
or `[fast]` for that subset. Template YAML and the remote decorator need no extra.
Browser automation requires Playwright installed inside the sandbox image.

## Server-only installation inside an image

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-server==0.5.0a0'
```

The server runs the application inside an image. Installing it does not create a
sandbox. Host installation does not update existing sandbox images; rebuild the
image to use a new server version. See the [server guide](server-sdk.md) for
command registration and startup, and [file transfer limits](template-server-api.md#file_ops)
for buffered base64 uploads and download policy limits.

## Moving from 0.4 previews

The base 0.5 client no longer installs `agent-sandbox-server` automatically. Add
`[server]` when your local code registers commands or starts the runtime; remote
client use continues to work with the base package.

Module-level `sandbox.run` and `sandbox.run_async` have been removed. Deploy the
application first, connect to it and call `ServerClient.commands.run`; see
[template application startup and connection](template-workflows.md).
`ProviderSandbox.run` and the remote `@sandbox(...)` decorator remain available.

## Development from a checkout

From the repository root, install both local distributions together:

```bash
git rev-parse HEAD
python -m pip install -e ./server-sdk -e './client-sdk[dev]'
python -m pip check
```

For client-only source development, use `python -m pip install ./client-sdk`.
For local registration without the development tools, use
`python -m pip install ./server-sdk './client-sdk[server]'`.
Record the commit when reproducing a source installation; both packages come
from that same checkout. To reproduce a release, check out its tag first.
Contributor checks and publication requirements are in
[CONTRIBUTING](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md).
