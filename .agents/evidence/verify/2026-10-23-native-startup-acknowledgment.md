# Native startup acknowledgment across the engine

Result: PARTIAL (local correction passes; real OpenSandbox rerun required).

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/88. Actual failure: https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/39941973393 on provider e5ee3ded4c6485e66a7a58b2a8d00a756beedbc7, SDK c8882c29fd6a84fe10f9e6791aeacd1f5c0a5131, CLI 0ae68e8b6e2721d04f715d73618899004097264a. Source/profile build, launch/readiness, CLI application call and Python existing-application call passed. Prepared-image Python startup then timed out waiting for its process acknowledgment. Cleanup completed successfully.

The Node EPP bridge was losing the native `exec.start` process identifier, and Python's engine chunk parser dropped a received `pid`. The project `ProcessChunk` also accepted only integer pids, although native OpenSandbox identifiers are opaque strings. Python now preserves both identifier shapes and timestamps. A real StreamReader regression validates the startup metadata, integer/string identity, empty output and subsequent output/exit, including an exec.run-only internal startup path. No PID is inferred, fabricated or converted from output. The pinned standard E2B clients are unchanged.

Executed locally with Python 3.11:

- Focused workflow operations, process models, workflow launcher and sandbox-server helpers: 56 PASS.
- `cd client-sdk && mypy src/agent_sandbox`: PASS, all 98 configured SDK source files.
- Scoped Ruff: PASS; scoped format and diff checks: PASS.
- Initial pytest commands used nonexistent test filenames and collected no tests; corrected commands above passed.
- An initial mypy invocation from the repository root missed the client configuration, checked 333 including preserved upstream files and reported 341 existing/configuration-exclusion errors; the required configured client command above passed. No upstream sources were changed.

Bilingual API reference and changelog document opaque startup identifiers. The matching CLI acknowledgment fix and a new pinned real OpenSandbox T4 run are still required before claiming prepared-image acceptance.
