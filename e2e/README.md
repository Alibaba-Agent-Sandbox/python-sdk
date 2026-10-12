# Real-cloud E2E suite (Python SDK)

End-to-end tests of `easy-sandbox` (client-sdk) and `easy-sandbox-server` (server-sdk) against the
**real Alibaba Cloud FC agent sandbox platform**: real sandboxes, real envd, real in-sandbox server,
real template build. Mocks live in `client-sdk/tests` and `server-sdk/tests`; this suite exists
because mocks cannot prove the product works (see the Definition of Done in
[`../.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md)).

> 中文说明见 [README.zh-CN.md](README.zh-CN.md). Known product defects pinned by this suite:
> [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## Run

```bash
pip install -e ./server-sdk -e ./client-sdk pytest        # or: make dev
cp .env.example .env                                       # then fill in real values (gitignored)

make e2e          # sandbox tests only (fast path, ~8 min)
make e2e-all      # + slow tests and the Docker/ACR custom-template flow
make e2e-cleanup  # dry-run janitor; add ARGS=--yes to delete leftovers

cd e2e && python -m pytest test_03_commands.py -k "timeout"   # a subset
cd e2e && python -m pytest -m "not e2e_slow" -ra               # what `make e2e` runs, plus summary
```

Required: `E2B_API_KEY` (plus `E2B_API_URL`/`E2B_DOMAIN` for non-default regions). Docker flow also
needs `AccessKey`, `AccessSecret`, `ACR_NAMESPACE` and a working Docker daemon. `OPENAI_API_KEY` /
`OPENAI_BASE_URL` are only used by AI-codegen features, which this suite does not exercise. Values
come from the environment or the gitignored `.env` files (`e2e/.env`, `.env`, `client-sdk/.env`);
the environment wins.

Without credentials every test is **skipped** with the message
`E2E skipped: missing credentials [...]`. The suite is never collected by the unit CI
(`client-sdk` / `server-sdk` run `pytest tests/` from their own directories).

## What is covered

| File | Scope |
|---|---|
| `test_01_platform.py` | auth (valid/invalid key), template catalogue, sandbox list, error mapping |
| `test_02_lifecycle.py` | create / connect / info / list / kill, timeouts (`e2e_slow`: TTL expiry), metadata tagging |
| `test_03_commands.py` | `run` / `run_code` / `custom`, exit codes, stdout/stderr, cwd, background processes, process list / signals |
| `test_04_files_envd.py` | files through envd: write/read text and binary, list/stat, mkdir/move/remove, size boundaries |
| `test_05_network_and_code.py` | port URLs and in-sandbox HTTP services, code execution |
| `test_06_server_sdk.py` | `easy-sandbox-server` inside a real sandbox (template `python-hello`): `/commands`, `/files/*`, `/process/*`, `/capabilities`, `/system/info`, `/env`, `/ports`, custom routes |
| `test_07_declarative.py` | `@sandbox` declarative remote execution |
| `test_08_custom_template_docker.py` | `DockerBuilder` -> ACR push -> official `CreateTemplate` -> sandbox -> server-sdk endpoints (`e2e_docker`, self-skips when Docker/ACR is unusable) |

Markers: `e2e` (everything), `e2e_slow` (> ~60 s), `e2e_docker` (needs Docker + ACR),
`known_issue` (strict xfail documenting a recorded bug, see [KNOWN-ISSUES.md](KNOWN-ISSUES.md)).

## Guarantees

- **Tagging and cleanup.** Every sandbox and template is created through fixtures that add the
  metadata `e2e=<run id>` (templates use the prefix `e2e-`) and register it for deletion. The session
  finalizer deletes everything tracked and then sweeps by tag, even when tests fail or the run is
  interrupted. `scripts/e2e-cleanup.py` is the janitor for runs that were hard-killed (default is a
  dry run; `--yes` deletes; `--run-id`, `--all-tagged`, `--older-than N`, `--templates`, `--acr`).
  It never touches resources without the tag/prefix.
- **Secrets are never printed.** Failure reports pass through a masking hook that replaces every
  credential value (and derived forms); helpers never log request headers. Do not add `print` of
  environment values.
- **Determinism.** Tests are independent (own sandbox or own directory under a per-run workdir),
  use generous timeouts and poll with `eventually` only for known-eventual operations (envd
  readiness, sandbox listing, server start-up).
- **Docker flow guard.** `docker_ctx` pushes a 2 MB random-layer canary to ACR first
  (`E2E_CANARY_PUSH_TIMEOUT`, default 120 s). If it cannot finish, the module is skipped with the
  exact reason instead of hanging for hours (KI-011). Docker without buildx is handled with
  `DOCKER_BUILDKIT=0` and an isolated `DOCKER_CONFIG`.

## Environment knobs

| Variable | Default | Meaning |
|---|---|---|
| `E2E_SANDBOX_TTL` | 300 | sandbox lifetime in seconds |
| `E2E_SERVER_TEMPLATE` | `python-hello` | template with `easy-sandbox-server` preinstalled |
| `E2E_RUN_ID` | generated | tag value (`e2e=<id>`) |
| `E2E_CANARY_PUSH_TIMEOUT` / `E2E_CANARY_BYTES` | 120 / 2000000 | ACR canary push limits |

## Adding a test

1. Use the fixtures (`base_sandbox`, `code_sandbox`, `server_sandbox`, `sandbox_factory`, `workdir`);
   never call `Sandbox.create` directly, or the sandbox will not be tracked.
2. Assert the **intended** behaviour. If it fails because of a product bug, mark the test
   `@pytest.mark.known_issue` + `@pytest.mark.xfail(strict=True, reason="KI-0NN: ...")` and add the
   entry to [KNOWN-ISSUES.md](KNOWN-ISSUES.md) (both languages).
3. Record the run in `.agents/evidence/verify/<date>-<topic>.md` (Definition of Done).
