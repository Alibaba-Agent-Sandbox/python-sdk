# Verification: Complete provider isolation

- Date: 2026-10-18
- Change: proposed ADR `2026-10-18-provider-portability-updates`; Python PR #38, Issue #52.
- Result: PARTIAL — client full suite and real cloud pass; server aggregate has seven failures.
- Revision scope: provider-owned auth/engine/session assembly, structural contracts, compatibility facades and regressions in the accompanying commit; verification preceded this commit.
- Packages: source client/server 0.3.0 plus built wheels/sdists.
- Environment: Python 3.13.13, Linux, real Express cn-hangzhou; credentials supplied through an ignored environment file with values omitted.

## Commands run

```sh
cd client-sdk && pytest tests/ -q --tb=short
make test
make lint typecheck format-check
make build dist-check
bash scripts/check-repo-health.sh
```

## Results

| Check | Result | Scope/limitation |
| --- | --- | --- |
| Complete client tests | PASS | 2151 passed, 24 skipped; 148.69 seconds. Includes ownership/import-boundary and configuration regressions |
| Client and server lint/format | PASS | Both packages; 107 client source modules pass mypy, 56 server modules pass mypy |
| Build and distribution checks | PASS | Both wheels/sdists; twine, py.typed, combined clean-venv install/import |
| Current-source real Express | PASS | Create, exec, write/read, connect, list, deletion; post-delete listing confirms absence |
| Aggregate make test | FAIL | Server: 848 passed, 7 failed, 1 skipped; stops before client, whose full suite was run independently |

## Problems found

The server aggregate failures are Responses WebSocket upgrade token enforcement,
HTTP Content-Length/Transfer-Encoding/body-limit framing, an unconfigured one-engine
assertion and ambiguous X-Access-Token rejection. This patch does not alter server source;
these failures are recorded without claiming their root cause or waiving acceptance.
The draft remains unmerged until required gates/reviews pass.

## What was verified

Provider-owned session binding, URLs, authentication, optional create inputs and resource
cleanup replace the core native/default bypass. Historical public exports remain. The
import-boundary regression prevents concrete backend imports in core implementation files;
explicit composition roots, declarative metadata and public export facades are intentional.
New architecture and configuration docs are available in English and Chinese.

## Cleanup

The real source CLI, standalone CLI and Python smoke each tracked and deleted only its own
new Express sandbox. Post-delete listing confirmed each owned ID absent. No Team, key,
Volume, Bucket, role or template was created by these follow-up smoke runs. Existing
storage acceptance remains the separate 2026-10-16 record and is not relabeled as a new test.

## Not verified

No new native E2B/Cube/container provisioning or optional image-factory activation is claimed.
No full-region/full-capability acceptance, package publication or verified merge is claimed.
The current implementation remains proposed while mandatory aggregate gates fail.
