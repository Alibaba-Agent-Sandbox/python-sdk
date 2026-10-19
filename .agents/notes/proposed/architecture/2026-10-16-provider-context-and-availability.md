# Decision: Resolve provider context independently of the standard protocol API

Status: proposed

## Problem

The SDK deliberately exposes a pinned E2B protocol API and a provider-aware project API. This separation is useful, but the native Express special path re-read ambient provider configuration after explicit selection. Feature declarations also do not prove handler coverage or account/runtime availability. A provider namespace must not become an opaque sandbox ID merely because the provider is reserved, malformed or unavailable.

## Decision

Keep `Sandbox` and `AsyncSandbox` as synchronous/asynchronous standard E2B protocol clients and keep `ProviderSandbox` explicit. Fix the native Express configuration path to resolve Express configuration regardless of the ambient provider. Reject unresolved explicit resource namespaces before requests.

For subsequent architecture work, resolve a provider context once and pass it through native lifecycle, protocol and extension operations. Separate declared features, implemented handlers and conditional availability. Availability must preserve unknown prerequisites instead of inventing backend support or discovery endpoints. Provider-specific management registration remains separate from common-operation adapters. The CLI owns invocation normalization and the shared operation plan: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.

A later maintenance phase should provide executable source-port import/patch replay and validate source provenance in CI. Existing original hashes and patch notes are useful evidence, but they do not by themselves constitute a reproducible replay pipeline. Do not apply broad style rewrites to generated code.

## API Design

Existing public standard and provider entry points retain their separate contracts. Proposed internal provider contexts contain a provider identity, resolved configuration and available adapters. A future availability result distinguishes support, lack of implementation, unknown prerequisites and a known unavailable condition. Exact public discovery names require a separate reviewed API contract; this proposal does not claim new exports exist.

## Alternatives considered

- Switch the standard API dynamically through ABX_PROVIDER: rejected because it changes pinned synchronization, protocol, models and errors.
- Add every host feature to the builtin adapter: rejected because registry membership does not implement a capability.
- Use command registration as universal capability discovery: rejected because metadata and handler binding cannot infer backend enablement.
- Retry another provider for missing operations: rejected because resource ownership must remain explicit.

## Dependencies

- SDK migration work: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47.
- Pending management registration: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38.
- CLI operation architecture and implementation: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.

## Test Strategy

Exercise the actual ProviderSandbox entry with another ambient provider and an unavailable ambient provider while explicitly selecting Express. Verify selected configuration and authentication; mock only remote responses in offline regressions. Test invalid, reserved, empty and unknown resource namespaces without backend requests. Keep standard protocol behavior tests and pinned signature checks distinct; signatures alone do not prove migration compatibility.

Run real enabled-provider scenarios for conditional capabilities before claiming success, preserving cloud errors and cleanup evidence. Source replay tests must compare maintained outputs, original provenance and declared patches.

## Acceptance criteria

- An explicit native Express selection never loads another provider's schema or credentials.
- Explicit resource namespaces resolve or fail before backend work.
- Standard and provider entry points are accurately documented in both languages and in contributor architecture guidance.
- Provider availability cannot be inferred solely from a manifest or command registration.
- Shared changes land before consumers; each repository owns its own record and verification.
- Conditional pause/snapshot success, a reproducible source replay and broader native operation unification remain explicitly pending until independently verified.
