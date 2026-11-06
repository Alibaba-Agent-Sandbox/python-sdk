# Verification: Managed database CA startup argument

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; continuation of runtime `2ee960cb919d640c282cbbeff24d15aa051b7495`.
- Result: PARTIAL — focused local validation passed; latest full gates and actual FC argument readback are in progress.
- Package under test: matching 0.4.0a7 source candidate, not yet published.
- Environment: CPython 3.12.13, psycopg 3.3.8, real local PostgreSQL and SQLite, PID-isolated local CLI fixtures. No credential values recorded.

## What was verified

The deployment continuation identified environment configuration larger than the target FC budget.
Independent review accepted a narrow public-CA startup argument rather than weakening TLS.
`--database-ca-base64` decodes canonical Base64 ASCII with both encoded and decoded size bounds,
rejects a simultaneous existing `ABX_MANAGED_DATABASE_CA_PEM` source, and passes the result to the
existing certificate-only/X509 validator and private temporary CA-file context. No role credential
is added to arguments. Existing environment-only usage remains supported.

The official [CustomContainerConfig reference](https://www.alibabacloud.com/help/en/functioncompute/api-fc-2023-03-30-struct-customcontainerconfig)
defines array startup arguments without a documented size guarantee. The local 64 KiB decode bound
therefore does not establish FC support for a 64 KiB certificate argument. Actual accepted sizes
must be recorded from the specific deployment/readback.

## Commands run

- Client Ruff and format checks for the entrypoint and new command tests.
- `mypy src/agent_sandbox/` in `client-sdk/`.
- `pytest tests/test_managed_entrypoint.py tests/test_managed_agents.py tests/test_providers/test_managed_import_boundary.py -q` in an isolated PID namespace.

## Results

| Scenario | Result | Scope |
| --- | --- | --- |
| Actual command parsing with public CA | PASS | Gateway, Worker and Dispatcher all reach the existing validator and a real 0600 temporary file, removed after startup returns. |
| Environment compatibility and conflict | PASS | Existing environment source still works; a present source, including an empty one, conflicts with the argument. |
| Malformed encoding/ASCII/size | PASS | Static parser errors without echoing the supplied value; noncanonical Base64, non-ASCII content and oversized input rejected. |
| Invalid PEM/X509 and cleanup on startup failure | PASS | Other PEM types and invalid certificates rejected; an exception during startup removes the temporary file. |
| Focused command/managed API/import regression | PASS | 57 tests, zero skipped, 26.81s. Includes 16 new command cases and the preceding 41 scenarios. |
| Full client mypy | PASS | 114 files. |
| Latest complete local/remote CI | IN PROGRESS | Separate results will identify the exact tested commit. |
| Actual FC creation/startup argument readback | PENDING | No cloud argv-size or successful joint deployment claim is made here. |

## Cleanup

The new command tests start no cloud resource. Their public certificate files are created in
private temporary directories and are checked absent after both normal return and startup error.
The real local database and CLI fixture teardown remains unchanged.

## Problems found

The former CA environment-only transport can exceed a constrained deployment's environment
budget. This optional argument changes transport only; `sslmode=verify-full`, explicit libpq
CA configuration and certificate validation remain intact.

## Not verified

No new package is published. The preceding CI wheels predate this additional flag and cannot
stand in for its final distribution. A new exact CI artifact and actual FC readback are required.
Models/providers in the local regression remain fixtures; its real PostgreSQL/HTTP/process
components do not imply a real-model FC active-cancellation acceptance.
