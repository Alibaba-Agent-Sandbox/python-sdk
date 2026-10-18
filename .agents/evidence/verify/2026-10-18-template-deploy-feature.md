# Verification: Independent template deployment metadata

- Date: 2026-10-18
- Change: SDK Issue https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/50
- Base: `0ce8359026028cd4dcf9ee0a7e51493c387f1e25`
- Result: PASS
- Packages: paired editable client/server 0.3.0 from this branch.
- Environment: Linux, Python 3.12.15. Credentials supplied only in process memory.

## What was verified

The old parser rejects an independently declared image deployment feature. The
updated registry accepts it without granting it to old manifests or built-in Express.
Real local installer tests check on-disk receipts, consent and provider discovery.

## Commands run

- Focused new regressions before the production fix: 3 FAIL, 2 PASS; the failures
  are E8014 rejections of `templates.deploy` at parsing/install boundaries.
- Focused new regressions after the production fix: 6 PASS.
- `make lint format-check typecheck`: PASS across both packages (56 server and
  86 client source files typechecked).
- `python -m pytest e2e/test_02_lifecycle.py::test_create_info_and_kill e2e/test_02_lifecycle.py::test_connect_from_second_handle_shares_state -q`:
  2 PASS in 8.34 seconds against real Express using the branch SDK.
- `python scripts/e2e-cleanup.py --all-tagged`: PASS, dry-run; zero candidates
  out of zero listed. No resources leaked from this run.

## Results

The current run verifies metadata compatibility, real filesystem installation,
and preservation of the existing real-cloud lifecycle and shared file state.
Additional executed gates:

- Complete client suite: 2066 PASS, 21 SKIP, two asynchronous subprocess finalizer
  warnings (`Event loop is closed`); exit 0 in 119.32 seconds.
- `make test`: server 854 PASS / 6 FAIL in 319.73 seconds; exit 2 prevents its
  subsequent client command. The client suite was separately completed above.
- `make build dist-check`: PASS; both wheels/sdists, twine validation, both
  `py.typed` markers and real combined-wheel installation/import.
- `bash scripts/check-repo-health.sh`: 106 PASS / 1 WARN / 0 FAIL.
- `make hygiene` and `git diff --check`: PASS.

The six server failures are raw loopback HTTP/WebSocket framing/authentication
checks: two `TestResponsesWebSocket` cases, `TestContentLength::test_valid_still_works`,
`TestPolicyModeFraming::test_transfer_encoding_rejected_in_policy_mode`,
`TestBodyLimit::test_lying_content_length_cannot_exceed_cap`, and
`TestAuthentication::test_ambiguous_x_access_token_rejected`. Instead of the server
response, the environment returns HTTP 501 with a platform network-audit-disabled
message. These required checks remain failed; no network setting was changed and
no gate was bypassed. Full current-head hosted CI remains separate.

The same six exact tests were then executed in a separate untouched accepted-main
checkout at `0ce8359026028cd4dcf9ee0a7e51493c387f1e25`, with its own source paths
selected explicitly: **6 FAIL in 2.94 seconds**, reproducing the same test identities
and platform HTTP 501 responses. No server source or server test is changed in this
PR. This comparison was actually executed; it is not inferred from the feature diff.

Exact reviewed product head `326e142772efce2bf2c4a45cfa1577e1574f54d0`
subsequently passed **all nine hosted checks**: the complete client and server
suites across Python 3.10/3.11/3.12, package build/install checks, hygiene and docs.
Run: https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39087792959.
Independent root review found no blocking defect. This supplies full-suite success
without rewriting the failed local run. The note is accepted for this narrow
metadata change; final bookkeeping-head CI and actual merge state must still be
checked separately before delivery is reported complete.

## Cleanup

Installer fixtures use isolated temporary stores. The cloud fixture destroys its
owned sandboxes; the independent janitor readback lists none. No native deployment
resource was created.

## Not verified

No native provider image deployment, Python deployment API, hosted MCP endpoint,
public package installation or package publication is asserted. CLI behavior is
tracked separately: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/42.
