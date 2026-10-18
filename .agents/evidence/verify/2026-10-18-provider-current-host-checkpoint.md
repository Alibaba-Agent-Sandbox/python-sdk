# Verification: Provider current-host integration checkpoint

- Date: 2026-10-18
- Result: PARTIAL — client and configured cloud pass; final aggregate/hosted gates pending.
- Scope: integration with main `e43a4d8e2e656adf9f25c20c6ef6ea93ab90f142`; provider-owned auth/session/URLs, lazy schema composition, native HTTP creation and no-replay management.
- Owner: Issue #52, PR #38; host dependency https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35.
- Environment: Linux, Python 3.11.15 in an isolated development environment; matching source client/server 0.3.0, Node 22.22.2. Credentials supplied in memory from ignored configuration and never recorded.

## Commands and results

- `make lint format-check typecheck`: PASS for both distributions, 99 client and 56 server modules.
- Initial integrated client: 2171 PASS / 3 FAIL / 24 SKIP. Failures exposed lost custom-auth classification and the no-replay `retry=False` contract when integrating main. Both fixed with the existing negative regressions.
- Complete client after fixes: `pytest tests/ -q --tb=short`: 2174 PASS / 24 SKIP, 143.93 seconds.
- Original `make test` server checkpoint: 847 PASS / 8 FAIL / 1 SKIP. It included intercepted raw HTTP, a readiness race and absent pip in the test environment. pip was installed as a development prerequisite; no production package behavior was changed for it.
- HTTP fixture follow-up: 67 PASS / 2 FAIL in 38.47 seconds. Placeholder Host returned 501 while the same initialized listener's actual authority returned 200. Correct authorities, complete framed reads and initialization waiting preserve assertions. Two intentionally malformed upgrade/chunked requests remain intercepted with 501/502 and require unchanged hosted CI.
- Configured `e2e and not e2e_slow`: 116 PASS / 6 SKIP / 2 DESELECTED / 1 known XFAIL, 424.64 seconds. The XFAIL is existing KI-009 code-interpreter behavior. Skips: unconfigured OpenSandbox/Cube/E2B/container and two non-opted-in Volume cases.
- Catalog plugins were installed with consent and doctor verification into a fresh test HOME before that E2E run; no native credential was inherited by another backend.

## Current implementation

The retired gRPC daemon, native lifecycle wrapper and framing hooks remain removed.
Express selects native HTTP through the same Provider contract as plugins. Its wire URL
helper and auth diagnostics are adapter-owned. Package composition injects schemas;
reading bundled metadata does not discover the registry, and public provider exports
remain lazy. Empty/nonempty Volume creation is tested through the real HTTP wire contract
with an unrelated ambient provider and the retired daemon unavailable.

## Cleanup and limitations

Independent listing after the full cloud suite observed zero total sandbox resources
and zero Python E2E tags. No new Team/key/Volume/Bucket/role/template was created by this
checkpoint. Existing storage evidence is preserved and is not relabeled as a new run.

Final full Server repetition, distributions, health and exact-head hosted matrix/review
remain pending. The intentionally malformed local traffic failures are not converted to
passes or skips. Native unconfigured providers and optional image-factory activation
remain outside verified coverage; the PR stays draft until required gates pass.
