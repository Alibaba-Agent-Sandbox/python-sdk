# Decision: Describe built-in provider updates and existing Express adoption

Status: implemented

## Problem

Python update treats the built-in provider as an uninstalled plugin. Existing Express resources can be reused, but the SDK is not a zero-change E2B replacement.

## Decision

Route bundled and external backends through the same Provider factory and session hooks. Move Express authentication, native engine creation and lifecycle binding into providers/alicloud_express; move explicit E2B wire adapters under providers/shared/e2b. Core depends on structural protocols. Preserve historical import/module identity, reject foreign defaults and distinguish created-resource cleanup from borrowed-resource ownership. Retain SDK-bundled update guidance without fetching/installing software.

## API Design

installer.update(alicloud-express) returns status bundled, installed SDK version, available null, changes and message; ref is rejected. Existing Git/catalog behavior is retained. Provider session_protocols, prepare_session, resolve_session_url, open_terminal and optional engine hooks own backend assembly; absent implementations fail closed.

## Alternatives considered

Separate built-in plugin updates would split the SDK release contract. Automatically adopting E2B_* secrets would weaken provider isolation. Rebuilding all resources is unnecessary for client adoption.

## Dependencies

Shared host design: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/c5a6a3c75921cfb4359f1c23041ec847ce63c932/docs/en/design/provider-portability-and-updates.md; Node management requires compatible abx.

## Test Strategy

Existing installer suite plus offline no-receipt and actual CLI regressions, both-package lint/format/typecheck, scoped links and required full aggregate. Add architecture import-boundary and create/connect ownership regressions. Run real Express create/exec/files/connect/list/cleanup against current sources; historical storage evidence remains separate.

## Acceptance criteria

Bundled update is actionable and performs no plugin I/O; Git/catalog regressions pass; migration explicitly distinguishes resource reuse and source compatibility; mandatory gates pass before merge.

Acceptance also requires no concrete backend imports in core implementation, no
null/default-provider lifecycle bypass, provider-owned authentication/session/URL/terminal
assembly, no foreign configuration defaults, and owned-versus-borrowed cleanup regressions.

## Evidence

[Verification](../../../evidence/verify/2026-10-18-provider-portability-updates.md).

Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/52.

## Implementation

The full-isolation follow-up removes the earlier guard-only limitation. Authentication,
cloud mappings and session defaults are provider-owned. CLI templates and UI metadata
remain owned by the CLI repository. Historical evidence remains unchanged; acceptance is tracked in the new
[isolation verification](../../../evidence/verify/2026-10-18-provider-complete-isolation.md).

The Express wrapper explicitly forwards its selected provider into engine creation;
[follow-up verification](../../../evidence/verify/2026-10-18-provider-explicit-engine-routing.md)
records the failing negative control, 2152-pass client suite and real conflict-case cleanup.


The current-host integration retains the accepted API-key-only runtime authentication,
independent CLI error renderer and retired native gRPC slice. Provider-owned URL builders
replace core wire-format logic. Python schema composition remains lazy and injected;
CLI tool schemas and handler discovery are recomputed together. Earlier engine-routing
verification remains historical, not evidence that the retired daemon is still used.
See the [integration checkpoint](../../../evidence/verify/2026-10-18-provider-current-host-checkpoint.md).

Port access and file-transfer URL conventions now belong to explicit adapter hooks.
Asynchronous-only discovery fails closed in synchronous helpers. Neutral Python imports
remain lazy; a fresh-process regression prevents built-in auth/wire loading.

[Port and file URL boundary checkpoint](../../../evidence/verify/2026-10-18-provider-port-url-boundaries.md).

Current host/adapter acceptance is complete for the tested Express configuration; see
[final verification](../../../evidence/verify/2026-10-18-provider-isolation-acceptance.md). Hosted checks pass on the tested
implementation revisions. The evidence-only PR head must pass its gates before merge.
Native image factories and unconfigured backend E2E remain separate acceptance work.

[Convergence verification](../../../evidence/verify/2026-10-18-provider-convergence-acceptance.md) records the ordinary remote
merges, provider-owned pure metadata restoration and current Express smoke results.
