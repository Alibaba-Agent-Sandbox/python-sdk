# Decision: Real-cloud E2E suite and Definition of Done

Status: implemented

## Problem
`client-sdk` and `server-sdk` are verified by thousands of mocked unit tests, but a mock cannot tell
whether the SDK works with the real platform. Real defects (per-call environment variables dropped,
signals never reaching processes, raw `httpx` errors leaking, async `@sandbox` functions returning a
coroutine string) were invisible to the unit suite. There was also no shared rule for when work counts as
finished.

## Decision
1. **Definition of Done** ([`../../DEFINITION-OF-DONE.md`](../../DEFINITION-OF-DONE.md), English and
   Chinese): done means unit tests, an E2E run against real components recorded in
   `.agents/evidence/verify/`, an ADR in the right state directory, English and Chinese docs and a
   CHANGELOG entry; E2E that cannot run means BLOCKED. Credentials stay in gitignored `.env` files and are
   masked everywhere. Linked from `CONTRIBUTING.md` and the PR template; `make e2e` documents the entry point.
2. **`e2e/` pytest suite** (marker `e2e`; never collected by unit CI): real sandbox lifecycle, commands
   and code, files through envd and through the in-sandbox server, process list/signals, ports and URLs,
   timeouts, declarative `@sandbox`, and the custom-template flow (`DockerBuilder` -> ACR -> official
   template -> sandbox -> server-sdk) behind `e2e_docker`, which self-skips with an exact reason when
   Docker/ACR is unusable. Skips cleanly without credentials.
3. **Tagging and cleanup:** every sandbox/template is tagged (`metadata e2e=<run id>`, template prefix
   `e2e-`), tracked and deleted in finalizers even on failure; `scripts/e2e-cleanup.py` is the janitor.
4. **Known issues as strict xfail** (`known_issue`): each product bug the suite found is pinned by a test of
   the *intended* behaviour and listed in `e2e/KNOWN-ISSUES.md`; fixing the bug flips the test and forces
   the marker to be removed.
5. Makefile targets `e2e`, `e2e-all`, `e2e-cleanup`; `scripts/check-repo-health.sh` exempts
   `DEFINITION-OF-DONE.md` from the "every file under `.agents/notes/` is an ADR" rule.

Files: `e2e/**`, `scripts/e2e-cleanup.py`, `Makefile`, `.agents/notes/DEFINITION-OF-DONE.md`,
`.agents/evidence/verify/2026-10-12-e2e-foundation.md`, `.github/CONTRIBUTING.md`,
`.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`, docs.

## API Design
N/A — this decision does not involve API changes. Entry points: `make e2e`, `make e2e-all`,
`make e2e-cleanup`, pytest markers `e2e`, `e2e_slow`, `e2e_docker`, `known_issue`, and the environment
variables `E2E_SANDBOX_TTL`, `E2E_SERVER_TEMPLATE`, `E2E_RUN_ID`, `E2E_CANARY_PUSH_TIMEOUT`,
`E2E_CANARY_BYTES`.

## Alternatives considered
- **Put the E2E tests next to the unit tests under `client-sdk/tests/integration`** — rejected: they
  would be collected by the unit CI, need credentials, and the per-package layout cannot test the SDK and
  the in-sandbox server together.
- **pytest-asyncio** — rejected: a session-scoped event loop owned by the fixtures keeps sandboxes alive
  across tests and removes a dependency.
- **Mark SDK bugs as skipped or fix them in this change** — rejected: skipping hides them, and the task
  forbids touching `*/src`; strict `xfail` records them and fails loudly when they are fixed.
- **Always run the Docker flow** — rejected: pushing real layers to personal ACR from CI-like environments
  can take hours (about 17 KB/s observed); a canary push decides, with the reason in the skip message.

## Dependencies
`pytest >= 7`, the two packages installed (`make dev`), real credentials, optional Docker and ACR
credentials for `e2e_docker`.

## Test Strategy
The suite is run for real: the fast path and the slow/docker path against the live cloud, with strict
xfails proving the known-issue tests fail for the documented reason. After each run the janitor must show
no tagged sandbox left. Results are in the evidence file below.

## Acceptance criteria
- `make e2e` passes on the real cloud (known issues as xfail), with 0 leaked sandboxes afterwards.
- Without credentials the whole suite is skipped with a clear message; unit CI is unaffected.
- Docker flow either completes or skips with the exact reason (no hang).
- No credential value in any report, evidence file or tracked file.

## Evidence
- [`2026-10-12-e2e-foundation`](../../../evidence/verify/2026-10-12-e2e-foundation.md)
