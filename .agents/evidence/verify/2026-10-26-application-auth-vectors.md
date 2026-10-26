# Verification: shared application authentication vectors

- Date: 2026-10-26
- Result: PASS for the additive authentication contract
- Change: additive contracts/testing/application-auth-vectors.json and its Python consumer test.
- Environment: Python 3.13, isolated virtual environment; client/server 0.4.0a6 installed from this source. Fixture checks use placeholder credentials only; separate cloud evidence used ignored credentials without recording values.

## What was verified

The fixture covers anonymous access, explicit application authentication and preservation of case-insensitive gateway headers. Runtime SDK code and configuration behavior are unchanged.

## Commands run

- `python -m pytest -q client-sdk/tests/test_api/test_application_auth_vectors.py client-sdk/tests/test_api/test_application_binding.py` — PASS, 52 tests.
- `ruff format client-sdk/tests/test_api/test_application_auth_vectors.py` — PASS.
- `ruff check client-sdk/tests/test_api/test_application_auth_vectors.py` — PASS.
- `make test` with locally adjacent, independently moving CLI/provider checkouts — server PASS (875 passed, 1 skipped); client 2359 passed, 3 skipped, 5 pre-existing provider integration failures. Those optional sibling tests do not use the required engine CI pins.
- Required provider-engine CI scenario with CLI 94a1f90244e7b36e06c4618feaa323c4d056e784 and providers 857a66b3884faeaade01411ec9561987a7aee705 — PASS, 4 tests.
- `make test` in an isolated standalone checkout matching ordinary SDK CI — server 875 passed/1 skipped; client 2339 passed/27 conditional skips/1 transient PTY delete connection failure. The complete affected server-client E2E module reran successfully: 35 passed. Final standalone client full rerun — PASS: 2340 passed, 27 conditional skips in 176.75 seconds. The corresponding standalone server run passed 875 with 1 skip.
- `make lint`; `make typecheck`; `make format-check` — PASS for both packages.
- `make build dist-check` — PASS: both wheel/sdist pairs, twine checks, py.typed and clean combined install.
- `pytest e2e/test_server_http_e2e.py -q` with the E2E credential prerequisite supplied — PASS, 22 actual local HTTP/server tests (initial credential-free invocation explicitly skipped them).
- `pytest e2e/test_standard_contract.py::test_standard_sync_lifecycle_files_processes_and_interpreter -q` — PASS on real Express, 1 test including lifecycle/files/process/interpreter; existing tracker cleanup ran.

## Cleanup

The fixture tests create no cloud resources. The separate real Express standard-contract test used the existing owned-resource tracker and cleaned up its sandbox; HTTP test subprocesses stopped normally. Credentials were injected from ignored configuration, with no values recorded.

## Not verified

No new SDK cloud or model behavior is claimed. PR https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/142 passed all 13 checks at 98642ae6712a5017e187cae7952a2b3c819c1ece: client/server Python 3.10/3.11/3.12, distributions, hygiene, pinned public contract, required provider engine, both public runtime Docker fixtures and Markdown links. Subsequent evidence-only heads still require their own checks/review before merge. Consumers pin the immutable canonical fixture source rather than requiring a workspace checkout.
