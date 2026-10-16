# Verification: final provider ownership checks

- Date: 2026-10-16
- Change: source commit a5a2c0c; https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
- Result: PARTIAL
- Environment: Linux x64, Python 3.13.13; editable client/server.

## What was verified

The provider registry rejects unknown/empty qualified references before requests. The built-in adapter no longer inherits all host features and does not advertise generic mount/VPC/custom-domain operations. Standard E2B clients and ProviderSandbox remain explicit, separate contracts.

## Commands run

- Full client rerun: 2035 passed, 21 skipped (169.89 seconds). The run started before the final custom-domain metadata edit; do not treat it as an exact-head final matrix.
- Targeted registry/provider-sandbox/standard contract rerun on the final metadata: 62 passed (11.54 seconds).
- Lint/type/format: PASS (56 server / 86 maintained client mypy files).
- Repository health: PASS=106 WARN=1 FAIL=0.
- Source commit secret hook: PASS. Optional pre-commit framework absent; explicit source checks were run.

## Cleanup

No cloud operations in this review. Local fixtures and temporary homes clean up through existing test fixtures.

## Problems found

A known host feature is not automatically implemented by every provider. The adapter now declares its own set. Account/function/template/runtime prerequisites remain distinct from that static set.

## Not verified

New remote exact-head full matrix, real OpenSandbox full E2E, all conditional backend capabilities, generic provider template adaptation, pending typed registration integration, review/merge/release. Separate management work remains at https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38; no registration-only completion claim is made.
