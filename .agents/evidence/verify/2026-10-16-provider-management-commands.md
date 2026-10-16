# Verification: provider management commands

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34
- Result: PARTIAL; required repository/cloud gates remain blocked or failing as detailed below.
- Base revision: `bb7881d`; uncommitted scoped implementation reviewed on `feat/provider-commands-20261016`.
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

## Commands run

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

The engineering record stays proposed. The local branch initially inherits three unrelated
commits after `origin/main`; exclude that inherited range when preparing the scoped PR.

## Cleanup

The real-engine tests use temporary HOME/provider directories and request engine shutdown in
fixture finalizers. They create no cloud resources. The attempted cloud suite skipped resource
creation; its Make cleanup target was not reached after the two negative-case failures.
No claim about unrelated pre-existing cloud resources is made.

## Not verified

Real Alibaba Cloud management operations, remote CI's interpreter matrix, required review,
publication/merge, and a fully green repository gate set. Both package builds and clean wheel installation/import checks passed independently of the
aggregate CI gate. Required failures above remain unresolved.
