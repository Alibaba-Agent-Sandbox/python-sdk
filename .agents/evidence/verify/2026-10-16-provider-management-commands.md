# Verification: provider management commands

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34
- Result: PARTIAL; required repository/cloud gates remain blocked or failing as detailed below.
- Initial base revision: `bb7881d`; initial checks used an uncommitted scoped implementation.
- Final tested product revision after rebasing: `ae185c2d85724f3fc4d2cd87c233682184b6a2af` on `origin/main` `35da216a300f1e2e84254a1cf4b4a7ea98681505`.
- Package under test: client/server source trees, both version 0.3.0. Existing development environment reused; no dependency or lockfile changes.
- Environment: Linux, Python 3.13.13, Node 22.22.2; compatible Node CLI source engine. No credentials were printed or added to the isolated checkout.

## What was verified

The source changes are `client-sdk/src/agent_sandbox/providers/{manifest,installer,engine_client,commands,builtin,__init__}.py`.
Tests are `client-sdk/tests/test_providers/test_commands.py`, `test_commands_engine.py` and the
scoped built-in feature assertion in `test_registry_scoping.py`. Documentation/records accompany
those files. Manifest descriptors are bounded and included in consent; SDK metadata calls resolve no credentials and SDK invocation calls use the
same explicit provider in route and connection, close their clients, and never replay a
command POST. Three unimplemented standard feature claims are removed.

The opt-in engine tests used a real Node process, authenticated local HTTP and a real
installed temporary Node plugin. They discovered exactly 20 built-in operations, retrieved
a descriptor, executed read/write handlers, required mutation confirmation, and rejected
extra input properties. The plugin made no cloud requests. This proves the local process
contract, not Alibaba Cloud resource support.

## Commands run before rebasing

All commands used the source checkout on `PYTHONPATH` (client and server source directories)
and the existing development tools on `PATH`. When a Make target changes directory,
`PYTHONPATH` was set to absolute source directories before invocation.

| Command | Result | Evidence / limitation |
| --- | --- | --- |
| `python -m pytest client-sdk/tests/test_providers/{test_commands,test_manifest,test_installer,test_registry_scoping}.py -q --tb=short` | PASS | Latest run: 224 passed. Includes schema keyword/property-name distinction and explicit empty sections. |
| `ABX_COMMAND_TEST_BIN='<compatible abx command>' python -m pytest client-sdk/tests/test_providers/test_commands_engine.py -q --tb=short` | PASS | 2 passed initially; also included in the final 226-test run; real local Node engine and temporary plugin, no cloud. |
| Combined scoped suite plus `test_commands_engine.py`, with `ABX_COMMAND_TEST_BIN` set | PASS | Final run: 226 passed in 29.00s. Includes credential-free discovery and explicit region forwarding. |
| `make lint` | PASS | Both packages; latest static run also included the new engine tests. |
| `make format-check` | PASS | Both packages. |
| `cd client-sdk && mypy src/agent_sandbox/` | PASS | 84 source files; repeated after new command API was added. |
| `make typecheck` | FAIL | Stops at untouched `server-sdk/src/agent_sandbox/server/routes_browser.py:75`: unused type-ignore under the current environment. |
| `make test` | FAIL | Server phase: 852 passed, 8 failed; client phase was not reached by Make. Details below. |
| `cd client-sdk && python -m pytest tests/ -q --tb=short` | PASS | 2006 passed, 21 skipped in 159.13s; collected before the opt-in real-engine file was added. The latest schema refinements were verified by the 224-test scoped rerun. |
| `make hygiene` | PASS | No local paths or credential-like strings. |
| `bash scripts/check-repo-health.sh` | FAIL | 105 pass, 1 warning, 1 failure: existing English-only archived OpenSandbox research has no Chinese mirror. New relative links resolve. |
| `make e2e` | FAIL / BLOCKED cloud | 116 skipped for missing credentials/prerequisites, 2 deselected; 2 negative provider cases fail because catalog plugins are not installed in this isolated home. No cloud verification claimed. |
| `make build` | PASS | Both sdists and wheels built. |
| `env -u PYTHONPATH make dist-check` | PASS | Four archives pass twine; py.typed exists in both wheels; both wheels import from the clean temporary installation. The clean rerun avoids source-tree shadowing. |
| `make ci` | FAIL | Hygiene, server lint and formatting passed; existing server typecheck gate blocks the remaining aggregate target. |
| `git diff --check` | PASS | No whitespace errors. |

## Results and existing gate failures

The eight server failures do not touch provider-command source. Raw WebSocket/HTTP framing
cases receive environment-generated HTTP 501 or no expected status, rather than the local
server response. The unconfigured policy compatibility case sees an absent app instance,
and the packages case does not find pytest through its subprocess package listing. These
failures remain visible; no unrelated server code or tests were changed to suppress them.

The full client suite's skips include the existing Node-provider tests, which still look
for a sibling directory named `cli`. The new opt-in tests take an explicit compatible binary
and were run separately without skips. No skipped suite is treated as engine verification.

The isolated checkout did not contain a local credential file and its inherited environment
had no Express API key or Alibaba AccessKey pair. This describes the recorded attempt only;
additional authorized cloud verification with securely supplied credentials remains possible.

A distribution check started before the final rebuild had finished and reported a missing
client wheel. It was repeated after the build completed; only the completed-build check
is used for final distribution evidence.

The first complete pre-commit attempt rejected one new `isinstance` form under its pinned
Ruff version and reformatted an f-string fixture; both were corrected in source. Bandit also
flagged four existing subprocess boundaries in the two modified modules: B404 imports and
B603 calls. Review confirmed the installer uses fixed git argv, a constrained environment and
no shell; the engine launches the user's explicitly selected trusted local ABX_BIN/PATH
executable, not a remote command. Only those four lines received precise Bandit audit
annotations. No hook configuration, check selection or runtime behavior was weakened.

The engineering record stays proposed. The local branch initially inherited three unrelated commits after `origin/main`. The final
rebase excluded that range; the final verification section below records the resulting scope.

## Cleanup

The real-engine tests use temporary HOME/provider directories and request engine shutdown in
fixture finalizers. They create no cloud resources. The attempted cloud suite skipped resource
creation; its Make cleanup target was not reached after the two negative-case failures.
No claim about unrelated pre-existing cloud resources is made.

## Not verified

Real Alibaba Cloud management operations, remote CI's interpreter matrix, required review,
publication/merge, and a fully green repository gate set. Both package builds and clean wheel installation/import checks passed independently of the
aggregate CI gate. Required failures above remain unresolved.


## Final verification after rebasing

The reviewed implementation was committed with all repository hooks enabled, then rebased
with `git rebase --onto origin/main bb7881d feat/provider-commands-20261016`. Fetch resolved
`origin/main` to `35da216a300f1e2e84254a1cf4b4a7ea98681505`. Only the task commit remains in
that range, at product revision `ae185c2d85724f3fc4d2cd87c233682184b6a2af`.
The CHANGELOG conflict was resolved from the fetched main text plus this task's two provider
sections; inherited MCP, uv-workspace and server-loader changes were not reintroduced.
`git diff origin/main..HEAD --name-only` contains exactly the 19 approved task paths.

The initial implementation commit ran the secret scanner and complete configured pre-commit
framework, including pinned Ruff, formatting, detect-secrets and Bandit. All applicable hooks
passed. User identity and hooksPath were supplied for the task command only; no global Git
configuration or hook configuration was changed, and no check was skipped by override.

These checks used the final product revision above and the existing Python 3.13.13 development
environment. Client tests used absolute client/server source directories in `PYTHONPATH`;
`ABX_COMMAND_TEST_BIN` selected the compatible source Node CLI, so the new real-engine tests
were enabled. Distribution checks explicitly removed `PYTHONPATH` to verify installed wheels.

| Command | Result | Final revision evidence |
| --- | --- | --- |
| `cd client-sdk && python -m pytest tests/ -q --tb=short` | PASS | 1944 passed, 21 skipped, 16 warnings in 172.25s. The two new real-engine tests were enabled. |
| `make lint format-check` | PASS | Both packages; all source/test files satisfy the configured checks. |
| `cd client-sdk && mypy src/agent_sandbox/` | PASS | 84 source files. |
| `make ci` | FAIL (exit 2) | Hygiene, server lint and server format pass; unchanged `server/routes_browser.py:75` has an unused type-ignore in this environment. Make stops before later aggregate targets. |
| `make build` | PASS | Both 0.3.0 sdists and wheels built on the rebased source. |
| `env -u PYTHONPATH make dist-check` | PASS | All four distributions pass twine; both typed wheels install together and import from temporary site-packages. |
| `bash scripts/check-repo-health.sh` | FAIL (exit 1) | 105 PASS, 1 WARN, 1 FAIL: existing English-only archived OpenSandbox research lacks its Chinese mirror; recommended release guide is absent. |
| `git diff --check` | PASS | No whitespace errors; working tree clean before recording these results. |

The 16 full-client warnings are from existing integration fixtures whose background PTY
threads cannot bind fixed loopback port 9001 because it is already in use. No unknown
process or pre-existing resource was terminated. They are warnings, not proof that those
PTY fixture paths executed successfully. The provider command tests use isolated temporary
engine discovery and ports and report no failed case.

Full-suite counts differ from the earlier pre-rebase run because the unrelated MCP changes
and their tests were excluded along with the inherited commits. The final table above is
the evidence for the reviewable branch. Required server/health gates remain failing; real
cloud management acceptance and remote CI/review remain outstanding and are not represented
as completed by these local checks. Host-side cloud evidence belongs to the linked CLI Issue
and can be referenced separately when published. This evidence-only update does not change
product source after the tested revision.
