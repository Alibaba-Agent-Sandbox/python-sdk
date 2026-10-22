# Verification: current documentation after compatibility removal

- Date: 2026-10-22
- Scope: contributor entry point, current English/Chinese guides and references, documentation indexes and changelog; runtime code is unchanged.
- Result: PASS for local documentation checks; latest-head remote CI remains required before merge.

## Behavior and sources

The maintainer requested one current project contract. Compare documentation with the merged native method signatures, provider-owned port hooks, official template API, single configuration registry and always-on server policy engine. Remove obsolete import/method/credential aliases, inert retry fields, old template API selectors and base64 transfer routes from current instructions. Standard upstream behavior and immutable historical engineering captures remain separately owned.

The implementation and real-component results are recorded in [original verification](2026-10-22-remove-legacy-compatibility.md) and [merged acceptance](2026-10-22-remove-legacy-acceptance.md). This documentation follow-up creates no cloud resources and performs no release or manual deployment.

## Validation

- PASS: `bash scripts/check-repo-health.sh` — 106 passes, 1 historical warnings, zero failures.
- PASS: `make hygiene` — no local paths or credential-like strings.
- PASS: `git diff --check` — no whitespace errors.
- Reviewed current method signatures, policy token setup, file route ownership and configuration descriptors against the changed documentation. Retired names remain only as explicit rejection/removal descriptions or historical review material.
- The latest-head remote CI and Markdown-link checks remain mandatory; product/cloud results belong to the linked implementation evidence, not to these document checks.
