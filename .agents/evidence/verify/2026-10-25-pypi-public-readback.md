# Verification: bounded public PyPI readback

- Date: 2026-10-25
- Change: [Issue 114](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/114)
- Tested base: dab0e3194e3f790fab28307d9fd126b8239bcbd7, plus scoped workflow/checker/tests changes.
- Package under test: client/server 0.4.0a2, official PyPI; tag/version unchanged.
- Environment: Linux, Python 3.11; no cloud credentials or resources needed.

## Original failure and real public verification

Original publication run [40198182884](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40198182884)
attempt 1 uploaded server at 13:45:37–40 UTC and client at 13:45:42–45 UTC.
Metadata returned HTTP 404 from 13:45:45 through 13:46:26. At 13:46:38,
pip still listed versions only through 0.4.0a1 and could not install exact 0.4.0a2.
This was a post-upload verification failure, not a rejected upload.

- PASS: rerun-failed-jobs, attempt 2, completed SUCCESS with unchanged tag/artifacts.
- PASS: downloaded original `python-release-candidate` artifact 12601415310;
  `python scripts/check_release.py published` matched both wheels and both sdists
  against actual PyPI filenames/SHA-256 digests.
- PASS: fresh venv, `python -m pip install --no-cache-dir --index-url https://pypi.org/simple agent-sandbox-client==0.4.0a2`.
- PASS: `python -m pip check`; both installed distributions are exactly 0.4.0a2.
- PASS: imports and callable checks for Sandbox.create, AsyncSandbox.create,
  ProviderSandbox.create and agent_sandbox.server.start, outside the checkout.
- No cloud resources created; no cleanup required. The real readback did not need
  to induce a second propagation delay; controlled shell regressions cover that path.

## Regression and owner checks

- PASS: `pytest client-sdk/tests/test_release_validation.py -q`: 11 tests.
  The maintained workflow shell executes with controlled external commands:
  metadata-404 recovery, installation recovery with visible errors, six-attempt
  exhaustion, immediate metadata/digest-verification failure, and no retry of
  pip-check/import failures. Original filename/hash mutation regression remains.
- PASS: the actual patched final workflow shell executed against the original
  artifacts and official PyPI, then created a fresh environment, installed, checked
  dependencies and public imports (exit 0).
- PASS: `make lint typecheck format-check`; both distributions checked.
- PASS: repository health 106 PASS / 1 warning / 0 failures; hygiene PASS.
- PARTIAL: `make test` server run: 873 passed / 1 skipped / 2 failed. Raw
  loopback HTTP probes expected 400 but observed 501 (missing WebSocket key)
  and 502 (chunked framing). Repeating with loopback NO_PROXY made framing
  pass; missing-key upgrade still returned 501. No server implementation is
  changed by this patch. The original a2 same-tag official CI/release rerun passed.
- PASS: client full suite: 2261 passed / 27 skipped (124.73 seconds).
- This head's remote CI and independent review: pending before merge.
