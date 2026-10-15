# Releasing `agent-sandbox-server`

`agent-sandbox-server` is the PyPI distribution built from `server-sdk/`. It is the package a template image installs. The client distribution (`agent-sandbox`, built from `client-sdk/`) is a separate upload and is **not** covered by the commands below.

## Version

The two distributions are lock-step. These four must stay equal (see `client-sdk/tests/test_version_lockstep.py`):

| Location | What |
| --- | --- |
| `server-sdk/src/agent_sandbox/server/_version.py` | server `__version__` (hatch reads this) |
| `client-sdk/src/agent_sandbox/_version.py` | client `__version__` |
| `client-sdk/pyproject.toml` | `agent-sandbox-server==<version>` pin |
| `client-sdk/src/agent_sandbox/agent/mcp.py` | `SERVER_VERSION` |

The current version is **0.3.0**. `agent-sandbox-server` is not on PyPI yet, so 0.3.0 is the version to publish. Do not upload a version that PyPI already has.

When cutting the next release, change all four of the above together and set the `Next release` line in `CHANGELOG.md` to that version. A one-sided bump fails the lock-step test and the version check in `.github/workflows/publish.yml`.

## Build and check

From the repository root, with Python 3.10 or newer:

```bash
python -m pip install build twine
python -m build --outdir dist/server-sdk server-sdk
python -m twine check dist/server-sdk/*
```

`twine check` must print `PASSED` for both the wheel and the sdist. The wheel metadata must show:

- `Name: agent-sandbox-server`
- `Version: 0.3.0` (or the version you just set)
- `Requires-Python: >=3.10`
- `Requires-Dist: websockets>=12.0`
- a Markdown description rendered from `server-sdk/README.md`

The wheel must not contain `agent_sandbox/__init__.py` (that file belongs to the client distribution; the server package is only the `agent_sandbox.server` portion of the namespace). `server-sdk/tests/test_packaging.py` checks this layout.

`dist/` is build output. Do not commit it.

## Upload

The maintainer uploads with a PyPI API token. The token is not stored in this repository.

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=  # PyPI token, supplied by the maintainer
python -m twine upload dist/server-sdk/*
```

Upload `agent-sandbox-server` before any client upload. The client depends on `agent-sandbox-server==<same version>`.

A published GitHub Release also runs `.github/workflows/publish.yml`, which builds both distributions, runs `twine check`, and uploads the server and then the client using the `PYPI_API_TOKEN` secret.

## PyPI name

`agent-sandbox-server` has no existing PyPI project, so the first upload creates it.

The name `agent-sandbox` on PyPI is a different project (Agent Infra Team, "Python SDK for the All-in-One Sandbox API", latest 0.0.30 as of 2026-10-15). Do not upload `client-sdk` under that name. `publish.yml` will try; that client upload fails until the client distribution is renamed. The server upload is independent and can still be published with the commands above.
