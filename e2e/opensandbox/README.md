# OpenSandbox live-test helpers

Secret-free helpers for running the Easy Sandbox `opensandbox` provider against a real,
local [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) server (Docker
runtime). Design and rationale: `docs/en/design/provider-opensandbox-mapping.md`.

| File | Purpose |
|---|---|
| `local-up.sh` | `up` (default) / `down` / `status` / `env`. Installs Docker (`docker.io`) and `opensandbox-server` into `$OSB_WORKDIR` if missing, starts both, waits for `/health`, prints `export` lines. Needs Linux, Docker-capable kernel, passwordless sudo (or root), internet. |
| `live_smoke.py` | Stdlib-only, 35 checks of every REST call the provider needs (auth, create/get/list/endpoint, SSE exec, background commands, files, renew, pause/resume, kill). |
| `sdk_smoke.py` | Same flow through the official `opensandbox` Python SDK (`pip install opensandbox`); oracle only. |

```bash
cd python-sdk/e2e/opensandbox
./local-up.sh up
eval "$(./local-up.sh env)"
python3 live_smoke.py          # prints ALL OK on success
python3 sdk_smoke.py           # optional
./local-up.sh down
```

Tunables (environment): `OSB_SERVER_VERSION` (1.1.1), `OSB_EXECD_IMAGE`
(`opensandbox/execd:latest`; v1.1.0 lacks `argv`), `OSB_PORT` (8080), `OSB_API_KEY`
(`local-dev-key`, not a secret), `OSB_WORKDIR` (`~/.cache/easy-sandbox/opensandbox-local`),
`OSB_WITH_EGRESS`, `OSB_WITH_CODE_INTERPRETER`. Test overrides read by the smokes:
`OPENSANDBOX_BASE_URL`, `OPENSANDBOX_API_KEY`, `OPENSANDBOX_TEST_IMAGE`, `OPENSANDBOX_DOMAIN`.

These files are not pytest tests (no `test_*` names) and are never collected by `make e2e`.

## Provider plugin E2E

Two further scripts exercise the exec-provider plugin in `examples/providers/opensandbox/` against the
same local server. They use a throwaway `HOME` (your real `~/.ebx` is never touched) and read the server
from the environment: `EBX_OPENSANDBOX_BASE_URL` (default `http://127.0.0.1:8080`) and the API key from
`EBX_OPENSANDBOX_API_KEY`, `OPEN_SANDBOX_API_KEY` or `OPENSANDBOX_API_KEY`. Needs Node >= 20, pytest and an
importable `easy_sandbox` (the scripts add the sibling `client-sdk/src` to `PYTHONPATH`).

| File | Purpose |
|---|---|
| `provider_e2e.py` | Stages `node-unit`, `node-live`, `install`, `kit` (shared `ProviderContractTests --provider-under-test opensandbox`), `sdk` (`Sandbox.create(provider="opensandbox")` scenarios) and `env` (canonical `EBX_OPENSANDBOX_*` beats native `OPEN_SANDBOX_*`). `--stages a,b` selects a subset. |
| `provider_install_e2e.py` | Install flows with `python -m easy_sandbox.providers`: local path, git `file://` bare repo pinned to a commit, tree-digest receipt, tamper detection, update (check / re-consent / rollback), uninstall, `--purge`, `--link`. Needs only `git` and Node; uses the server for one sandbox round trip when it is reachable. |

```bash
./local-up.sh up && eval "$(./local-up.sh env)"
python3 provider_e2e.py                # the OPENSANDBOX_* names printed by local-up.sh env are accepted too
python3 provider_install_e2e.py
```

Both exit non-zero when a check fails. `provider_install_e2e.py` used to print non-fatal `[GAP ]` / `[BUG ]`
lines for installer defects found by the authoring evaluation (`docs/en/design/provider-authoring-evaluation.md`);
all of them are fixed and are now ordinary checks. The `kit` stage runs
`python -m easy_sandbox.providers test opensandbox`. Like the files above, these are not pytest tests and
`make e2e` never collects them.
