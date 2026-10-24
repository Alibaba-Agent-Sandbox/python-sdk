# Verification: Python alpha real-component acceptance

- Date: 2026-10-24
- Result: PASS for the stated non-slow E2E scope; conditional cases remain unverified.
- Product candidate: 18858b6 (0.3.1a1), real cloud plus companion CLI 0.4.11 source 94a1f90; no product code changed after testing.
- Credentials supplied internally from the ignored workspace environment; no values recorded.

## Results

- `python -m pytest e2e -m 'e2e and not e2e_slow' --maxfail=5 -ra --tb=short`: 119 passed, 9 skipped, 2 deselected, exit 0. Covers actual platform, lifecycle, commands, files, code/ports, in-sandbox server, declarative execution, configured provider routes, MCP, local transport and standard clients.
- Skips: four third-party backend configurations absent, two Volume opt-ins absent, one CLI named-string-array opt-in absent, pause template and snapshot allowlist absent. Slow cases were explicitly excluded. None is counted as a pass.
- `python scripts/e2e-cleanup.py --run-id <this-run-id>`: dry-run readback, zero matching resources; no deletion of another run's resources. Fixture finalizers cleaned owned resources.
- Separate platform/lifecycle subset: 15 passed, 1 slow case deselected, exit 0.
- Local full client suite: 2,193 passed, 25 skipped. Separate actual Node doctor factory-close and invalid-syntax cases: 2 passed.
- Local full server: 873 passed, 1 skipped, 2 failed due managed-network 501/502 replacing rejection responses. Both failed again with proxy variables removed. Strict Cube process RPC tests also receive 501/502. These are recorded as blocked local checks; their assertions remain mandatory in remote CI.
- Lint, formatting, typecheck and version/tag/metadata checks passed. Health 106 PASS, 1 recommendation WARN, 0 FAIL; hygiene and staged secret scan passed.

## Delivery boundary

Owner Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/90.
The PR and same-tag publication workflow must still pass normal remote CI. At this evidence commit no PyPI upload has been performed. A successful alpha publication will be verified separately through public metadata, file digests, client-only installation and pip check. No blanket provider/template production claim follows from this run.
