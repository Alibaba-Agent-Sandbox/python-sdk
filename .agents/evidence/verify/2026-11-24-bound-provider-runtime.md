# Verification: Explicit Provider binding and runtime preparation

- Date: 2026-11-24
- Change: Explicit Python Provider client on the SDK main baseline a9a572d81847fe99216bf1bb454b91810dacc676
- Result: PARTIAL
- Environment: Python 3.11.15, Linux x86-64 glibc, fixed Node 22.22.2 and OpenSandbox 0.5.1.
  Credentials supplied from an existing private environment and excluded from this record.

## What was verified

Three reviewers ran independent adversarial checks of contract and target routing, artifact
integrity and cache behavior, and the standalone Node path. Initial review eliminated dependency
on ambient SDK/CLI configuration. Implementation review identified bounded preparation, empty
handshake features, unsupported create inputs, and independent shutdown requirements. The third
round checked the corrections and independently reproduced colliding process IDs across two
Sandbox handles, cancelling a close waiter, and closing during in-flight initialization.

## Commands run

- `pytest -q -p no:cacheprovider e2e/test_bound_provider.py`: live Express result 1 pass.
  A tagged sandbox returned the expected command output and file content. The exact sandbox
  was deleted and follow-up get raised the typed NotFound.
- `pytest -q -p no:cacheprovider client-sdk/tests/test_providers/test_bound_client.py client-sdk/tests/test_providers/test_epp.py`:
  development run 38 passed. An initial native fixture misused the Provider object as
  its sandbox protocol. The test was corrected to use a separate protocol object.
- Stock Node and OpenSandbox published archives were retrieved over HTTPS, verified against
  fixed lengths and SHA-256 values, and prepared through the Python API. Independent harness
  runs included a rootless mount namespace masking system Node and a blank caller PATH.
  Cold, warm, and offline all succeeded. The EPP calls covered create, get, list, connect,
  renew, command streaming, files, ports, PTY, delete and absent state against an
  OpenSandbox backend test double. Concurrent streams used the same native process ID.
- The latest complete local test and CI status is recorded in the pull request.

## Cleanup

The real Express sandbox was deleted and verified by direct ID. Standalone component runs reaped
all of their subprocesses and removed temporary workspaces. Test sandbox records were empty.
No database, deployment, key, or image was created.

## Not verified

Live OpenSandbox backend verification requires a reachable OpenSandbox server or a supported
container runtime. No such target was configured in the workspace. The component tests exercised
real runtime and plugin bytes with a backend test double. Release of a signed catalog and automatic
native package installation remains outside the implemented lock-driven path.
