# Verification: multi-agent provider context and SDK architecture review

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
- Result: PARTIAL — SDK ownership fixes verified; broader architecture and conditional capability acceptance remain open.
- Audited baseline: 9df2cc19b974; verification covers the scoped follow-up source changes in this PR.
- Environment: Linux, Python 3.13.13, editable client/server packages. No cloud mutation in these SDK regressions.

## Method and verified fixes

Three agents independently examined architecture/provider semantics, code maintenance and open-source/documentation practices across the CLI and Python SDK. The primary agent integrated the owner-scoped changes. This review does not certify all project repositories or include Node SDK implementation.

Explicit ProviderSandbox selection of alicloud-express previously entered the builtin path but let load_config use another ambient provider. The helper now explicitly loads BUILTIN_PROVIDER_ID configuration. Tests call the actual native create entry with an installed different default and an uninstalled default, mocking only remote protocol creation. Both regressions failed before the fix; both pass afterwards.

Any colon-qualified sandbox reference now resolves a namespace or fails before backend work. Reserved/invalid namespaces and empty IDs fail E8002; valid unknown providers fail E8001. New namespace regressions initially produced seven failures and one pass on each language implementation; the corrected behavior passes. Bare IDs remain unchanged.

Standard Sandbox/AsyncSandbox remain pinned E2B protocol clients. They do not dynamically switch protocol through ABX_PROVIDER. The explicit ProviderSandbox API remains a reasonable extension boundary; the internal context/configuration path still warrants subsequent consolidation.

## Commands and results

- `pytest -q client-sdk/tests/test_providers/test_registry_scoping.py client-sdk/tests/test_providers/test_sandbox_provider.py client-sdk/tests/test_api/test_sandbox.py` — **123 passed**.
- Targeted Ruff lint/format for changed source/tests — **PASS**.
- Full `make lint`, `make typecheck` and `make format-check` — **PASS** for both distributions; mypy checked 56 server and 87 maintained client files, with an unused interpreter override note. Ported/generated exclusions remain declared separately.
- Repository health — **106 PASS / 1 WARN / 0 FAIL** before this new evidence file; the existing warning concerns historical context.
- The complete hosted Python 3.10/3.11/3.12 matrix, build, links, hygiene and 354-shape contract checks passed on baseline 9df2cc1. Follow-up-head CI is still required after push. Signature checks are not complete behavioral compatibility evidence.

## Documentation and future work

Bilingual architecture/design index/API design and the Chinese README now distinguish standard clients, maintained source ports and native provider extensions. They no longer describe the whole SDK as merely E2B-shaped or universally asynchronous. The [provider-context proposal](../../notes/proposed/architecture/2026-10-16-provider-context-and-availability.md) records the owner-specific plan.

Open work includes separating declared features, implemented operations and conditional availability; replayable source import/patch tooling; current-output/provenance verification; and representative wire/behavior drift gates. Do not remove generated implementations simply to reduce code size or treat broad static-check exclusions as proof of maintained patch quality.

CLI-specific defects and its common-operation plan remain owned by https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40. In particular, management registration does not implement missing pause/resume/PTY/template adapters or establish account/runtime enablement. The separate registration work remains at https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38.

## Cleanup and unverified acceptance

Offline regressions did not create cloud resources. Earlier real Express migration evidence and actual conditional pause/snapshot rejection remain preserved. No enabled successful pause/snapshot fixture was available, so this review makes no success or completion claim. Full acceptance, required review and dependency/merge gates remain open; the PR remains draft.
