# Verification: Python 0.5.0a1 publication

- Date: 2026-11-25
- Result: PASS
- Issue: [186](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/186)
- Release: [v0.5.0a1](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.5.0a1)
- Source/tag: `8d9297f7d1a9adddf3710ddcaab914b9e35d3618`

## Source and release gates

PR185 delivered the production fixes. PR187 head `322af90b2ac71e97ec4a268db1659bf255e9809c` passed CI45596378240 and Docs45596378028, was marked ready and merged with that expected SHA. Independent remote GET confirmed the merge. The version tag was independently read back as the merge above; no existing tag was replaced.

[Publish run45597651893](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45597651893) completed successfully on that tag. All paired Python3.10/3.11/3.12 suites, standard contract, Node bridge, both public runtime fixtures, hygiene and package-build gates passed. Publish job139152237666 individually confirms successful tag binding, paired distributions, preserved candidate artifact, existing-file hash preflight, server upload, client upload, and public PyPI hash/fresh-install verification. These upload/readback steps executed; they were not skipped or dry-run.

## Independent public readback

Downloaded all four files through official PyPI metadata and compared the actual bytes with their published SHA-256 values. The sanitized [result](python-050a1/public-readback.json) records those hashes and completed checks.

A fresh temporary environment installed `agent-sandbox-client==0.5.0a1` from `https://pypi.org/simple` with `--no-cache-dir`, then ran the existing `scripts/check_dists.py` client acceptance body outside the repository: standard/Provider/interpreter imports, explicit missing-server registration error, no implicit server distribution, and actual ServerClient HTTP. Installing `agent-sandbox-client[server]==0.5.0a1` then passed exact paired-version checks, command registration and `pip check`.

A second fresh uv environment installed only public `agent-sandbox-server==0.5.0a1` and its dependency, with no pip module. The existing `e2e/verify_package_inventory.py` ran against its real Server SDK HTTP listener: HTTP200 included the installed server and websockets. HTTP probes used an isolated loopback network; package installation used the ordinary public network. Local listeners and all temporary readback environments were removed. No cloud resource was created for publication acceptance.

## Original propagation observations

The first independent no-cache pip attempt saw an older client simple index and could not resolve a1, although metadata/artifact URLs and the release runner's fresh install had succeeded. The second attempt installed the client and passed its HTTP checks, then saw an older server simple index for the optional extra. The third unchanged attempt completed the whole readback. A subsequent anonymous public simple JSON request contained a1 for both packages, with `Cache-Control: max-age=600, public` and `X-Cache: MISS, MISS, MISS`. This is an observed temporary index-visibility difference; it does not establish a particular CDN or proxy root cause. No global pip cache was purged, HOME changed, index substituted or artifact overwritten.

## Boundaries

This release contains the merged MCP cleanup/protocol fixes, harness guidance and pip-independent inventory. It does not activate draft native-template, provider-runtime or managed-application redesigns, update existing sandbox images, or add Python MCP template-build tools. Historical preflight and earlier failures remain unchanged. Real Express cleanup acceptance belongs to PR185's evidence; publication does not repeat cloud/model/FC deployment or claim OpenSandbox cloud acceptance.
