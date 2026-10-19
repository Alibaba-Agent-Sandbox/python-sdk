# Decision: Describe implemented Express conditional capabilities accurately

Status: implemented

## Problem
The local discussion conflated backend allowlist admission with missing product support. The current accepted standard Python sync/async public methods and the separate native Provider facade already exist, but the conditional guide is focused on fixture provisioning and leaves this distinction implicit.

## Decision
Clarify the existing supported standard entry, explicit pause/snapshot allowlist conditions, generation2 snapshot requirement, connect-based resume, request timeout and cleanup. Add concrete EN/ZH SDK and CLI examples and link the current official Agent Sandbox pages. Keep native Provider extension gates distinct and preserve historical acceptance as historical evidence.

## API Design
No runtime API changes. This documents interfaces already accepted on main; no features are newly enabled or falsely declared for native providers. Python uses create_snapshot, not a camelCase alias. Current guide scope is standard Python sync/async public methods and the separate native Provider facade.

## Alternatives considered
Changing a feature flag without implementing a provider's matching wire contract would misrepresent support. Repeating already verified cloud tests for prose would create unrelated resources. Treating an account/template admission failure as globally unsupported contradicts the official service contract.

## Dependencies
Accepted python-sdk sourced4d93e8cbb986f33a8868f7a4139ed0edb49eaba; companion owner https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/conditional-acceptance.md . Official service references are linked directly from the guides. No provider/template catalog schema change is needed.

## Test Strategy
Check actual standard public method/command availability, parse Python examples, validate relative links and run repository health/hygiene. Preserve the existing real generation2 receipt instead of claiming a new cloud run. Require current-head hosted CI before merge.

## Acceptance criteria
The EN/ZH guide distinguishes implemented standard support from admission and native extension contracts; examples map to actual symbols and commands. Historical failures/receipts remain unchanged and only scoped documentation/records are committed.

## Evidence
See [verification](../../../evidence/verify/2026-10-19-express-conditional-support.md).
