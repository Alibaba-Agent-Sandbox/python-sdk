# Decision: Launch managed workflows from native template IDs

Status: implemented

## Problem

The workflow launcher rejected every managed template unless the provider exposed an immutable artifact identity. Platforms already accept native IDs such as Express `base`; this extra restriction prevented a valid operation. Resolving the built-in provider to an object and registering it again also failed its reserved-ID check.

## Decision

Accept the selected provider's native template reference. Preserve provider matching, required operations, startup checks, protocol validation and owned-resource cleanup. Keep unknown artifact digests unknown. Preserve the caller's provider selection and normalize only the actual built-in singleton to its ID, rather than registering it again. Replace the introductory planning-state discussion in both workflow guides with usage examples.

## API Design

No new arguments or state types. `launch_workflow(..., reference="base", provider="alicloud-express")` now supports an existing manifest with `input: managed`. Image workflows still require their existing SHA256 reference. Source builds remain a CLI responsibility.

## Alternatives considered

- Require platform versioning or add a registry version service: unnecessary for creating a native template, and unavailable on these inputs.
- Treat a native ID as an immutable artifact: would make an unsupported content claim.
- Remove operation/provider checks: could dispatch to the wrong platform or imply capabilities that have not been implemented.

## Dependencies

Existing provider registry, workflow planner and resource journal. No package or platform dependency added. The existing packaging dependency supplies prerelease ordering; alpha requirements must distinguish a2 from a3. The CLI adapter's optional source-placeholder metadata is validated and retained in raw manifest data without granting Python preparation operations.

## Test Strategy

Regression tests cover managed create, application protocol rejection, no-HTTP exec, foreign-provider rejection and preservation of the built-in string selector. Real Express tests create both public native IDs, execute a shell command, close the workflow and independently query for deletion. Run the repository CI gates and document the initial live failure plus successful rerun.

## Acceptance criteria

- Native managed IDs can execute the selected declared operation without fabricated versions.
- Invalid provider bindings and application protocols still fail before inappropriate invocation.
- Live tests leave no owned sandboxes and do not claim interpreter API coverage.
- English/Chinese guides, changelog, regression and live evidence accompany the change.

## Evidence

- [Issue #95](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/95)
- [Verification](../../../evidence/verify/2026-10-24-managed-native-workflows.md)
- [Public release verification](../../../evidence/verify/2026-10-24-python-a3-public-release.md)
