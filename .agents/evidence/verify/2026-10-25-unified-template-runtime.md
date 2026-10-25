# Verification: complete template startup candidate

- Date: 2026-10-25
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/107
- Result: PARTIAL
- Package under test: matching editable client/server candidate 0.4.0a1; no PyPI
  publication is claimed.
- Environment: Linux, Python 3.13.13; Express credentials supplied only through
  environment variables. The CI Python-version matrix remains a remote gate.

## What was verified

Specification 5 rejects workflow selection, starts one complete template, preserves
all declared services and resources, and cleans every resolved client on failure.
Provider operations remain independent from application service declarations.

## Commands and results

- `python -m pytest client-sdk/tests/test_workflows/test_launch_contract.py -q`:
  17 passed, shared vectors.
- Focused launcher/model/policy/capability/contract tests: 126 passed.
- Launcher and offline catalog regressions: 57 passed, including multiple services,
  later-service cleanup failure, preparation boundary and generic protocol exposure.
- `make lint`: PASS, both packages.
- `make typecheck`: PASS, 56 server and 99 client modules.
- `bash scripts/check-repo-health.sh`: PASS=106, WARN=1, FAIL=0.
- `python -m pytest e2e/test_managed_template.py -q -ra`: 4 passed in 18.46 seconds.
  Real Express `base` and `code-interpreter-v1`, selected by provider name and built-in
  instance, executed shell commands and confirmed deletion of the owned sandbox.
  This does not test the interpreter API. This initial run preceded the candidate
  version bump and exercised the same new launcher implementation.
- `make test`: server suite 878 passed, 2 failed; it therefore did not start the
  client suite. The separate full client run and full `make e2e` are in progress.
- `make format-check build dist-check`: candidate artifacts built and twine checks
  passed; combined-install verification is still running at this checkpoint.

## Environment failures retained

The same two server tests failed before the launcher changes and on repeat:
`test_upgrade_without_a_key_is_a_400_not_a_hang` received HTTP 501 instead of 400;
`test_transfer_encoding_rejected_in_policy_mode` received 502 instead of 400.
A direct malformed upgrade request to the real loopback server returned plain text
`项目网络审计已关闭`, demonstrating interception outside the server's JSON handler.
The chunked test passed alone; the upgrade test still failed alone. Neither test nor
server implementation was weakened. Remote CI must pass these checks before merge.

## Cleanup

Each of the four native scenarios confirmed the sandbox was absent after context
exit. No template/image was built by Python. The full E2E cleanup report is pending.

## Not verified

Full remote CI, candidate publication, source-template Python application consumption
and any specification 5 catalog-wide cloud matrix remain pending. Historical receipts
were not rewritten or promoted to new-template verification.
