# Decision: Accept independent template deployment metadata

Status: implemented

## Problem

An image-only provider template factory cannot declare deployment separately from
legacy image building. The Python manifest validator rejects `templates.deploy`
with E8014, preventing installation even when a CLI host implements that factory.

## Decision

Add `templates.deploy` to `FEATURES` and `ProviderFeature`. Keep manifest feature
selection explicit and preserve existing `templates.build` declarations. The
built-in Express provider excludes the new flag because registering metadata
does not implement an image deployment factory.

## API Design

Provider manifests may declare `templates.deploy`, independently or together with
`templates.build`. Parsing, installer consent and provider discovery preserve the
explicit declaration. This change adds no Python deployment method, cloud endpoint
or automatic feature inheritance. CLI factory behavior is owned separately.

## Alternatives considered

- Reuse `templates.build`: conflates image building with image-only deployment.
- Enable the flag for all built-in features: would advertise an unimplemented factory.
- Add a Python image deployment API: exceeds the metadata compatibility change.

## Dependencies

- SDK Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/50
- CLI dispatch: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/42
- Registry metadata: https://github.com/Alibaba-Agent-Sandbox/registry/pull/5
- CLI/provider consumers must implement and verify dispatch before declaring it.

## Test Strategy

Demonstrate old-host rejection, then verify manifest parsing and real filesystem
plugin installation, consent and discovery for legacy build and opt-in deployment.
Verify Express keeps legacy build without deployment. Run both packages' existing
checks, build/install checks and a real Express lifecycle/connection smoke with
owned cleanup. Native template deployment is outside this schema change.

## Acceptance criteria

- Old `templates.build` manifests remain installable.
- `templates.deploy` manifests install and retain exactly their declared features.
- Express does not gain the deployment feature by registry expansion.
- English/Chinese contracts, authoring guidance and changelog describe the scope.
- Actual verification and limitations are recorded; required CI/review pass before merge.

## Evidence

- [Verification](../../../evidence/verify/2026-10-18-template-deploy-feature.md)
