# Verification: Direct application processes without Docker

- Date: 2026-10-20
- Change: application runtime PR https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/75; parent runtime revision `d2073fd471f10913381a43e2167fc31789dbaddc`
- Result: PARTIAL; direct-process scenarios PASS, full FC deployment remains BLOCKED
- Package under test: client/server 0.3.0 source checkout; only tests and documentation changed in this follow-up
- Environment: Linux non-root session, Python 3.11.15, real pgserver 0.1.4 PostgreSQL and psycopg 3.3.6. Credentials supplied in memory from ignored configuration; no values recorded.

## What was verified

Docker is not a prerequisite for application runtime testing. Separate Python
gateway, worker and dispatcher processes drive actual SandboxServer HTTP APIs.
The same HTTP scenario now runs with SQLite and a real temporary PostgreSQL
server: gateway restart, durable idempotency, signed dispatcher/worker invocation,
auth rejection, artifact retrieval, SSE replay and terminal cancellation.
A separate actual cloud sandbox test performs remote shell/file/artifact operations
and verifies owned deletion. These tests use a deterministic model, not a real LLM.

## Commands run

From the Python SDK checkout, using its existing application test environment:

```bash
python -m pytest client-sdk/tests/test_applications -q -ra
python -m pytest e2e/test_10_application_runtime.py -q -ra --tb=short
python scripts/e2e-cleanup.py --all-tagged
make lint typecheck format-check
bash scripts/check-repo-health.sh --quiet
make hygiene
```

The cloud commands use a wrapper which loads only the existing sandbox configuration
into the child environment and masks configured values before writing diagnostic
output. A separate standard AsyncSandbox read-only listing verifies no active
application-proof sandbox remains. The owned sandbox ID is also checked directly.

## Results

| Scenario | Result | Evidence |
| --- | --- | --- |
| Initial unchanged application suite | PASS | 26 passed in 13.09 seconds; no skips |
| Application suite with both HTTP database backends | PASS | 27 passed in 16.97 seconds; no skips; real PostgreSQL included |
| Actual cloud sandbox loop | PASS | 1 passed in 10.68 seconds; deterministic model, actual remote tools |
| Owned-resource absence and standard list | PASS | One recorded owned sandbox absent; zero active application-proof sandboxes |
| Changed test Ruff/format | PASS | Lint exit 0; already formatted |
| Full lint/typecheck/format | PASS | Both distributions; 56 server and 116 client source modules pass mypy; 91 server and 245 client files formatted |
| Initial legacy janitor setup | FAIL | Sandbox-only wrapper omitted legacy ABX authentication; E1001 before listing; no deletion |
| Configured legacy janitor dry run | PASS | Existing ABX configuration supplied in memory; zero candidates out of zero listed, zero deletions |
| Health/hygiene and document links | PASS | Health 107 pass, 1 existing warning, 0 failures; hygiene passes; five changed-document local links resolve |

## Cleanup

The cloud executor killed its exclusive sandbox, the test repeated kill to confirm
absence, and its finally/tracker attempted cleanup. A separate standard-client
check confirmed the same owned sandbox absent and found zero active application
proof resources. No unrelated resources were deleted. Local service processes are
terminated and waited for; temporary PostgreSQL servers stop in fixture teardown.

## Problems found

The earlier report grouped runtime verification and FC container deployment too
broadly. Runtime, PostgreSQL and remote sandbox testing work without Docker.
Documentation now distinguishes ordinary Python processes from container/function
placement and provides direct test commands. Product runtime code is unchanged. The first legacy janitor attempt omitted its
separate ABX authentication configuration; supplying the already available settings
corrected the verification setup and the dry run passed without deleting anything.

This session has no Docker socket or daemon, no usable sudo privilege, no
newuidmap/newgidmap and no subordinate UID/GID allocation for its user. Rootless
Docker prerequisites are therefore missing; merely installing the CLI would not
make containers executable. See the official prerequisites:
https://docs.docker.com/engine/security/rootless/.

## Not verified

Full FC image apply/update/destroy, IAM/private ingress, timer/task behavior in FC,
real LLM calls and a production persistent PostgreSQL binding are not validated
by this direct run. A temporary local PostgreSQL server does not establish durable
managed cloud state. Images may be built in CI or another builder; absent local
Docker does not block these direct runtime tests. The parent application PR stays
Draft until its remaining real-deployment gates are met.
