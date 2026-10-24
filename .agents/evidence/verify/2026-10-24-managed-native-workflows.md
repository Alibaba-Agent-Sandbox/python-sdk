# Verification: managed native workflows

- Date: 2026-10-24
- Change: [Issue #95](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/95)
- Result: PASS for the managed workflow and manifest changes. Local environment limitations and untested scopes are recorded below.
- Packages: initial managed live run used matching client/server 0.3.1a2 editable sources on this branch; final candidate is 0.3.1a3, Python 3.12.13.
- Backend: real Alibaba Cloud Express; credentials supplied through environment variables, values excluded.

## What was verified

The public Python workflow launcher accepts provider-native template IDs without requiring an immutable version, executes the declared shell operation and deletes its owned sandbox. The unit cases retain application protocol preflight and reject foreign-provider bindings.

## Commands run

```bash
python -m pytest client-sdk/tests/test_api/test_workflow_launch.py -q
python -m pytest e2e/test_managed_workflow.py -q -ra
make ci
```

## Results

| Scenario | Result | Details |
| --- | --- | --- |
| Focused regression | PASS | 90 workflow/manifest/version tests, including alpha ordering, source metadata and both built-in provider selector forms |
| First live attempt | FAIL | Both native IDs hit reserved provider registration before create; no sandboxes created |
| Live rerun after first fix | PASS | 2 tests in 10.25s: `base` and `code-interpreter-v1`, shell output and exit code checked |
| Final managed live rerun | PASS | 4 tests in 17.63s on 0.3.1a3 source: both templates via string and real built-in Provider object; independent deletion queries |
| Local lint/typecheck | PASS | Server 56 and client 98 source files |
| Local full server tests | FAIL | 877 passed; two malformed raw HTTP cases returned 501/502 (also reproduced on untouched baseline), plus package-list case failed because the uv environment lacked pip |
| Clean baseline raw HTTP comparison | FAIL | Same two failures, 24 passes; unrelated to modified workflow/parser code |
| Build/distribution checks | PASS | Repeated for final 0.3.1a3: both wheels/sdists, twine, py.typed and fresh combined installation |
| Repository health | PASS | 106 PASS, 1 existing warning, 0 FAIL |
| First 0.3.1a3 remote CI | FAIL | Only client MCP version lockstep failed; replaced the duplicated MCP version literal with the canonical package version. Server matrix, pinned public contract and Python-to-Node integration passed |
| Local full client run before final MCP correction | FAIL | 2219 passed, 20 skipped, 10 deselected; MCP version mismatch and two loopback RPC cases rejected by this environment with HTTP 501 |
| Final runtime remote CI | PASS | [40106360868](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40106360868), commit `b2b9757be40df340bc8275386f5c23dbb55fa955`: Python 3.10/3.11/3.12 client/server, distributions, pinned contract and Python-to-Node integration |

## Cleanup

Both live cases exit their owning async workflow context and use a fresh control-plane `get_info_by_id` query until `SandboxNotFoundError`. Other errors do not count as absence. The existing run tracker provides fallback cleanup for only tracked resources. No owned sandboxes remained after the passing run. No new native templates or images were created.

## Problems found

Real testing caught built-in provider re-registration, which mocks did not reveal. Creation now retains the supplied provider selector. The failure is preserved above rather than being counted as a pass.

## Not verified

These tests do not exercise the code interpreter API, all source-template applications, or platform-managed app entrypoints. They do not establish immutable artifact identities. OpenSandbox source launch belongs to the coordinated CLI/provider/template work.

The companion plugin's optional source-placeholder field exposed a compatibility parser bug: alpha sequence numbers had been discarded. The existing `packaging` dependency now performs version comparison. CLI and Python regression vectors include alpha/beta/RC/release ordering. No template-registry version mechanism was introduced.

Second-round independent review also caught malformed placeholder input raising `TypeError` and the real built-in Provider object being registered again. Both now have regressions; the latter was rerun against the real cloud. No arbitrary object is normalized merely because it claims the built-in ID.

Final runtime documentation-link run [40106360855](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40106360855) passed. Local raw-socket RPC failures were not ignored or relabeled as passes; the unrestricted remote provider-engine job passed unchanged. This record-only update does not modify package source.
