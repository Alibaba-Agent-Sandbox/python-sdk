# Verification: project-independent raw HTTP control

Date: 2026-11-17. Result: PARTIAL — independent environment distinction reproduced; this does not mark the failed managed HTTP tests as passed.

## Scope and execution

The [stdlib-only control](2026-11-17-raw-http-environment/control.py) imports no project modules and starts one temporary loopback ThreadingHTTPServer. Its GET handler returns 200/ok; its POST handler immediately returns413 without reading the request body. Python3.13.13 executed `python control.py` with exit0 in2.60 seconds. It shuts down and closes its server in finally. No cloud resources, model calls or secrets were used.

Actual [result](2026-11-17-raw-http-environment/result.json): raw socket GET received HTTP/1.1 501 Not Implemented, while the same server through stdlib http.client and urllib with ProxyHandler({}) returned200/ok. A raw header-only POST with oversized Content-Length timed out after2 seconds instead of delivering the handler413. These reproduce the relevant raw managed-test symptoms outside the project.

This supports treating raw-transport failures separately from the changed managed Turn projection. It does not identify the network/interception implementation or prove all raw HTTP product behavior correct. The eight failing tests remain FAIL in the managed wire verification; do not weaken assertions or claim a complete suite pass.
