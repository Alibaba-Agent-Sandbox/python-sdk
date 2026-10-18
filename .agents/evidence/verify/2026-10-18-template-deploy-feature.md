# Verification: Independent template deployment metadata

- Date: 2026-10-18
- Change: SDK Issue https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/50
- Base: `0ce8359026028cd4dcf9ee0a7e51493c387f1e25`
- Result: PARTIAL
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

Result remains PARTIAL pending baseline comparison and latest-head hosted CI. The
local failures remain recorded; only an actual complete latest-head CI pass can
provide full-suite success. A focused real-cloud pass does not erase local failures.

## Cleanup

Installer fixtures use isolated temporary stores. The cloud fixture destroys its
owned sandboxes; the independent janitor readback lists none. No native deployment
resource was created.

## Not verified

No native provider image deployment, Python deployment API, hosted MCP endpoint,
public package installation or package publication is asserted. CLI behavior is
tracked separately: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/41.
