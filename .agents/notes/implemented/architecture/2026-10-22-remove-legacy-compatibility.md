# Decision: Remove retired project compatibility

Status: implemented

## Problem
The maintainer states that the project has not formally released and requests removing old template management/API behavior and other project compatibility layers. Keeping aliases, alternate factories and fallback branches expands an API that is not meant to be supported.

## Decision
ProviderSandbox keyword/import cleanup, deprecated protocol methods, sandbox server transfers/authentication and explicit provider addressing.
Keep a single current project contract. Do not add a migration mode or replacement aliases. Preserve historical engineering evidence and the current pinned upstream standard-client contract.

## API Design
Removed interfaces are unavailable. Current provider preparation uses `templates.build` and `prepareProject`; each owning provider retains its native implementation. This repository's exact changes are reviewable in its scoped branch.

## Alternatives considered
- Keep deprecated wrappers or document them as disabled: rejected by the maintainer's request.
- Rewrite historical evidence: rejected; old evidence describes its tested revision.

## Dependencies
Cross-repository cleanup is coordinated with https://github.com/Alibaba-Agent-Sandbox/agent-sandbox and https://github.com/Alibaba-Agent-Sandbox/awesome-providers. Shared UI originates in https://github.com/Alibaba-Agent-Sandbox/website and is synchronized into https://github.com/Alibaba-Agent-Sandbox/registry.

## Test Strategy
Run the repository's required local checks and regressions for current observable behavior, including rejection of removed interfaces. Record actual results and outstanding live/remote gates separately.

## Acceptance criteria
- Current paths work and removed project compatibility paths are unavailable.
- Documentation and tests describe the same contract.
- Required local checks pass, evidence is recorded, and remote CI/review pass before merge.

## Evidence
- [Verification](../../../evidence/verify/2026-10-22-remove-legacy-compatibility.md)

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/84

## Acceptance

Verified merged implementation: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/85. The source merge commit is `d1a54f78e447bc67b90dbfdf48168b020275c871`.

- [Remote acceptance](../../../evidence/verify/2026-10-22-remove-legacy-acceptance.md)
