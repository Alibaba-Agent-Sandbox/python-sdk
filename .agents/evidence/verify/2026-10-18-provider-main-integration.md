# Provider/main integration verification — 2026-10-18

Result: PARTIAL pending real Express acceptance and exact-head CI.

Source: provider isolation622dd4fa and accepted maine43a4d8e, ordinary merge
plus scoped integration repairs. Python3.13, fresh editable client/server packages.

- Full client run:2174 PASS,24 SKIP. Earlier run had one custom-auth mapping
  failure; adding the provider-owned rejection handler fixed it (nine KI regressions
  PASS). Subsequent canonical auth/provider run:531 PASS,23 SKIP.
- Ruff lint/format and Makefile package-scoped mypy:PASS (56 server/99 client files).
- Health106 PASS,1 WARN,zero FAIL; hygienePASS. Fresh build, twine checks, py.typed
  checks and actual combined client/server wheel install/import:PASS.
- First full server run:848 PASS,7 FAIL,1 SKIP,1 teardown ERROR. Six are known
  platform raw-socket/framing/upgrade limitations (including HTTP501 network-audit
  disabled responses). One additional test exposed premature fixture readiness.
  The fixture now waits for its own policy and PTY initialization; focused policy
  follow-up97 PASS. Full rerun is recorded below; failures are never called passes.

No Python gRPC engine, old lifecycle hooks or engine-only bridge fixtures return.
Volume validation/payload coverage uses the real native HTTP contract. Config
metadata remains pure; provider discovery is injected. Root import aliases retain
class/module identity. No default AK/SK token creation route is restored.
Real Express E2E is currently running locally; no cloud secret was uploaded.

Final full client run:2174 PASS/24 SKIP. Final full server run:849 PASS/6 FAIL/
1 SKIP; only the six disclosed platform raw-socket limitations remain, and the
fixture readiness case now passes. Final local real Express E2E:112 PASS,2 SKIP
(explicit Volume opt-in absent),2 deselected slow tests,1 expected recorded KI-009
platform code-interpreter expression limitation; exit0. This is real lifecycle,
commands, files, network, server SDK, declarative and MCP acceptance, not mocks.
Final canonical auth/provider regressions531 PASS/23 SKIP; quality gates PASS.
Wheel builds, distribution validation and actual paired installation/import PASS.
Cleanup dry-run confirmation is recorded separately before merge.

Post-run cleanup dry-run:exit0,zero tagged sandbox candidates and zero remaining
sandboxes listed. No cloud resources remain from this acceptance run.
