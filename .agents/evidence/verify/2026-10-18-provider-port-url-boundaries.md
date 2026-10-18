# Verification: Explicit port and file URL boundaries

- Date: 2026-10-18
- Result: PARTIAL — implementation and targeted regressions pass; final aggregates and hosted checks are recorded separately.
- Scope: accompanying port/file adapter hooks, neutral import facades and fixture repairs on the current-host integration branch.
- Environment: Linux, Node 22.22.2, Python 3.11.15; locked dependencies. Credentials remain in the ignored environment and are not recorded.

## Behavior and verification

Provider-selected port access owns URL/host computation and access headers. Async-only
providers cannot inherit a bundled synchronous address. File URL helpers require an
explicit filesystem adapter hook, including when the session URL uses HTTP. The direct
standalone network API preserves its bundled compatibility behavior through composition.
Neutral Python HTTP/protocol imports no longer eagerly load built-in authentication or wire code.

- Fresh-process import regression failed before lazy facade repair and passed afterwards.
- Python scoped isolation/network/native/sandbox/files: 106 passed.
- CLI scoped isolation/network/files/create/list: 112 passed.
- CLI strict typecheck/build and standalone Linux executable build/version smoke passed.
- CLI executable SHA256: `8797dbe0bf6b1f3ecac8afb28c37aa2f9f1e38263cb26ac1e7cd50a8d65e34ed`.
- CLI capture: 114 cases, zero skipped, 17 documents; new capture, no historical overwrite.
- Python both-package lint and mypy: PASS (101 client and 56 server modules). Commands run from the owning package as configured in the Makefile; a root-level mypy attempt ignored package settings and failed, then was corrected.
- Python client/server wheel builds, twine, py.typed and combined clean installation: PASS.
- npm dry-run package-content validation: PASS using the locked npm 10 task wrapper.

## Checkpoint failures retained

The first post-port Python aggregate had 2173 passed, 4 failed, 24 skipped and 1 teardown
error. One assertion incorrectly expected native addressing for an async-only provider;
that assertion now requires E8004. Three live loopback requests were disconnected by the
local intermediary; a separate API run passed all 372 tests. The live fixture now also
waits for the actual HTTP/PTY thread before accepting intermediary socket readiness.
No production assertions or timeouts were weakened. A final aggregate follows.

The CLI aggregate had 3912 passed, 20 failed, 3 skipped. All 20 failures match the
unchanged main baseline after normalizing the renamed Cube no-PTY case. They involve
intermediary HTTP 501/502, malformed socket framing, TLS/proxy interception or WebSocket
close details. The baseline had 22 failures: the archive-umask and terminal-bridge
regressions are fixed. Hosted CI is still required and is not waived.

The executable combined acceptance had 142 passed, 2 failed, 1 guarded skip; both owned
sandboxes were removed, zero leaked. Both failures were offline region isolation: the
harness inherited ALIBABA_CLOUD_REGION_ID independently of its explicit credential map.
After removing that inheritance, offline acceptance passed 61 cases with one no-resource
leak-check skip. Cloud results and new final validation will be preserved separately.

## Cleanup and limits

No Team, key, Volume, Bucket, role or template was created by these follow-up runs.
Native E2B, Cube, container and OpenSandbox environments are not configured; no native
acceptance or optional image-factory activation is claimed. Current-head CI and real
Express SDK acceptance remain pending this checkpoint.
