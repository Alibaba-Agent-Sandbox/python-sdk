# Verification: Provider conditional capabilities — 2026-10-20

Result: PARTIAL — verification in progress.

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

Both directions of pause/resume have passed real memory/file continuity. Fresh-source Snapshot creation through the actual provider command also passed; diagnostic resources were reconciled and removed. Combined pause-then-Snapshot acceptance exposed a service transition rejection; the manual controller only retries definitive409 rejections after reconciling its unique source/name, never ambiguous timeout/5xx mutations. Full combined acceptance and final fixture cleanup are recorded before marking complete. No cloud/model workflow is dispatched from Actions.
