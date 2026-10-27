# Decision: Use consented Express managed API keys
Status: proposed

## Problem

AK/SK users cannot use runtime APIs without manually provisioning a sandbox key. The retired guessed temporary-token implementation was not a valid solution. Users need minimal migration, explicit consent and exact permission instructions. Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/143.

## Decision

The Express provider owns official 2026-08-20 credential creation, private persistent storage, identity/region/Team isolation, concurrency and expiry. A managed resource expires in 30 days; within its last day use requires consent to extend that same resource. No background renewal is promised for existing clients. CLI asks before creation/renewal; explicit --ci may authorize it. Plain noninteractive execution and CI environment variables do not grant consent. Explicit keys win and rejection never switches credentials. Disabled keys are not replaced. Unknown write outcomes stay journaled pending; no blind replay. SDK uses the shared engine and explicit prepare functions; no duplicated cloud implementation.

## API Design

Provider catalog: api-key.resolve (read), api-key.prepare (confirmed write), returning nonsecret metadata and a private local file reference. Python Express exposes async prepare_api_key and prepare_api_key_sync, both requiring confirm=True for writes. Native/standard runtime construction resolves existing prepared credentials. Generic CLI UI only interprets provider-owned authentication/consent callbacks.

## Alternatives considered

- Restore guessed RPC exchange: no confirmed temporary-token contract.
- Silent credential creation: contradicts the required user experience.
- One key per command: resource churn and unclear ownership.
- Independent cloud SDKs in every consumer: violates shared provider ownership.

## Dependencies

Locked official @alicloud/sandbox20260820 1.2.0, existing provider-commands/1 engine. Companion: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/200. Existing API-key SDK use remains independent of the CLI; the optional AK/SK path needs a matching CLI.

## Test Strategy

Consent denial and --ci, explicit-key priority, official generated models, real expiry request, reuse/renewal, identity/Team isolation, concurrency, private storage, disabled keys, definite permission denial and uncertain writes. Run required local checks and real CLI/SDK cloud lifecycle, with exact owned-resource cleanup. Keep cloud and mocked evidence separate.

## Acceptance criteria

- No credential write without explicit consent or --ci.
- Existing E2B standard users retain their credentials and calling contract.
- AK/SK-only CLI and Python clients use shared managed credentials.
- Exact feature/action/resource mapping, policy and recovery documented in English and Chinese.
- Required checks and real component acceptance recorded; no secrets or leaked owned resources.

## Evidence

- [Verification](../../../evidence/verify/2026-10-27-managed-api-key.md).
