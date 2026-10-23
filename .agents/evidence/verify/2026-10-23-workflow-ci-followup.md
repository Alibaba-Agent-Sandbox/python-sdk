# Verification: workflow CI follow-up

- Date: 2026-10-23
- Result: PARTIAL pending the next complete CI matrix.
- Runtime source remains 2c7c4dd554d0623143b7e6277faf0019ca3138ee; this follow-up changes regression assertions and records, not production behavior.

The first real Ubuntu matrix run was [39938162377](https://github.com/alibaba-agent-sandbox/python-sdk/actions/runs/39938162377). All server jobs passed on Python 3.10, 3.11 and 3.12, as did hygiene and the pinned standard E2B public contract. Each client job failed only because two wheel metadata assertions still expected the retired empty server extra. Python 3.11 reported 2170 passed, 23 skipped, 10 deselected and 2 failed. Keep the mandatory direct dependency on the matching server; change those assertions to reject the retired extra. Do not restore that compatibility shim.

Local packaging tests initially skipped at module scope because hatchling was absent from the editable environment (isolated distribution builds had still passed). Install the build backend as prescribed in CONTRIBUTING and rerun the real artifact tests: 7 passed. This closes a gap in local verification, not a weakening of CI. Add an explicit model regression for each actual retired build field so moved parity coverage remains attributable: system_packages, python_packages, node_packages, copy_files and custom_commands all raise ValidationError in a complete current manifest. The current application base metadata remains valid.

The final local full unchanged server run reported 873 passed, 1 skipped, 2 failed: raw WebSocket upgrade returned 501 instead of 400 and raw transfer-encoding framing returned 502 instead of 400. The same unchanged server tests passed in all three Ubuntu matrix jobs. No server assertion or security code was modified for these local results.

The final real cloud suite passed: [cloud acceptance](2026-10-23-workflow-real-cloud.md), 120 passed, 8 conditional skips, 2 slow cases deselected, zero failures; post-suite janitor dry run listed no sandboxes. Final distribution build/twine/py.typed/combined-install checks passed after the runtime metadata-preservation change. This verification does not replace the new portable-source OpenSandbox CI scenario or the next latest-head client matrix.
