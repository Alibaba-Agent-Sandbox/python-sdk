# Verification: Defensive complexity cleanup

- Date: 2026-10-29
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/150
- PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/151
- Base: 78f6d8616e3371e01faaabc3313c7328a1f5bf5b
- Result: Source behavior, targeted real-cloud acceptance and the complete remote CI matrix pass. Local environment failures remain recorded below. Final documentation commit and merge still require current-head checks.
- Source and test changes are on an isolated branch; original workspace edits are preserved.

## Checks

| Check | Result |
| --- | --- |
| Focused changed behavior | 199 passed |
| Complete client suite | 2362 passed, 27 skipped |
| Complete server suite | 873 passed, 1 skipped, 2 failed |
| Final lint/format and mypy | PASS; server 56 source files, client 101 source files typechecked |
| Build, twine, fresh combined wheel install | PASS |
| Server packaging after installing hatchling | 5 passed |
| Additional engine tests, fixed provider revision | 18 passed, 8 failed |

Server source and tests are byte-identical to the base. A raw loopback WebSocket handshake expected 400 but received external HTTP 501 with the environment's network-audit-disabled response; transfer-encoding policy expected 400 but received 502 (isolated rerun passed). Do not change product assertions to accommodate interception.

Initial engine expansion used an old sibling provider checkout and failed 15 tests; repeat pinned CI provider revision 857a66b. Of the remaining eight failures, five encountered loopback 501/502; three non-CI expectations drifted from provider behavior (two domain choices, one advertised feature set). These are not included in passing client counts. Missing CLI fixtures and hatchling accounted for some original skips; supplements do not make the whole suite green. The pure-Python synchronous HTTP keepalive test is included in the passing client suite.

## Adversarial decisions

Accepted deletions have observable equivalence or a demonstrated defect: duplicate create target selection, dominated timeout validation, equivalent response defaults, full schemas in normal help, redundant background delegation, per-call event loops, and broad lifecycle catches.

The opposing reviewer caught three regressions before delivery: requiring exec.run as well as exec.stream for background-only providers; synchronous callback self-deadlock; and submitted work surviving Ctrl-C. All three received corrections and regressions. Actual SIGINT independently ran the cancelled coroutine's finally block; sequential, notebook and 12-thread probes reused one event loop.

Retained: ServerClient cross-loop compatibility, endpoint/audience authentication, managed-key preparation consent, ownership-aware cleanup, non-idempotent write replay rules and public configuration exports. No management API key was prepared or renewed. Qualified-ID CLI routing remains a separate unresolved design issue; register deployment and keep_alive handle design were documented, not redesigned.

## Real components and cloud

A source-built CLI and editable Python client used an existing authorized Express API key loaded only into child processes. One owned base sandbox with a 180-second TTL passed: three sequential synchronous literal-argument executions, background shell variable expansion, synchronous file write/read, and TypeScript lifecycle/literal/background checks against that same sandbox. Deletion succeeded. The first independent check mistakenly called instance-only standard is_running as a class method and failed locally; corrected standard get_info returned SandboxNotFoundException, independently proving absence. The verification mistake is not a product failure.

The existing declarative cloud suite additionally passed all six tests: sync/async remote functions, remote exception propagation, borrowed-instance survival, automatic owned-instance deletion and local serializer validation.

Three maintained Python cloud regressions also passed (23 collected, 3 selected, 20 deselected): quoted_operator, background_preserves and sync_connection_reuses. Their owned base fixture performed cleanup. This is targeted Express acceptance, not every provider/template or complete cloud suite.

English and Chinese application registration examples were executed locally: @command() registers demo, which returns hello=1. SDK application examples now use application_client and async context cleanup. Public guides omit internal acceptance statistics and audit timelines.

## Repository records and hygiene

Final repository health: 107 passed, 1 warning, 0 failed. git diff --check passed. Python make hygiene passed; CLI hygiene passed as part of make ci. The first CLI health run found a generated ignored parity report containing local paths; the report was moved outside the checkout and health rerun. No tracked source was exempted.

## Remote CI and remaining gates

Complete remote checks passed for source revision `7499ddf6c6805b50a65afa6e4b9778f5c466d468`: Build packages, server-sdk (Python 3.11), Public runtime fixture (python-hello), client-sdk (Python 3.12), Python to Node provider engine, Pinned E2B public contract, server-sdk (Python 3.12), No local paths or secrets, Public runtime fixture (agents-cli), client-sdk (Python 3.11), server-sdk (Python 3.10), client-sdk (Python 3.10), Markdown links. This independently distinguishes local environment failures from the successful remote matrices. Local failures and prior cancellations remain in history; no network assertions were relaxed.

The final records-only commit must pass its own current-head checks before merge. The ADR describes the implemented change; the PR carries pending merge state. No release is part of this change.
