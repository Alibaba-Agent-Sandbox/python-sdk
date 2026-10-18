# Decision: Retire the unimplemented builtin retry promise
Status: proposed

## Problem

References advertise retry tuning that neither builtin HTTP transport reads.
Public config names and an actively forwarded EPP value have compatibility
owners, so they are not equivalent to unreachable implementation code.
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/60

## Decision

Document a single-attempt builtin transport and retain existing names/defaults
only for configuration/extension compatibility. Remove active tuning examples
and clarify independent engine discovery/auth recovery. Do not implement generic
retries or change EPP payloads in a documentation correction.

## API Design

No name/default/schema/behavior change. max_retries is still forwarded to EPP;
provider-specific interpretation is not a builtin transport guarantee. Existing
retry_base_delay parsing remains a compatibility value, not an active scheduler.

## Alternatives considered

- Enable generic transport retries: changes timeout and mutation semantics.
- Remove public config/EPP fields silently: breaks a separate public contract.
- Keep the advertised behavior: continues giving users an ineffective knob.

## Dependencies

Shared configuration owner: https://github.com/Alibaba-Agent-Sandbox/python-sdk.
CLI consumer: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox.
Node configuration-name exports remain unchanged. Registry/website aggregate
source guides; no generated catalog or capability badge change is needed.

## Test Strategy

Inspect both builtin HTTP implementations and EPP field reads; confirm only
bilingual docs/changelog/owner records change and source/schema bytes remain
unchanged. Run record/link/hygiene checks and required hosted gates. Existing
mutation-safety/cloud evidence is cited, not rerun to validate prose.

## Acceptance criteria

- No reference presents these values as working builtin retry/backoff tuning.
- Existing config and EPP contracts remain unchanged and explicitly scoped.
- Bilingual docs/records and required validation pass; no new retry claim.
