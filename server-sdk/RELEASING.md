# Releasing `agent-sandbox-server` and `agent-sandbox-client`

This repository (`Alibaba-Agent-Sandbox/python-sdk`) publishes two lock-step PyPI distributions:

| Directory | PyPI project | Import |
| --- | --- | --- |
| `server-sdk/` | `agent-sandbox-server` | `agent_sandbox.server` |
| `client-sdk/` | `agent-sandbox-client` | `agent_sandbox` |

`agent-sandbox` on PyPI is an unrelated project. Do not publish the client under that name, and do not tell users to `pip install agent-sandbox`.

Upload the server first. The client depends on `agent-sandbox-server==<same version>`.

## Version

These four must stay equal (`client-sdk/tests/test_version_lockstep.py` and the version step in `.github/workflows/publish.yml`):

| Location | What |
| --- | --- |
| `server-sdk/src/agent_sandbox/server/_version.py` | server `__version__` |
| `client-sdk/src/agent_sandbox/_version.py` | client `__version__` |
| `client-sdk/pyproject.toml` | `agent-sandbox-server==<version>` pin |
| `client-sdk/src/agent_sandbox/agent/mcp.py` | `SERVER_VERSION` |

The version to publish is **0.3.0**. Neither project name is on PyPI yet. Do not upload a version PyPI already has.

For a later release, change all four together and move `CHANGELOG.md` `[Unreleased]` to `## [x.y.z] - YYYY-MM-DD`.

## Build and check

From the repository root, Python 3.10 or newer. This is the same build `publish.yml` runs:

```bash
python -m pip install build twine
python -m build --outdir dist/server-sdk server-sdk
python -m build --outdir dist/client-sdk client-sdk
python -m twine check dist/*/*
```

`twine check` must print `PASSED` for every wheel and sdist.

Server wheel:

- `Name: agent-sandbox-server`
- `Version: 0.3.0`
- `Requires-Python: >=3.10`
- `Requires-Dist: websockets>=12.0`
- Markdown description from `server-sdk/README.md`
- no `agent_sandbox/__init__.py`

Client wheel:

- `Name: agent-sandbox-client`
- `Version: 0.3.0`
- `Requires-Dist: agent-sandbox-server==0.3.0`
- Markdown description from `client-sdk/README.md`
- owns `agent_sandbox/__init__.py` and does not ship `agent_sandbox/server/`

`dist/` is build output. Do not commit it.

A clean install of both wheels, then `import agent_sandbox` and `import agent_sandbox.server`, is what `python scripts/check_dists.py combined-install` checks.

## Pending publishers

Publishing uses PyPI trusted publishing (OIDC). No `PYPI_API_TOKEN` and no other PyPI token is required. The workflow does not read a password.

`.github/workflows/publish.yml` requests `id-token: write` and runs in the GitHub environment `pypi`. Each upload step is `pypa/gh-action-pypi-publish@release/v1` with `skip-existing: true`. The server directory is uploaded first, then the client.

Create one pending publisher on PyPI for each project name **before** the first upload. For **both** `agent-sandbox-server` and `agent-sandbox-client`:

| Field | Value |
| --- | --- |
| PyPI project name | `agent-sandbox-server` or `agent-sandbox-client` |
| Owner | `Alibaba-Agent-Sandbox` |
| Repository name | `python-sdk` |
| Workflow filename | `publish.yml` |
| Environment name | `pypi` |

The GitHub environment `pypi` must exist on `Alibaba-Agent-Sandbox/python-sdk` (it does). Do not create a tag or a GitHub Release until both pending publishers are in place. Publishing a GitHub Release runs this workflow and uploads to PyPI.

## Dry run and re-run

`workflow_dispatch` input `dry_run` (default false) builds both distributions and runs `twine check` only. The upload steps are skipped. Use it to check the workflow on GitHub without publishing:

```bash
# Actions → Publish to PyPI → Run workflow, on main, with dry_run checked.
```

Or the API, after this workflow is on `main`:

```http
POST /repos/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/publish.yml/dispatches
{"ref":"main","inputs":{"dry_run":"true"}}
```

A real upload is a GitHub Release (`release: published`), or **Run workflow** with `dry_run` left unchecked. Unchecked `dry_run` publishes. Do not use it until both pending publishers exist.

`skip-existing: true` makes a re-run safe after a partial upload. If the server package is already on PyPI and the client step failed, re-run the failed jobs on that same workflow run (or dispatch again with `dry_run` unchecked). PyPI keeps the existing files and the missing distribution is uploaded. Server is still first.
