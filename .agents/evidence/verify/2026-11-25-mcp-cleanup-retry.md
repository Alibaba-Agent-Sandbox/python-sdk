# Verification: MCP cleanup retry and harness preparation

- Date: 2026-11-25
- Result: IN PROGRESS
- Issues: [181](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/181), [182](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/182)
- Candidate: editable client/server0.5.0a0 source, Python3.11.15, Linux.

## Triage and review

Independent CLI/API and SDK reviews confirmed handle/session deletion before failed cleanup and a nonexistent installer command. Round1 challenged cancellation between provider return and registration; registration now has no intervening await. Existing exact-provider ownership and background-task retention remain intact. Public instructions describe behavior; this file contains engineering evidence.

## Local checkpoints

- Initial existing manager/session/HTTP tests:137passed.
- Added cleanup manager/session and real Unix-socket HTTP tests:148passed at the first patch checkpoint.
- Resource rollback and lifecycle/cleanup suite after ownership corrections:104passed.
- Actual missing-binary process launch through Agents routes:1passed,171deselected. Initial test expected the internal runtime_not_installed code; observed public API correctly maps it to sandbox_error. The assertion was corrected to the existing public contract, without changing production error mapping.
- make lint, make typecheck, make format-check:passed (58server and114client source files typechecked).
- Full make test:running; final result appended below.

## Actual HTTP behavior

A real uvicorn process loop and Unix socket carry initialization, DELETE503 after an injected owned-handle failure, POST409 for that closing session, same-ID DELETE200 on retry, then DELETE404. The successful sibling is cleaned once, the failed handle remains until retry, and raw synthetic exception text is absent from the response. Provider failures are controlled test doubles; this is real transport validation, not cloud-delete qualification.

## Environment and failures

The repository has no uv.lock; a frozen sync refused installation rather than inventing a lock. Editable installation then followed the repository's declared development dependencies in an isolated virtual environment. A combined invocation of both packages' pytest directories failed collection because each owns tests.conftest; each package's normal make target is used for full suites.

## Cleanup and limits

The local HTTP listener was stopped in finally; missing-binary tests create no process. Unit handles are synthetic, and no cloud resources were created by these local checks. No package version was changed or released. This is not a claim that all MCP deployment topologies, models or native template startup migration are verified.


## Second review checkpoint

Independent reviewer identified that returned handles could be lost if cancellation occurred before an awaited registration lock. Registration now runs synchronously after the provider returns; regressions deliberately hold the state lock while the provider returns and confirm tracking has already completed. Duplicate borrowed connections retain their own failed close without overwriting owned identity.

The actual Sandbox.kill implementation, unlike a mocked kill handle, closed its provider after a failed remote delete. Both implementations were challenged with a closed-sensitive protocol. The Python SDK now retains the transport until remote acknowledgment and separately tracks completed local cleanup. A close failure after acknowledgment does not issue a second remote delete.169 focused manager/session/API tests passed after this correction and the HTTP protocol guard.

Explicit protocol versions are checked after Origin/auth but before expiry, dispatch or deletion. Invalid/empty versions are refused; valid2025-06-18 and absent header behavior pass. Companion CLI round2 was independently inspected for the same ownership, idle retry and protocol guard semantics. No further blocker was found in those scoped paths.


## Real Express HTTP acceptance

Reproducible harness: `python e2e/verify_mcp_http_cleanup.py` with authorized process configuration. [Sanitized assertion results](mcp-cleanup-retry/express-http.json).

A separate root reviewer ran the edited SDK through real uvicorn HTTP over a Unix socket and the real Express backend. Eight assertions passed: anonymous initialization401; authenticated initialize; tool discovery; create one base sandbox with120-second TTL; execute an actual command through the same MCP session; DELETE200; independent native SandboxNotFound; the deleted session returns404. No fallback deletion was needed. The owned instance was absent, the listener stopped, and no database, image or template was created. This verifies this HTTP session path, not FC deployment or OpenSandbox cloud qualification.

## Full suite initial checkpoint

The original full make test stopped after the server suite:885passed,1skipped,6failed. Five failures occurred in existing loopback HTTP/WebSocket/framing checks; they are retained as observed failures, not converted into passes. The package-list test also failed because the fresh uv environment had no pip module. Installing pip satisfies the baseline test expectation but does not fix the product behavior: the existing packages route ignores a failed pip command and returns an empty successful inventory. This separate defect was reported to the integrator for triage. Client tests run separately because make stopped before them. Namespace retest and final CI are recorded subsequently.

The final lint/typecheck/format gates and paired build/dist-check passed. Fresh client-only and optional-server wheel installations, namespace imports, actual HTTP checks and pip check succeeded. Wheels are candidate build outputs only and were not published.

Official protocol header behavior was independently fetched from https://modelcontextprotocol.io/specification/2025-06-18/basic/transports . The web connector returned401 in this environment; a direct HTTPS read of the official source succeeded. Invalid/unsupported explicit versions require400; negotiated-version fallback explains unchanged absent-header handling.
