# Decision: Verify provider initialization, content updates and Python release candidates

Status: proposed

## Problem

Provider doctor accepted lazy Node clients without executing initialization. Catalog updates
used display versions, so Git content changes could be missed. Installed providers bypassed
SDK compatibility checks at load time. Standalone CI silently skipped the Python-to-Node path,
and publication did not bind a tag, tested wheel pair and public files to one candidate.
Skills also described unavailable PyPI installs and inaccurate plugin trust/consumer boundaries.

## Decision

Await an explicit no-sandbox engine initialization route for Node doctor, closing the local
client on every outcome. Old engines fail with an actionable unverified error. Keep ordinary
runtime clients lazy. Compare provider tree content for explicit catalog updates; use recorded
archive digests only for notices and preserve rollback/consent. Recheck SDK requirements on load.
Add one strict cross-language CI job with public immutable peer commits. Release from matching
version tags after the reusable CI suite succeeds on that same checkout, validate the actual wheel pair, retain artifacts, compare any existing PyPI hashes,
and verify public digests and fresh installation after publishing. Skills use matching public
source archives, accurate consumer scope and direct-build Dockerfile dependencies.

## API Design

`EngineProvider.verify_handshake(config)` awaits
`POST /v1/providers/:provider/initialize`. The companion CLI closes initialized infrastructure
without invoking sandbox lifecycle. Existing CLI 0.4.10 lacks this endpoint and is not claimed
compatible with the new doctor. See the
[CLI engine contract](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md).
No new registry service, package version scheme or cloud health probe is introduced.

## Alternatives considered

- Treating construction of a lazy client as success hides plugin and launcher failures.
- Creating a sandbox during doctor adds unnecessary cloud cost and side effects.
- Comparing manifest versions cannot identify unversioned Git content changes.
- A full language/version matrix or registry service is unnecessary for these defects.

## Dependencies

The Node doctor endpoint requires the companion CLI change before users can verify it.
The cross-language CI core path pins already public CLI and provider commits. Local doctor
integration uses the paired candidate; it is not a claim about the existing public CLI release.
The public source installation recipe pins Python commit
`fee74e631d9cfc3488fd41f853ca6dafc1277784`; it does not contain this unmerged patch.

## Test Strategy

Regress same-display-version content updates, rollback, runtime requirements, absent launcher,
legacy-engine responses, actual invalid Node syntax and infrastructure cleanup without cloud
creation. Test release tag/hash rejection. Run mandatory package checks and candidate wheel
installation; validate the published source recipe independently. Record blocked cloud and
remote gates separately from local success.

## Acceptance criteria

- Doctor never reports initialization without a verified engine response.
- Explicit catalog updates detect changed content and retain consent/rollback behavior.
- Standalone cross-language CI fails when its declared prerequisites are absent.
- Wrong release tags and differing existing artifacts fail before upload.
- English/Chinese docs and product Skills describe executable commands and real scope.
- Required cloud/remote gates pass before merge; no publication is performed by this task.

## Evidence

- [Verification](../../../evidence/verify/2026-10-23-release-readiness.md)
