# Verification: native Python Provider for Alibaba Cloud Container Edition

- Date: 2026-11-24
- Change: `2026-11-24-alicloud-container-native-provider`; stacked on [PR #167](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/167) at `0f229aa8b28c45f1c2998947acbff9857e411310`
- Result: BLOCKED for ACS/ACK acceptance
- Package under test: editable Client SDK and Server SDK 0.4.0a7 development checkout
- Environment: Python 3.12 on Linux; no Container Edition cluster key or target was available in the existing workspace and SDK configuration

## What was verified

The native Provider is reached by both Python entry points. Contract tests run lifecycle calls, two gateway layouts, separate credentials, versioned connect and timeout, terminal-aware process execution, file I/O and default-context Jupyter. They exercise the SDK HTTP client with a test transport.

## Commands run

- `pytest -q tests/test_providers/test_alicloud_container.py tests/test_providers/test_bound_client.py tests/test_providers/test_registry_scoping.py` from `client-sdk`
- `make lint`, `make format-check`, `make typecheck`, `make build`, and `make dist-check`
- `bash scripts/check-repo-health.sh` and `make hygiene`
- `pytest -q test_alicloud_container_native.py` from `e2e`

## Results

| Scenario | Result | Notes |
| --- | --- | --- |
| Native and private routing, auth, write uncertainty, teardown | PASS | 47 targeted tests including bound and registry regressions. Controlled HTTP backend. |
| Lint, format, mypy, distribution and records | PASS | Both package wheels and source archives build and pass distribution checks. |
| Review round 1 | PASS | Reviewed lifecycle, framing, credential audiences and direct wheel integration against the pinned providers. |
| Review round 2 | PASS | Corrected legacy connect timeout, signaled exits, public Jupyter NDJSON ending, refresh omission semantics and plugin install validation. |
| ACS/ACK E2E | BLOCKED | One targeted test skipped. A cluster endpoint and its sandbox-manager key are required. |

## Cleanup

The local HTTP contract owned no remote resources. The live test skipped before making requests.

## Problems found

The Kruise manager reports a fixed envd version. Framing follows its actual Connect implementation. Older connect routes require an explicit timeout. The Jupyter HTTP response suppresses its internal completion message; the reader processes complete HTTP responses, and errors or malformed JSON are surfaced. A second audit found the bundled selection could shadow install verification of the Node plugin and corrected it.

## Not verified

Real ACS or ACK lifecycle, cluster-specific admission and internet/private ingress, and deployment-side SandboxSet operations. No package publication occurred.
