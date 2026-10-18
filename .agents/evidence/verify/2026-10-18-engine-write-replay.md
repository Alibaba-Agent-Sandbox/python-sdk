# Verification: provider engine mutation replay

- Date: 2026-10-18
- Change: https://github.com/alibaba-agent-sandbox/python-sdk/issues/53
- Result: PASS for the scoped fix; local environment failures and unconfigured providers remain disclosed
- Package: editable client/server 0.3.0 from main 145341d plus the scoped change
- Environment: Linux, Python 3.12.15; local dependencies installed from package metadata (no repository lockfile exists). Credentials never recorded.

## What was verified

HTTP and SSE mutations are not repeated after a transport disconnect. GET/HEAD
keep one recovery before any stream output; explicit 401 rejection can refresh
engine discovery once. A real Unix HTTP socket consumes the complete create
request and closes without sending a response; exactly one operation commits.
The Unix socket avoids this environment's intercepted loopback TCP path.

## Commands run

- `pytest tests/test_providers/test_engine_replay.py -q`: 43 PASS.
- Before fix, the newly added suite produced 34 FAIL / 9 PASS; the mutation
  assertions reproduce the unsafe reconnect behavior. The initial TCP component
  variant was intercepted with HTTP 502 and was replaced with real Unix HTTP.
- Client `ruff check src/ tests/`, `ruff format --check src/ tests/`,
  `mypy src/agent_sandbox/`: PASS (204 formatted files, 86 typed source files).
- Client `pytest tests/ -m "not integration"`: 2099 PASS, 21 SKIP,
  10 DESELECTED, two pre-existing event-loop/subprocess warnings.
- `make ci`: FAIL in unchanged server suite, initially 853 PASS / 7 FAIL.
  One package inventory failure was caused by the uv environment lacking pip;
  installing pip and rerunning that exact test passed. The other six are the
  previously observed intercepted HTTP/WebSocket framing/auth tests. Server
  source/tests are unchanged from main. A full green make ci is not claimed.
- Server Ruff/format/mypy: PASS (91 formatted files, 56 typed source files).
- `make build dist-check`: PASS, both sdist/wheel pairs, four twine checks,
  py.typed and combined installed wheel imports.
- `bash scripts/check-repo-health.sh`: 106 PASS / 1 WARN / 0 FAIL.
- `make hygiene`: PASS.

## Results

| Scenario | Result |
|---|---|
| POST/PUT/PATCH/DELETE across four existing connection errors, HTTP and SSE | PASS; one submission |
| GET/HEAD including lowercase method spelling | PASS; one recovery |
| Confirmed 401 before provider dispatch | PASS; bounded recovery retained |
| Read stream failure after first yielded event | PASS; never replayed |
| Real Unix HTTP server commits POST then drops response | PASS, ordinary and SSE calls |
| Full cloud suite and janitor | Fresh complete repeat: 115 PASS / 4 SKIP / 1 XFAIL / 2 DESELECTED; janitor zero candidates |
| Hosted Python 3.10/3.11/3.12 CI | Runtime head bd548d5: all nine checks PASS, including both full package suites and distribution build |

## Cleanup

Local clients and servers close through fixtures. No cloud resources are created
by regressions. Live suite janitor exited 0: zero tagged candidates, zero sandboxes listed. No cloud leak observed.

## Problems found

Full live run initially lacked installed e2b/container plugins, so two credential-refusal checks failed with provider-not-installed. In a new isolated HOME, real installer consent, integrity and doctor handshakes passed for both local catalog plugins. Repeating only the two failed refusal checks then produced 2 PASS / 6 DESELECTED. The targeted repeat first produced 2 PASS / 6 DESELECTED. A subsequent fresh complete suite with those installed plugins exited 0: 115 PASS / 4 SKIP / 1 XFAIL / 2 DESELECTED in 338.06s. The earlier failed full run remains recorded and is not rewritten as a pass. No native E2B/container credential was used.

Unchanged server HTTP framing tests encounter the environment's intercepted
loopback behavior. First-run missing pip was corrected as an environment issue;
its earlier failure is preserved above. No gate was weakened.

## Not verified

A native catalog provider cloud lost-response scenario is not configured here.
Mock cases establish logic; local socket cases establish real HTTP behavior,
not a native provider pass. Native E2B/container and OpenSandbox/Cube live calls remain unconfigured/skipped; they are not provider acceptance. The actual local engine installer/handshake/refusal and Unix HTTP lost-response components pass. Hosted full package suites and the fresh configured cloud suite pass; review the final record-only head CI before merge.
