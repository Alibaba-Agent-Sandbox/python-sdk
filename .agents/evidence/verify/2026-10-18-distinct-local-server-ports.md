# Verification: distinct local HTTP and PTY ports

- Date:2026-10-18
- Result:PARTIAL; client/cloud/quality/package PASS; six local server baseline restrictions, hosted pending.
- Base:ac3787a; production source unchanged.

Actual failed CI job: [https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39109163353/job/117621358258](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39109163353/job/117621358258).
It reports EADDRINUSE and HTTP1.0/404 for a WebSocket handshake. The exact job
URL is recorded from GitHub metadata rather than inferred from a run number.
Before fix:two deterministic default/explicit port-reuse cases FAIL, matching
the bind collision. After fix:20 actual local listener/policy cases PASS.
Only local allocation retries occur before any listener/request starts; no
mutation is replayed.

Full client:2085 PASS /21 SKIP /10 deselected; two existing warning categories.
make lint typecheck format-check:PASS (80 client/56 server typed files).
Configured Express real cloud:116 PASS /4 SKIP /1 XFAIL /2 deselected; native
OpenSandbox/Cube/E2B/container prerequisites are absent and not called passes.
Known platform Jupyter expression behavior remains XFAIL. Independent janitor
exit0,zero candidates out of zero listed. No resources leaked.
No historical evidence is modified and no cloud pass is inferred from local IPC.

Server full local suite:854 PASS /6 FAIL. The same exact six raw-socket
cases FAIL against accepted unchanged ac3787a in3.98s; their intercepted raw
requests receive the host501 audit-disabled response or no application response.
The production server tree is unchanged. This local suite is not called PASS;
required latest-head hosted Python3.10/3.11/3.12 checks must pass before merge.
make build dist-check:PASS for both sdists/wheels, twine, both py.typed markers
and fresh combined-wheel install/import. Health106 PASS/1 existing WARN/0 FAIL;
hygiene/whitespace PASS. Original local failures remain preserved.
