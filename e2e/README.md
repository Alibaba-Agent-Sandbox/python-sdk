# Real-cloud E2E suite (Python SDK)

End-to-end tests of `agent-sandbox` (client-sdk) and `agent-sandbox-server` (server-sdk) against the
**real Alibaba Cloud FC agent sandbox platform**: real sandboxes, real envd, real in-sandbox server.
Templates are built and deployed with `abx template build|deploy`, which the CLI's own E2E suite covers. Mocks live in `client-sdk/tests` and `server-sdk/tests`; this suite exists
because mocks cannot prove the product works (see the Definition of Done in
[`../.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md)).

> 中文说明见 [README.zh-CN.md](README.zh-CN.md). Known product defects pinned by this suite:
> [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## Run

```bash
pip install -e ./server-sdk -e ./client-sdk pytest        # or: make dev
cp .env.example .env                                       # then fill in real values (gitignored)

make e2e          # sandbox tests only (fast path, ~8 min)
make e2e-all      # + slow tests
make e2e-cleanup  # dry-run janitor; add ARGS=--yes to delete leftovers

cd e2e && python -m pytest test_03_commands.py -k "timeout"   # a subset
cd e2e && python -m pytest -m "not e2e_slow" -ra               # what `make e2e` runs, plus summary
```

Required: `ABX_SANDBOX_API_KEY` (plus `ABX_SANDBOX_BASE_URL`/`ABX_SANDBOX_DOMAIN` for non-default
regions). Values come from the environment or the gitignored `.env` files (`e2e/.env`, `.env`, `client-sdk/.env`);
the environment wins.

Without credentials every test is **skipped** with the message
`E2E skipped: missing credentials [...]`. The suite is never collected by the unit CI
(`client-sdk` / `server-sdk` run `pytest tests/` from their own directories).

## Provider plugins

Third-party providers are not part of this suite's cloud run. They follow the same six tiers as the CLI, from plugin unit tests (T0) to a local OpenSandbox server (T4) and the Alibaba Cloud platform (T5). The table is [cli/e2e/providers/PLAN.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/e2e/providers/PLAN.md) ([中文](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/e2e/providers/PLAN.zh-CN.md)). OpenSandbox helpers for T4 live in [opensandbox/README.md](opensandbox/README.md).

## What is covered

| File | Scope |
|---|---|
| `test_01_platform.py` | auth (valid/invalid key), sandbox list, error mapping |
| `test_02_lifecycle.py` | create / connect / info / list / kill, timeouts (`e2e_slow`: TTL expiry), metadata tagging |
| `test_03_commands.py` | `commands.run` / `run_code`, exit codes, stdout/stderr, cwd, background processes, process list / signals |
| `test_04_files_envd.py` | files through envd: write/read text and binary, list/stat, mkdir/move/remove, size boundaries |
| `test_05_network_and_code.py` | port URLs and in-sandbox HTTP services, code execution |
| `test_06_server_sdk.py` | `agent-sandbox-server` inside a real sandbox (template `python-hello`): `/commands`, `/files/*`, `/process/*`, `/capabilities`, `/system/info`, `/env`, `/ports`, custom routes |
| `test_07_declarative.py` | `@sandbox` declarative remote execution |
| `test_08_providers.py` | Live calls for `opensandbox`, `alicloud-express` (SDK and CLI), `cubesandbox`, `e2b`, and `alicloud-container`. A provider with no backend of its own is skipped and does not receive the Express key. |
| `test_09_volume_mounts.py` | Opt-in existing Volume acceptance: prove an exact kernel mount, exclusively create/read/remove a sentinel, and verify persistence after destroying and recreating a sandbox. All tagged sandboxes are released. Ordinary directories cannot pass. |
| `test_09_mcp_lifecycle.py` | Python MCP metadata/TTL/list, command/files and external-instance ownership |

Markers: `e2e` (everything), `e2e_slow` (> ~60 s),
`known_issue` (strict xfail documenting a recorded bug, see [KNOWN-ISSUES.md](KNOWN-ISSUES.md)).


Python MCP lifecycle coverage is in `test_09_mcp_lifecycle.py`: real creation,
allowlisted metadata, list visibility, TTL, command/file use, and external-query
ownership at shutdown. Only listing retries, using the existing 40-second
eventual-consistency window. No IDE or new-image deployment is inferred.

## Guarantees

- **Tagging and cleanup.** Every sandbox is created through fixtures that add the
  metadata `e2e=<run id>` and register it for deletion. The MCP creation
  tool does not expose metadata; its E2E records the returned owned ID directly
  in the tracker and shuts down its owning manager in `finally`. The session
  finalizer deletes everything tracked and then sweeps by tag, even when tests fail or the run is
  interrupted. `scripts/e2e-cleanup.py` is the janitor for runs that were hard-killed (default is a
  dry run; `--yes` deletes; `--run-id`, `--all-tagged`, `--older-than N`).
  It never touches sandboxes without the tag.
- **Secrets are never printed.** Failure reports pass through a masking hook that replaces every
  credential value (and derived forms); helpers never log request headers. Do not add `print` of
  environment values.
- **Determinism.** Tests are independent (own sandbox or own directory under a per-run workdir),
  use generous timeouts and poll with `eventually` only for known-eventual operations (envd
  readiness, sandbox listing, server start-up).

## Environment knobs

The server fixture follows `Sandbox.server_at`: the template-authored server has
no configured token, so it does not receive the unrelated envd `X-Access-Token`.
The CLI provider scenario uses `ABX_BIN` (which may include arguments) or `abx` on
`PATH`; it never assumes a sibling source checkout. Missing expected report rows
fail the scenario, including when no CLI executable is available.

Install the catalog providers required for credential-refusal checks in an isolated
test HOME before running the complete suite. Installation must keep consent and
doctor verification enabled; a missing plugin cannot prove its credential boundary.
Host-side `InvalidCredentialsError` and provider-side `InvalidAPIKeyError` are both
valid credential refusals. Cube live acceptance requires an explicitly configured
`ABX_CUBESANDBOX_BASE_URL`; an unrelated local port listener is insufficient.

| Variable | Default | Meaning |
|---|---|---|
| `E2E_SANDBOX_TTL` | 300 | sandbox lifetime in seconds |
| `E2E_SERVER_TEMPLATE` | `python-hello` | template with `agent-sandbox-server` preinstalled |
| `E2E_RUN_ID` | generated | tag value (`e2e=<id>`) |
| `ABX_E2E_VOLUME_MOUNT` | unset; skips | Set to `1` to permit the Volume acceptance test. |
| `ABX_E2E_VOLUME_NAME` | unset; skips | Existing writable Volume name in the API key's Team/region, with its storage role configured. No Volume is provisioned or deleted. |
| `ABX_E2E_VOLUME_MOUNT_PATH` | unset; skips | Dedicated canonical sandbox path under `/mnt/abx-e2e/`. This narrower path rule belongs to the test harness. |
| `E2E_VOLUME_TEMPLATE` | unset; skips | Template meeting the storage/runtime requirements in the [official mount guide](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1). |

## Adding a test

1. Use the fixtures (`base_sandbox`, `code_sandbox`, `server_sandbox`, `sandbox_factory`, `workdir`);
   never call `Sandbox.create` directly, or the sandbox will not be tracked.
2. Assert the **intended** behaviour. If it fails because of a product bug, mark the test
   `@pytest.mark.known_issue` + `@pytest.mark.xfail(strict=True, reason="KI-0NN: ...")` and add the
   entry to [KNOWN-ISSUES.md](KNOWN-ISSUES.md) (both languages).
3. Record the run in `.agents/evidence/verify/<date>-<topic>.md` (Definition of Done).
