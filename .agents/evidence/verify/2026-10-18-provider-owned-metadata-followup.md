# Verification: Provider-owned metadata follow-up

- Date: 2026-10-18
- Result: PASS for failing-before/passing-after ownership regression and previously recorded convergence checks. Current-head hosted checks remain the merge gate.
- Tested implementation: `b3db77c1812c4d9a9accbdaa1afdf08f3e222ebd`. Negative-control merged main: `13b214b334b1dba26c46f94feea6f4699d5038cb`.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/66
- PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/67
- Environment: Linux, Node22.22.2 / Python3.11.15. The negative controls use no credentials or real network services.

## Negative and positive controls

Temporary shared clones checked out the actual merged main revisions. Each isolated
process replaced the provider-owned compatibility URL rule with an opaque path and
required the public TransportConfig helper to return that path.

| Owner | Unchanged merged main | Fixed implementation |
| --- | --- | --- |
| CLI | Expected assertion failure, exit1 | PASS, exit0 |
| Python | Expected assertion failure, exit1 | PASS, exit0 |

The probes exercise observable routing, not source-text matching. The committed CLI
regression also preserves literal dollar characters; the committed Python regression
patches the composed owned builder. Neutral-import and async-only port/file refusal
regressions remain unchanged.

## Delivery context and checks

The original isolation PRs #35/#38 merged during parallel completion work. A guarded push
had been rejected rather than replacing another contributor's history. Their source was
retained through ordinary merges; this follow-up uses its own branch/Issue/PR and includes
only the remaining metadata/rule ownership repair, typed neutral contract, translations
and exact dated records. No closed PR was reopened and no protected/default branch was pushed.

Detailed executed checks and real Express acceptance are preserved in
[convergence acceptance](2026-10-18-provider-convergence-acceptance.md). Latest local
full client2178 pass/24 skip, CLI90-pass convergence,907-pass parity ledger, package
checks,114-case capture and cloud smoke are explicitly scoped there. Both-owner health
and hygiene checks were successful; configured-secret scanning ran before each commit.
The earlier fresh storage/persistence acceptance and full116-pass cloud suite remain
at their original tested revisions in [acceptance](2026-10-18-provider-isolation-acceptance.md).

The only subsequent source change is documentation/evidence; required hosted checks must
pass on that final head before either follow-up merges. Native backend credentials/runtime
limitations and the known Jupyter xfail remain disclosed. No package release is claimed.
