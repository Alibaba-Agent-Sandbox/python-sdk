# Verification: packaged Python installation guidance

- Date: 2026-10-24
- Change: [Issue #101](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/101), based on `8b77f789111a92713de51573cbb7e8ff7411e9c4`.
- Result: PASS for local packaging and document changes; public a5 publication is not included in this result.
- Packages: matching 0.3.1a5 client/server built locally on Python 3.12.

## What was verified

The actual wheel METADATA and source-archive README for both distributions contain corrected prerelease installation instructions and no old a2 pin. Client metadata requires exactly `agent-sandbox-server==0.3.1a5`. Apart from the version declarations, application runtime code is unchanged from the real proxy-tested a4 candidate.

## Commands run and results

- `python -m pytest client-sdk/tests/test_release_validation.py client-sdk/tests/test_packaging.py -q`: 9 passed in 3.85 seconds.
- `python -m pytest server-sdk/tests/test_packaging.py -q`: 5 passed in 0.74 seconds.
- `make build dist-check`: passed; both wheel/sdist pairs, twine, py.typed and combined clean installation/imports.
- Inspected each wheel's METADATA with `zipfile` and `email`, and each sdist README with `tarfile`: matching a5 versions and dependency, corrected descriptions in all four artifacts.
- `git diff --check` and repository health passed (106 PASS, 1 existing warning, 0 failures).
- Initial [CI 40112322302](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40112322302) failed hygiene because the new guide creates and activates `.venv`, which matched the broad virtualenv assumption guard. Added narrowly anchored allowlist entries for that exact activation command in the two installation guides; the environment is explicitly created immediately above. The guard itself and credential rules are unchanged. Corrected `make hygiene` passed; current-head full CI and links remain required before merge.

## Preserved publication history

[a4 publication run 40111654824](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40111654824) was intentionally cancelled during validation after the stale packaged instructions were found. Its Build & Publish job ended cancelled with an empty steps list: no upload step executed. Both exact a4 PyPI JSON endpoints returned 404 at readback. The immutable `v0.3.1a4` tag remains at `8b77f789111a92713de51573cbb7e8ff7411e9c4`; release metadata clearly says it was not published to PyPI. Cancellation is not a test pass.

## Real runtime evidence and limits

[OpenSandbox T4 40110372103](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40110372103) verified the unchanged runtime through default/direct, portable/direct and default/proxy application paths with independent cleanup. This documentation/package correction creates no cloud resources and does not repeat that cloud test. Public a5 readback and the complete template matrix remain separate follow-up gates; no all-template or real-model claim is made here.
