# Verification: bundled provider updates and Express adoption

- Date: 2026-10-18.
- Result: PARTIAL; changed installer/CLI behavior and static checks pass, mandatory full server gate fails.
- Base: b91a1a162b8c02f386d182a21b00e06a363a12d1 plus scoped installer/CLI/tests/docs/record changes.
- Environment: Linux, Python 3.13.13, isolated development environment with both editable packages and declared extras. No cloud credentials supplied.
- Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/52.

## Commands and actual results

| Check | Result | Evidence and limits |
| --- | --- | --- |
| `cd client-sdk && python -m pytest tests/test_providers/test_installer.py -q --tb=short` | PASS | 95 tests, including no-receipt bundled guidance, ref rejection, actual CLI JSON, Git/catalog/pin/rollback behavior. |
| `make lint format-check typecheck` | PASS | Both packages; mypy checks 56 server / 87 client files. An initial isolated environment lacked optional dependencies; installing the repository's declared extras resolved those setup errors. |
| `make ci` | FAIL | Server phase: 849 pass / 6 fail / 1 skip, 322.36 seconds, Make exit 2. Six raw HTTP/WebSocket/policy framing cases encounter environment-generated HTTP 501 or incompatible local responses in untouched server code. Later client/build/dist phases were not reached. |
| Repository health | PASS | 106 pass / 1 historical warning / zero fail. |
| Scoped links, diff and configured-secret scan | PASS | No source outside the intended change; no secret values in records. |

The new documentation distinguishes keeping existing Express resources from E2B import/config/API compatibility. Built-in update reports bundled ownership and matching client/server/Node upgrade guidance; it does not install software, contact a catalog or claim a latest-version check. No public package availability, native factory activation or zero-change migration is inferred.

## Additional validation and limits

The independent complete client run used a unique test-owned Unix socket: `cd client-sdk && ABX_ENGINE_SOCKET=<owned isolated socket> python -m pytest tests -q --tb=short`: **2141 PASS / 24 SKIP**, 155.40 seconds, exit 0. Skips remain skips; no native-cloud or newly enabled engine path is inferred. The server failure remains blocking despite the client pass. Native cloud acceptance in the existing provider-volume-live record remains historical; this follow-up creates no cloud resource and changes no existing Team, key, template or sandbox. Optional provider host/schema work is separate and cannot be declared released from this branch. The shared Node host still lands before its consumer.

## Accepted-main integration

Accepted main `145341d` is retained by normal merge. Conflicting record indexes retain both entries. Builtin feature declarations use explicit implemented support instead of inheriting new registry names; management commands remain present, and unsupported domain/storage/VPC/deployment features are not granted. CLI retains main's conservative pause declaration. Current integrated validation results are recorded separately from the earlier full aggregate above.

Final integrated client validation after main 145341d: **2147 PASS / 24 SKIP**, 143.85 seconds, exit 0, using a separate owned Unix socket. Both-package lint/format/typecheck pass again (56 server / 87 client source files). `templates.deploy` parsing/consent remains supported without granting the builtin a factory. This does not convert the earlier full-server aggregate failure into a pass.

Final integrated repository health: **106 PASS / 1 WARN / 0 FAIL**.
