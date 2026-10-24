# Decision: Publish an explicitly verified Python alpha pair

Status: implemented

## Problem

The reviewed runtime fixes remain local while publication does not use the repository's configured PYPI_API_TOKEN. The old release runbook also describes obsolete branch dispatch and OIDC-only behavior. A 0.3.0a1 package would fail existing catalog sdk >=0.3 compatibility requirements.

## Decision

Prepare client/server 0.3.1a1, preserving all four version bindings and existing compatibility rules. Publish through GitHub Actions with the repository secret, same-tag reusable CI, preserved candidate files, preflight hashes and server-before-client upload. Verify public hashes, client-only installation with automatic matching server and pip check. Keep the alpha explicit and distinguish package release from whole-project production acceptance.

## API Design

No new product API is introduced here. The earlier provider initialize contract requires the companion CLI 0.4.11 delivery; unsupported older hosts fail clearly. Add permanent real Node doctor checks to the strict cross-language job, including factory close and invalid module failure. Correct package README examples to public standard command/file APIs with cleanup and portable document links.

## Alternatives considered

0.3.0a1 would correctly fail existing provider minimum versions. Relaxing those checks would hide a mismatch. Copying the token into this workspace is unnecessary because it is already a repository Actions secret. Trusted Publishing is optional and not assumed configured. No new release service or version database is needed.

## Dependencies

Owner Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/90.
Companion CLI: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/126.
Provider integration: https://github.com/Alibaba-Agent-Sandbox/awesome-providers/pull/28.
The candidate extends the previously reviewed ddc96d8 commit on public main fee74e6. Runtime fixes, release metadata and scoped acceptance must pass required remote checks before release.

## Test Strategy

Run full client/server tests, lint/type/format, lockstep checks, actual Python-to-Node doctor, paired wheel installation and fresh PyPI readback. Run existing real-cloud E2E with owned-resource tags and cleanup. A managed-network HTTP 501/502 is recorded as a failure/block locally, never reclassified as passing; the same tests remain required in normal remote CI.

## Acceptance criteria

- Same prerelease version in both distributions, dependency and MCP metadata.
- Configured token used only by authorized upload steps, with no secret output.
- Same-tag CI and exact candidate checks precede upload.
- Actual doctor initializes and closes the real plugin without cloud lifecycle calls.
- Public files and fresh client-only installation prove the delivered pair after upload.
- E2E scope, skips, cleanup and remaining whole-project gates are explicit.

## Evidence

See [verification](../../../evidence/verify/2026-10-24-python-alpha-release.md). Remote CI, PR review and publication status are recorded on the linked owner Issue and PR; local build alone is not a published release.

## Implementation

Delivered in [PR #91](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/91); actual merged state was checked on 2026-10-24. Later acceptance and current limitations are indexed in the [current synchronization record](../../../evidence/verify/2026-10-24-current-docs-and-records.md). Earlier verification files remain unchanged and retain their original pending or failed observations.
