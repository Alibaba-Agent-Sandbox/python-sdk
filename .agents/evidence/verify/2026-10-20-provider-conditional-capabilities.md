# Verification: Provider conditional capabilities — 2026-10-20

Result: PASS for provider registration, real cross-consumer acceptance and cleanup; full local restricted-network suites remain PARTIAL and required hosted gates are verified before merge.

Source bases: CLI73d5ee3 and SDKbb83123. Scope: provider registration and one backend implementation, generic consumer regressions and local manual E2E, bilingual docs, owner guidance and records. No cloud/model Actions invocation. Full results and cleanup are recorded before merge.

## Local source verification

- Node22.22.2/Python3.11.15; CLI lockfile installation and fresh paired SDK source install.
- Provider wire/schema/error/disposal regression group:118 PASS. CLI typecheck PASS; ESLint0 errors/253 existing warnings.
- Python client2194 PASS/23 skipped/10 integration deselected; lint and mypy both packages PASS; format check PASS. Actual Python -> standalone Node engine discovery/invocation tests:2 PASS.
- CLI full local source run after required build:4033 PASS/20 FAIL/1 SKIP. The failures concern constrained loopback/proxy/raw TCP/TLS/WebSocket behavior outside the changed provider handlers. Initial pre-build run additionally failed on a missing generated dist entry; preserve both attempts. Hosted complete Node20/22 CI remains required.
- Server full local run858 PASS/2 FAIL; a pip-list failure was resolved by installing pip into the fresh uv environment and rechecking. The remaining unchanged malformed WebSocket upgrade case returns501 rather than expected400 in this environment. Hosted complete Python matrix remains required; no checks are weakened.
- SDK health106 PASS/1 historical WARN; CLI health106 PASS/11 historical WARN; both hygiene checks PASS.

## Real component acceptance in progress

A unique generation2 fixture was created through the actual CLI from the public runtime-v2/base image, CPU2/2048MB/15360MB, and reached ready. Credentials remain local. A first controller run passed discovery and cross-consumer pause/resume but its binary path was removed by a concurrent build; owned sandboxes/Snapshots were independently cleaned. A fixed standalone artifact is now used (SHA256a1558673f11691d108e4f88e32b0ed1832a7098cc439eaa3b73d0de3639845d9).

Both directions of pause/resume have passed real memory/file continuity. Fresh-source Snapshot creation through the actual provider command also passed; diagnostic resources were reconciled and removed. Combined pause-then-Snapshot acceptance returned HTTP503 and was not credited as a pass; the manual controller only retries definitive409 rejections after reconciling its unique source/name, never ambiguous timeout/5xx mutations. Full combined acceptance and final fixture cleanup are recorded below. No cloud/model workflow is dispatched from Actions.

## Final real acceptance

Standalone binary SHA256a1558673f11691d108e4f88e32b0ed1832a7098cc439eaa3b73d0de3639845d9, built from this PR runtime source. Manual command: `python e2e/provider_conditional.py --abx "$ABX_BIN" --template "$E2E_SNAPSHOT_TEMPLATE" --env-file .env --report provider-conditional-report.json` (from the Python owner). The CLI/Python engine use an isolated profile; no existing developer engine or cloud template is modified.

All six recorded scenarios PASS:
1. Actual standalone CLI and actual Python engine client return identical provider descriptors.
2. CLI pause / Python resume preserves an in-memory random token and file.
3. Python pause / CLI resume preserves the same memory token and file.
4. Python Snapshot creation / CLI restore: pagination/list, memory/file state, clone isolation and deletion.
5. CLI Snapshot creation / Python restore: same checks in the other direction.
6. Independent API404 readbacks and source-filtered Snapshot lists prove zero owned residuals.

The first immediate post-resume creation returned HTTP503; it was not automatically replayed or counted as success. A fresh final run waited for running state plus a30-second quiet interval before its first Snapshot creation; it completed with no busy retry. This interval is test stabilization, not an advertised cloud SLA. The final controller is the checked-in Python E2E source. Earlier failed receipts remain preserved externally; no merged history is rewritten.

Independent final cleanup read: own live sandboxes0, complete Snapshot list0, exact newly created fixture template HTTP404. Known diagnostic Snapshot results were also reconciled by their owned names/IDs and deleted. No existing user resource was deleted.

CLI source mappings follow the pinned standard generated API for pause, connect, sandboxes/{id}/snapshots, snapshots pagination and template-route Snapshot deletion. The standard compatibility frontend, fixed native feature tokens and protocol are unchanged. No catalog plugin/registry schema/UI edit is required: documentation aggregation continues to consume owner sources.

## Delivery gates

CLI PR: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/79
Python PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/73
Issue: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/78
Latest-head hosted source/test/docs gates are read back before normal SHA-pinned merge; a draft or queued run is not a completed merge. This record does not claim npm/PyPI publication or a new released CLI version. The original v0.4.0 binary predates the new registration; use a containing CLI build.
