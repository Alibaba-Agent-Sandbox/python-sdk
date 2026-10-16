# Verification: Reconnectable Python MCP background tasks

- Date: 2026-10-16
- Change: [Issue #44](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/44),
  [proposed decision](../../notes/proposed/feature/2026-10-16-mcp-background-tasks.md)
- Result: PARTIAL — scoped implementation/cloud pass; local full CI retains baseline failures and remote CI is pending
- Baseline: lifecycle PR #33, `3fd592bc9f1245d2ab49c41a34ba6aea52a03407`.
- Package: source checkout, both Python distributions 0.3.0; Python 3.11, Linux.
- Credentials supplied only through authorized process configuration; values not recorded.

## What was verified

The new Python-only tools retain only explicitly background-task sandboxes, save
bounded logs/atomic outcomes inside those sandboxes and reconnect by an opaque
handle. Native envd process behavior was tested before introducing the supervisor.

## Commands run

- `python -m pytest client-sdk/tests/test_agent/ -q --tb=short`
- `ruff check client-sdk/src/agent_sandbox/agent/ client-sdk/tests/test_agent/test_mcp_tasks.py`
- From `client-sdk`: `mypy src/agent_sandbox/` (project configuration); both-package `make lint typecheck format-check`
- From `e2e`: `python -m pytest -q --tb=short -s test_10_mcp_tasks.py`
- `make ci`, `bash scripts/check-repo-health.sh --quiet`, `git diff --check`

## Results

| Scenario | Result | Actual boundary |
|---|---|---|
| Native real Express Start → close stream/client → new Connect | PASS | Process continued; only subsequent LAST and exit 7 arrived; initial FIRST was not replayed |
| Native Connect after completion | Observed EnvdRpcError | Completed result could not be recovered; this is not a native durable-log claim |
| New task unit/process suite | PASS, 27 tests | Real local subprocesses behind a local sandbox transport substitute; not a provider acceptance |
| Initial new real Express E2E | PASS, 1 scenario, 9.63 s | Owner shutdown, fresh-manager complete BEFOREAFTER/ERR/exit7, byte pagination, new task from external manager, disconnect, confirmed cancellation and saved terminal read |
| Final scoped real Express E2E | PASS, 2 scenarios, 64.72 s | Frozen task runtime and Express CLI; new managers recover logs/outcomes, cancellation confirmed; owned tracker reports zero leaks |
| Full make e2e first attempt | FAIL, 3 scenarios | Missing catalog receipts make two key-isolation tests fail with ProviderNotFound; bare mode-0600 CLI JS without node breaks the CLI scenario; four native-provider skips and KI-009 xfail are preserved |
| Correctly isolated full make e2e | PASS, 114 passed / 4 skipped / 2 deselected / 1 xfailed, 235.61 s | Four catalog installs/doctor exit 0 in temporary configuration paths through existing SDK/CLI patchables; original HOME/global store unchanged; real transports/APIs unmodified; KI-009 retained |
| Actual separate-process task reconnect | PASS, 1 scenario, 10.65 s | A fresh Python process with its own SDK engine connects using the saved handle, recovers complete stdout/stderr and exit 7, then cancellation/cleanup complete |
| Initial separate-process probe | Setup FAIL, owned cleanup PASS | Child inherited a different editable SDK instead of the checked-out source and reported Unknown tool; fixed child source path explicitly before the passing run |
| First E2E harness invocation | Setup FAIL | Wrong relative test-file destination, no scenario collected; corrected before the actual run |
| Final affected agent suite | PASS, 222 tests | Includes 27 task regressions and both Python transports |
| Full client suite | PASS, 2002 passed / 22 skipped / 10 deselected | Earlier iteration with 24 task tests; the final three added boundary/race cases pass in the affected suite |
| Full server suite through make ci | FAIL, 847 passed / 8 failed / 1 skipped | No server source changes; eight failed test identities reproduced on untouched lifecycle baseline in the same environment |
| Full make ci | FAIL | Stops at server tests; not called green |
| Double-package lint/format/typecheck | PASS | Server 56 and client 85 typed source files; final retention guard rechecked under client project configuration |
| Wheel/sdist build and distribution validation | PASS | Final package verification recorded separately below |
| Repository health | PASS, 106 checks / 1 warning / 0 failures | Existing recommended release-runbook warning |
| Hygiene / diff whitespace | PASS | No credentials or workstation paths in scoped tracked content |

The eight baseline failures are two WebSocket upgrade cases, three raw HTTP
framing/body-limit cases, the unconfigured engine policy case, ambiguous-token
policy case, and pip package inventory. Seven encounter platform HTTP 501/network
policy or existing policy assertions; package inventory sees no pytest in this
interpreter layout. The untouched baseline was tested for these eight exact cases,
not misreported as a second complete server-suite run. No unrelated server test,
policy or network restriction was changed.

The first packaging attempt used a test-only environment without the `build`
module and failed before building. The existing workspace build environment then
built and validated both distributions. The final distribution check removes
source PYTHONPATH so its combined wheel-install import proves installed artifacts.

The complete cloud suite's four skips are explicit backend prerequisites:
OpenSandbox health is unavailable, CubeAPI has no explicit authorized URL, the
native E2B API key is absent, and the container-edition domain/key are absent.
They do not establish acceptance for these providers. KI-009 remains the known
Jupyter HTTP 404/trailing-expression limitation. The separate-process scenario
sets the child source path explicitly and uses a new engine socket nonce; no task
handle or output is recovered from the submitting process's Python memory.

## Independent review and corrections

Independent parent-agent source review found a mistakenly duplicated retention
method on SandboxMCPServer; it was removed, leaving only SandboxManager ownership.
Review also requested encoded argv limits and retention-set cleanup: the final
request is capped at 96 KiB before connection, Unicode/quote expansion has negative
controls, and kill/shutdown discard retained IDs. Startup reports actual observed
state; an uncertain submission preserves its chosen handle and reports unknown.
A late start response cannot restore cleared shutdown ownership; the final type
guard stores the ID before cache identity narrowing. Saved record/log/cancel
opens reject symlinks with O_NOFOLLOW. The added race and symlink negative controls pass.
Review is source/process reasoning, not separate cloud or Docker acceptance.
The parent independently reran the later 26-test task suite: 26 PASS in 8.48 s.
A final qualified-provider-handle regression was added after that run: canonical
ownership is retained even when the caller uses a provider-qualified ID, while the
temporary connection is still closed. The final affected suite passes all 222
agent tests, including 27 task cases.

The parent agent independently reran all 24 task regressions using the existing
SDK CI environment and both source directories: 24 PASS in 5.31 s. An earlier
review attempt used a different environment without pytest-asyncio and failed
before executing the async tests; it is an environment failure, not a product
pass or regression. This rerun is local process verification, not full CI or cloud.

## Cleanup

The native probe explicitly killed its one owned sandbox. New task E2E tracked one
owned sandbox, killed it in finally and ran its final tagged sweep:
`leaked_after_cleanup=0`. The final scoped rerun also reports zero leaked owned
sandboxes; an actual janitor dry-run sees zero tagged candidates out of zero listed
sandboxes, and deletes zero. The complete isolated-config make e2e also finishes
with zero tagged candidates out of zero listed resources. Its separate Node engine
is stopped before the temporary configuration directory is removed. The final
separate-process task scenario tracks one sandbox and reports zero leaked resources.
Tasks and their files disappear with the sandbox.

## Problems found

Native process Connect does not provide the durable replay/completed result needed
for this slice. No invented platform endpoint was added. Terminating the task's
owned group does not prove termination of deliberately detached sessions/groups;
use sandbox destruction for complete cleanup. Normal runtime calls still have their
existing renewal semantics; task tools themselves do not renew platform TTL.

## Not verified

Other providers, Windows, hosted multi-user deployment, arbitrary encoded-secret
detection and survival after sandbox expiry/recreation are outside this acceptance.
Original P0 Team/OCI/storage/doctor and complete P1/P2 workflows remain unfinished.

The normal secret hook initially rejected a synthetic API-key fixture whose literal
did not identify itself as test data. It was renamed to an explicit test placeholder;
no real key or hook bypass was used. The affected privacy regression was rerun.

## Source fingerprints

The final source-built client wheel matches each of the five changed agent modules
byte for byte; combined install validation imports from the new virtual environment
site-packages with source PYTHONPATH removed.

| File | SHA256 |
|---|---|
| `client-sdk/src/agent_sandbox/agent/mcp.py` | `819924cd3af8efd8e99c8ae48d01ed797e03249bdf9038b6c26bec5b70956937` |
| `client-sdk/src/agent_sandbox/agent/mcp_http.py` | `dc8bf62a0ab12eee0a1df947209d8e0a1873fb68d1f1c3abace6bc8994bf9278` |
| `client-sdk/src/agent_sandbox/agent/tools.py` | `1572c7c6057974571ece14e98e8532bd5133d7764f7ab2608b8361d444624238` |
| `client-sdk/src/agent_sandbox/agent/tasks.py` | `d5cfc4d5720d305b892215955ad59ddde3ad0da2c233502cda2c7361290f5c5c` |
| `client-sdk/src/agent_sandbox/agent/task_runtime.py` | `2b30490e45ef35c861900e3a92b714b870984ee302dda2dca2851e3a846f93b2` |
| `client-sdk/tests/test_agent/test_mcp_tasks.py` | `12b03d0ae8cf442b0f11558f2d69890ebe3f970800866933f9f40e6541f27641` |
| `e2e/test_10_mcp_tasks.py` | `c8533c46e992e59603826435a4dbee96101b33cf0b9c961851bc0bc7b552b451` |

Original product roadmap: [Issue #45](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/45) remains open.
