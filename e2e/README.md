# Real-cloud E2E suite (Python SDK)

Run `ABX_BIN=<candidate> pytest e2e/test_managed_api_key.py -q` with AK/SK and the Express endpoint/domain to verify explicit SDK preparation and standard/provider sandbox exec/files lifecycle through the real shared engine. The test uses an isolated home, confirms key deletion and stops its engine. Cleanup additionally needs `sandbox:DeleteApiKey`; see [permissions](../docs/en/guide/permissions.md).

End-to-end tests of `agent-sandbox` (client-sdk) and `agent-sandbox-server` (server-sdk) against the
**real Alibaba Cloud FC agent sandbox platform**: real sandboxes, real envd, real in-sandbox server.
Templates are built and deployed with `abx template build|deploy`, which the CLI's own E2E suite covers. Mocks live in `client-sdk/tests` and `server-sdk/tests`; this suite exists
because mocks cannot prove the product works (see the Definition of Done in
[`../.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md)).

> 中文说明见 [README.zh-CN.md](README.zh-CN.md). Known product defects pinned by this suite:
> [KNOWN-ISSUES.md](KNOWN-ISSUES.md).

## Standard E2B migration verification

Run `python -m pytest e2e/test_standard_contract.py -ra` from the repository root
for the standard Sandbox/AsyncSandbox and code_interpreter entry points. It
checks actual cloud lifecycle, files, background stdin, interpreter contexts,
callbacks, lazy pagination and network deny/restore. The separate native suites
continue to exercise ProviderSandbox. Do not count their mocks as cloud evidence.

Snapshot restoration additionally needs `E2E_SNAPSHOT_TEMPLATE`, naming a MicroVM
template in an account with the snapshot allowlist. Without it that scenario is
explicitly skipped. The test deletes its snapshots and tracks restored sandboxes.
Conditional pause/resume requires a supported runtime/account; a preserved method
alone is not verification. See the bilingual migration guide for service limits.

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
| `test_skill_storage_state.py` | Explicitly owned RW/RO OSS fixtures: standard-client persistence after sandbox destruction/recreation, exact kernel mounts, read-only enforcement and typed cleanup. |
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

## Owned OSS persistence and read-only acceptance

`test_skill_storage_state.py` uses the standard synchronous client against two
explicitly owned OSS Volume configurations pointing at the same dedicated storage
path: one writable and one read-only. Provision them separately, in the configured
API key's Team/region, with a RAM role limited to that owned storage. No Volume,
role or bucket is provisioned or deleted by this test.

Set `E2E_VOLUME_ACCEPTANCE=owned-only`, `E2E_VOLUME_OWNER_RUN` to your owned run name
(`abx-accept-` followed by 12 lowercase letters/digits), and
`E2E_VOLUME_RW_NAME`/`E2E_VOLUME_RO_NAME` to that run name plus `-rw`/`-ro`.
Also set `E2E_VOLUME_TEMPLATE` explicitly to an eligible runtime. MicroVM images
must already contain ossfs2 2.0.10 or newer; see the
[official mount prerequisites](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1).

Run `python -m pytest e2e/test_skill_storage_state.py -ra`. The test verifies the
exact kernel mount before touching a uniquely named, exclusively created sentinel,
fsyncs it, destroys the first sandbox and checks typed not-found, then creates a
new sandbox and reads the persisted data. A read-only mount must read that data
and reject a separate exclusive write with a permission/read-only errno. Cleanup
only removes the verified owned sentinel and tracked sandboxes. The fixture owner
must separately clean up its Volume definitions, role and backing storage.
Missing opt-in skips before constructing cloud fixtures; incomplete explicit
prerequisites fail rather than selecting an arbitrary Volume.

The standard Snapshot regression keeps its mutable marker inside an owned,
non-sticky directory. The tested envd image rejects SDK overwrite directly under
sticky `/tmp` even before a Snapshot; that independent behavior is retained in
[the state/storage verification record](../.agents/evidence/verify/2026-10-26-skill-storage-state-acceptance.md).

## Repository, expiring preview and third-party MCP runner

Run `python e2e/skill_tools_acceptance.py --output NEW_JSON_PATH` in an environment
with this checkout's matching client/server pair installed. Configure the standard
sandbox credentials locally; no account key is sent into the sandbox. The runtime
must provide Python, Node.js, git and outbound access to GitHub/npm.
`ABX_SKILL_RUNTIME_TEMPLATE` selects the eligible runtime (default
`code-interpreter-v1`); `ABX_SKILL_RUN_PREFIX` sets the owned fixture's purpose tag.
The new evidence output must not already exist.

The runner fetches the exact pinned public repository commit with at most two
bounded read-only attempts, verifies and starts its Node application, then checks
an application HMAC preview: valid response, unsigned/tampered rejection and
20-second expiry. This temporary fixture uses an application proxy with
`secure=False`; it does not prove provider gateway-native signed links. It then
installs pinned filesystem MCP releases `2026.7.10` and `2026.8.31`, performs actual
initialize/tools-list/read-file calls, reads logs, removes tools and verifies no
owned MCP process or sandbox remains. It is a manual real-cloud runner, not an
implicitly enabled unit/Actions test. Failures and cleanup are saved separately
from successful checks.

## Adding a test

1. Use the fixtures (`base_sandbox`, `code_sandbox`, `server_sandbox`, `sandbox_factory`, `workdir`);
   never call `Sandbox.create` directly, or the sandbox will not be tracked.
2. Assert the **intended** behaviour. If it fails because of a product bug, mark the test
   `@pytest.mark.known_issue` + `@pytest.mark.xfail(strict=True, reason="KI-0NN: ...")` and add the
   entry to [KNOWN-ISSUES.md](KNOWN-ISSUES.md) (both languages).
3. Record the run in `.agents/evidence/verify/<date>-<topic>.md` (Definition of Done).

## Shared Provider conditional acceptance (local only)

Use a CLI build containing the six Express command descriptors and a ready generation2 template admitted to pause/Snapshot. Run against local credentials:

```sh
python e2e/provider_conditional.py --abx "$ABX_BIN" \
  --template "$E2E_SNAPSHOT_TEMPLATE" --env-file .env --report provider-conditional-report.json
```

The controller starts an isolated real engine, compares CLI/Python discovery, tests both directions of pause/resume and Snapshot create/list/restore/delete, checks in-memory/file continuity and clone isolation, and independently verifies owned cleanup. It does not create/delete the supplied template. Keep the binary outside a build directory that another build can erase. The report excludes credentials and resource identifiers. This manual controller is not collected by pytest and is not dispatched from Actions.


### Optional native CLI named-array regression

Set `ABX_BIN` to an installed CLI executable for the existing provider CLI cases.
Set `ABX_E2E_CLI` to the same executable to enable the native `--json-args` string-array
regression in `test_19_named_string_array.py`. That regression uploads and verifies
this checkout's server source into a fresh tracked sandbox; it does not assume
an updated server is preinstalled. Its fixture polls the owned command catalogue
because platform health can answer before port forwarding is ready.

运行 CLI 用例时，通过 `ABX_BIN` 指定已安装的 CLI；将 `ABX_E2E_CLI` 指向同一个
可执行文件，可启用 `test_19_named_string_array.py` 的原生 JSON 数组回归。
该用例上传并校验当前 checkout 的服务器源码，使用独立、受跟踪的沙箱，
不会假定预置服务器已更新；以命令目录的就绪作为异步端口转发生效的依据。

## Optional real desktop acceptance

Follow the [desktop acceptance guide](../docs/en/guide/desktop-acceptance.md) and
its isolated pinned requirements, then run
`python e2e/desktop_acceptance.py --template "$E2B_DESKTOP_TEMPLATE" --output-dir NEWDIR`.
This is separate from the standard/Provider client suites; real desktop template,
private ingress, traffic token, VNC password and handover/replay prerequisites
remain explicit in the guide.
