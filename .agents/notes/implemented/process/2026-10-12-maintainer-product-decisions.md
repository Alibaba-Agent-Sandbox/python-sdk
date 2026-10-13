# Decision: Maintainer product decisions of 2026-10-12

Status: implemented

The maintainer confirmed four items that were previously left open. They are binding for the CLI port and the Python SDK.

## Decision

1. **Process signals.** `commands.send_signal` and the CLI `--signal` flag accept only 9 (SIGKILL) and 15 (SIGTERM). Any other number raises `ValueError`. envd delivers only those two. Help text and docs (en and zh) say this.
2. **KI-008, KI-009, KI-011 stay platform or environment limits.** SDK behaviour does not change. KI-008 is reported as a `FileOperationError` that names `ABX_HTTP_TIMEOUT`. KI-009 (Jupyter 404, `run_code` falls back to a shell) and KI-011 (ACR push throughput from this host) are unchanged.
3. **Version.** The CLI and the Python SDK stay on 0.3.0 together. The CLI moves from 0.2.0 to 0.3.0 because provider plugins require `cli >= 0.3`. There is no separate major bump for the Node port.
4. **Node versus CPython runtime differences stay.** Examples: `User-Agent` `abx-node-httpx/0.28.1`, `SIGUSR1` starting the Node inspector, `PYTHONUTF8` / `PYTHONIOENCODING` / invalid-UTF-8 argv. Functional behaviour matches. Byte identity is not required for these runtime differences.

## Canonical repositories

Issue templates and docs use these URLs. The organization segment is `alibaba-agent-sandbox`.

| Repository | URL |
|---|---|
| abx CLI | https://github.com/alibaba-agent-sandbox/agent-sandbox |
| Python SDK (client and server) | https://github.com/alibaba-agent-sandbox/python-sdk |
| Node.js SDK | https://github.com/alibaba-agent-sandbox/nodejs-sdk |

The `nodejs-sdk` directory is not created yet. It is a Node.js port of the SDK (not the `abx` CLI). Work starts only after the Python SDK capabilities are complete and the maintainer explicitly says to proceed. Until then, do not scaffold that directory or copy the Python API into it.

## SDK defects found by E2E

KI-001 through KI-007 and KI-010 are fixed in the Python SDK and labeled with their KI ids in the changelog. They stay a separate bug-fix change from the Node port's parity work. KI-008, KI-009 and KI-011 stay platform or environment limits (item 2 above). The same fixes are ported to the Node CLI as their own labeled change, with an allow-list so differential tests do not treat them as parity failures.

## Agents API scope

The earlier cut (25 of 47 official operations, `/v1/responses` out of this release) is **not** confirmed. A separate adversarial inventory decides which operations a self-hosted sandbox can implement, and those are implemented. This note does not settle that list.
