# Verification: current workflow documentation and Python matrix

- Date: 2026-10-23
- Result: PASS for the executed Python matrix and current documentation scope; new portable OpenSandbox execution remains a separate Provider gate.
- Owner Issue: https://github.com/alibaba-agent-sandbox/python-sdk/issues/88.

The [latest runtime/test matrix](https://github.com/alibaba-agent-sandbox/python-sdk/actions/runs/39939204599) at 270a7a8fa72656653b485403273491fd99aeefc8 completed successfully: client and server jobs on Python 3.10/3.11/3.12, pinned standard E2B public contract, hygiene and distribution build. This follows the failed historical run whose only client failures expected the removed empty server extra. The current assertions reject that shim, and the real packaging suite passed 7/7 locally with hatchling installed. Local unchanged raw server handshake/framing failures are documented separately; no server test was relaxed, and all three remote server jobs passed.

## Current documentation corrections

Update 12 English/Chinese current pages: template-system, server-api, provider-opensandbox-mapping, provider-authoring-evaluation, providers-and-credentials and api-reference. Remove old template-v1 examples/default grants, invented launch/package/inheritance guarantees, broad interpreter authorization and claims that a guessed platform route or image name establishes SDK support. Preserve main section anchors and actual server endpoint-policy details. The historical authoring evaluation remains marked historical, with its optional interpreter-to-shell suggestion explicitly rejected; immutable engineering evidence and source history are untouched.

Current pages explain specification 4 / operation contract 1, explicit input/startup/profile selection, immutable identities, exact stateless/default/context/stream operations, separate native/adapter/client layers and scoped provenance. API reference includes mode, application_client and exact protocol discovery. The source-root context example is a quoted string so YAML consumers agree. There is no restored legacy runtime translator or compatibility alias.

## Checks

- PASS: 141 local Markdown targets and fragments across all 12 changed pages.
- PASS: independent documentation pass for the template-system/server-api pair in both languages: 107 local targets/fragments.
- PASS: `bash scripts/check-repo-health.sh`: 106 passed, 1 existing missing-release-runbook recommendation, 0 failed.
- PASS: `make hygiene` and `git diff --check`.
- PASS: explicit retired-build-fields model regression: 14 model/ref tests; unsupported actual old fields fail rather than disappearing. This is test coverage of behavior already in the verified runtime, not a newly introduced compatibility translator.

This follow-up changes prose and engineering records only. The real-cloud [120-pass run and zero-residual dry run](2026-10-23-workflow-real-cloud.md) applies to unchanged production code. Catalog/document aggregation must consume this new source revision rather than publishing older contradictory current design text.
