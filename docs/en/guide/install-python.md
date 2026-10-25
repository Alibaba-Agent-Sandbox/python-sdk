# Install the Python packages

> Specification 5 template launch requires the matching `agent-sandbox-client==0.4.0a2` and `agent-sandbox-server==0.4.0a2` alpha packages used in this guide. The previous 0.3.x packages do not implement this entry point. To validate a source revision, install both distributions from the same checkout as described below.

Use Python 3.10 or newer and a virtual environment:

```bash
python -m venv .venv
# Linux or macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a2'
python -m pip check
```

This installs the alpha client and its required same-version `agent-sandbox-server` dependency. The import namespace is `agent_sandbox`; the unrelated PyPI distribution named `agent-sandbox` is not this project.

Check the installed pair:

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

Install the [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) separately. For template launch in this guide, use CLI 0.5.0 or newer and configure the selected provider before creating a sandbox.

## Optional dependencies

```bash
python -m pip install 'agent-sandbox-client[all]==0.4.0a2'
```

Replace `[all]` with `[mcp]`, `[session]` or `[fast]` for that subset. Template YAML and the declarative decorator belong to the base client; they need no extra. Browser automation requires Playwright installed inside the sandbox image.

## Server-only installation inside an image

```bash
python -m pip install 'agent-sandbox-server==0.4.0a2'
```

The server runs the application inside an image. Installing it does not create a sandbox. See the [server guide](server-sdk.md) to register commands and start the service.

## Development from a checkout

From the repository root, install both local distributions together:

```bash
git rev-parse HEAD
python -m pip install -e ./server-sdk -e './client-sdk[dev]'
python -m pip check
```

Record the commit when reproducing a source installation; both packages come from that same checkout. To reproduce a specific release, check out its tag first. Contributor validation and publication requirements are in [CONTRIBUTING](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md).
