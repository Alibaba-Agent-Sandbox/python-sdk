# Install the Python packages

The immutable source recipe below installs the tested 0.3.0 snapshot. The current 0.3.1a2 alpha candidate is documented separately below and is usable from PyPI only after its publication and public readback succeed. Package names alone do not prove publication. The CLI is installed separately from its own repository.

## Paired immutable source

Use a virtual environment with Python 3.10 or newer. This tested immutable implementation includes standard sync/async clients, native provider/server extensions, the server startup acknowledgement fix, strict workflows and the base YAML parser. It does not claim to be the latest main commit.

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"
python -m pip check
python -c "import agent_sandbox, agent_sandbox.server; from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

Both versions are 0.3.0 and must match. The client has a hard same-version server dependency for local server and declarative helpers; explicitly installing both source distributions prevents pip from seeking the unavailable server on an index. Do not install the unrelated `agent-sandbox` distribution.

## Optional extras

Workflow YAML loading and the declarative decorator are part of the base client; there is no declarative extra.

For all extras, retain the same server URL and use the client extra on its direct reference:

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[all] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=client-sdk"
```

Replace `[all]` with `[mcp]`, `[session]` or `[fast]` for that subset. MCP needs its extra; Browser automation requires separately installed Playwright in the image.

## Server-only image installation

```bash
python -m pip install "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/fee74e631d9cfc3488fd41f853ca6dafc1277784.tar.gz#subdirectory=server-sdk"
```

The in-sandbox service and the local client have different roles; installing the server does not create a sandbox.

## Current development checkout

From this repository root, in an isolated environment:

```bash
python -m pip install -e ./server-sdk -e "./client-sdk[dev]"
python -m pip check
```

This uses the checked-out revision rather than the immutable example above. Record its commit for reproducibility. Run examples only after configuring the required provider; an installation pass is not cloud/provider/model acceptance. Diagnose dependency conflicts in a fresh environment before reinstalling both matched distributions.

## Maintainer publication checks

Publish both distributions from a matching `v<version>` tag. The workflow first runs
the reusable CI suite against that same tag checkout; publication depends on its success.
The release workflow
builds one wheel/sdist pair per package, installs the exact wheel pair in a clean
environment, and preserves the candidate artifact. A manual run defaults to dry-run
and still requires the version tag. Before upload, any existing PyPI file must match
the candidate SHA-256; `skip-existing` alone is not verification. Server uploads before
client. After upload, the workflow checks public file digests and installs the exact client from the public index in a fresh environment, validates the automatically installed matching server, and runs `pip check`. A failed readback means publication
has not been verified; preserve the candidate for recovery instead of rebuilding silently.
This workflow does not replace required CI, reviews or real-backend acceptance.

## Optional alpha release

The 0.3.1a2 candidate is an opt-in prerelease. Once its public release is verified, install the exact client version below; its matching server is a required dependency. Until publication completes, the immutable source recipe above remains available. Node provider doctor requires the companion CLI initialize endpoint (planned CLI 0.4.11); 0.4.10 does not support it. This is not a production-readiness claim.

```bash
python -m pip install 'agent-sandbox-client==0.3.1a2'
python -m pip check
```
