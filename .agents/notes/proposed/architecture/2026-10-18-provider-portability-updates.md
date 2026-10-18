# Decision: Describe built-in provider updates and existing Express adoption

Status: proposed

## Problem

Python update treats the built-in provider as an uninstalled plugin. Existing Express resources can be reused, but the SDK is not a zero-change E2B replacement.

## Decision

Report the SDK-bundled release lifecycle without fetching or installing software. Document explicit config/API changes, ownership-safe adoption, native lifecycle versus Node management and coordinated client/server upgrades.

## API Design

installer.update(alicloud-express) returns status bundled, installed SDK version, available null, changes and message; ref is rejected. Existing Git/catalog behavior is retained.

## Alternatives considered

Separate built-in plugin updates would split the SDK release contract. Automatically adopting E2B_* secrets would weaken provider isolation. Rebuilding all resources is unnecessary for client adoption.

## Dependencies

Shared host design: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/design/provider-portability-and-updates.md; Node management requires compatible abx.

## Test Strategy

Existing installer suite plus offline no-receipt and actual CLI regressions, both-package lint/format/typecheck, scoped links and required full aggregate. Historical cloud storage evidence is linked without claiming another live run.

## Acceptance criteria

Bundled update is actionable and performs no plugin I/O; Git/catalog regressions pass; migration explicitly distinguishes resource reuse and source compatibility; mandatory gates pass before merge.

## Evidence

[Verification](../../../evidence/verify/2026-10-18-provider-portability-updates.md).

Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/52.
