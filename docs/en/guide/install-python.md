# Install the Python packages

Current development version 0.3.0 is not published on PyPI: both distribution metadata endpoints returned 404 on 2026-10-19. Package names do not prove publication. Use the tested paired source recipe below or a development checkout. The CLI is installed separately from its own repository.

## Paired immutable source

Use a virtual environment with Python 3.10 or newer. This tested immutable implementation includes standard sync/async clients, native provider/server extensions, and the server startup acknowledgement fix. It does not claim to be the latest main commit.

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
python -m pip check
python -c "import agent_sandbox, agent_sandbox.server; from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

Both versions are 0.3.0 and must match. The client has a hard same-version server dependency for existing decorator/namespace compatibility; explicitly installing both source distributions prevents pip from seeking the unavailable server on an index. Do not install the unrelated `agent-sandbox` distribution.

## Optional extras

For all extras, retain the same server URL and use the client extra on its direct reference:

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=client-sdk"
```

Replace `[all]` with `[mcp]`, `[declarative]`, `[session]` or `[fast]` for that subset. MCP needs its extra; the empty `[server]` alias alone does not add features. Browser automation requires separately installed Playwright in the image.

## Server-only image installation

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/08c51248bb3c1a6f1380bdb3d33126cda23bb7ec.tar.gz#subdirectory=server-sdk"
```

The in-sandbox service and the local client have different roles; installing the server does not create a sandbox.

## Current development checkout

From this repository root, in an isolated environment:

```bash
python -m pip install -e ./server-sdk -e "./client-sdk[dev]"
python -m pip check
```

This uses the checked-out revision rather than the immutable example above. Record its commit for reproducibility. Run examples only after configuring the required provider; an installation pass is not cloud/provider/model acceptance. Diagnose dependency conflicts in a fresh environment before reinstalling both matched distributions.
