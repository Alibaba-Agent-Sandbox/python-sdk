# Verification: Public developer journey documentation

- Date: 2026-10-24
- Result: PARTIAL — local checks and final CI/public readback recorded below as they complete.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/92
- Scope: bilingual documentation and engineering records; runtime code, template recipes and package versions unchanged.

## Baseline observation
Published CLI 0.4.11 and Python client 0.3.1a1 were exercised against real Express resources. A manually prepared python-hello steps manifest reached READY, then named commands, external HTTP, file hash round-trip, processes and a real PTY passed. The default Docker path lacked a local Docker installation. Initial incorrect --json info and unattended rm calls were corrected according to help; those invocation errors are not classified as product defects.

## Cleanup
Both owned sandbox and template were deleted; independent exact-ID reads reported sandbox not found and template HTTP 404. No list-emptiness inference was used.

## Local checks
- PASS: `bash scripts/check-repo-health.sh`: 106 passes, 1 existing recommendation warning, zero failures.
- PASS: `make hygiene`.
- PASS: published 0.3.1a1 wheel inspection confirms ProviderSandbox.connect/application_client/close are async; close releases connections without killing the sandbox.

## Remaining gates
Record local check results, latest-head CI, public documentation readback, and the post-publication rerun. No post-publication success is claimed here.
