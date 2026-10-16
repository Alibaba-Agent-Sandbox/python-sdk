# Verification: conditional Express backend capabilities

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
- Result: BLOCKED (backend prerequisites for successful conditional operations)
- Package: current project client, Python 3.13.13, real Express python-hello template. Credentials supplied only through ignored environment configuration.

## What was verified

Attempted real pause and snapshot creation instead of inferring support from the presence of client methods or from the generic Gen2 documentation. These are backend configuration/runtime restrictions; no successful operation is claimed.

## Commands run

A Python probe created its own short-lived sandbox, called Sandbox.pause and create_snapshot, and killed the owned sandbox in finally. A second owned probe confirmed the sanitized service reasons; request IDs and account details were omitted.

## Results

| Operation | Result | Sanitized service reason |
|---|---|---|
| Pause | BLOCKED | HTTP 400, nested code 403: Pause session operation is forbidden; pauseSession is not enabled for this function |
| Snapshot creation | BLOCKED | HTTP 400: sandbox runtime does not support snapshot |

The standard source-port entry points and mocked request contracts remain implemented. A successful pause/resume run needs a function with pauseSession enabled; successful snapshot restoration needs a supported MicroVM runtime and account access. No client fallback silently changes the operation or reports success.

## Cleanup

Both probes killed their own source sandbox successfully. No snapshot or restored sandbox was created by either rejected request. No existing cloud function settings were changed and no unrelated resource was deleted.

## Problems found

Generic Gen2 support is insufficient evidence that every existing function has pause enabled. The migration guide now distinguishes runtime availability from actual function/account settings. The companion CLI uses the same supported service operations: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.

## Not verified

Successful conditional pause/resume and snapshot create/list/delete/restore on correctly enabled fixtures. Keep the ADR proposed and report this prerequisite instead of claiming these paths passed.
