# Decision: Publish the paired Python0.5.0a1 preview

Status: proposed

## Problem

[Issue186](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/186) tracks distribution of the actual client/server fixes merged in [PR185](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/185). Existing public0.5.0a0 does not include the retryable MCP cleanup, protocol guard, corrected harness hint or pip-independent inventory behavior. Documentation-only PR180 did not require a release by itself.

## Decision

Publish agent-sandbox-client and agent-sandbox-server together as0.5.0a1. Keep the optional server extra exactly pinned, update current installation pages and packaged READMEs, and preserve historical release records and template image pins. Tag only the approved merged source and use the existing publish workflow's full paired CI, artifact preservation, existing-file hash preflight, server-first upload and public readback.

## API Design

No additional API beyond PR185. The current Provider and managed application drafts remain unmerged and are not part of this release. Installing the host client does not update an existing sandbox image; server changes require installing the new server package in that image.

## Alternatives considered

- Reuse public0.5.0a0: rejected because released artifacts are immutable.
- Publish only one distribution: rejected because the project keeps paired versions and the optional-server dependency exact.
- Include unrelated provider/native-template drafts or rebuild all template images: outside this release's required scope.

## Dependencies

Source merge76f28aa8168c03833a83169eafe17df77865b518. Existing GitHub pypi environment and PYPI_API_TOKEN configuration, without copying credentials. CLI-generated MCP consumers update their pin only after public Python artifacts are verified.

## Test Strategy

Version/tag checks, optional-server metadata checks, paired wheel/sdist build and clean installation, full remote CI for the exact version PR and release tag, then public artifact hashes and fresh client-only plus optional-server installations.

## Acceptance criteria

Both distributions have matching0.5.0a1 versions; remote gates pass; public files match the release workflow's artifacts; imports, actual client HTTP and pip check pass without implicitly installing the server in the base client; source/docs delivery and publication are separately recorded.

## Evidence

- [Preflight](../../../evidence/verify/2026-11-25-python-050a1-preflight.md)
