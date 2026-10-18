# Decision: Do not replay uncertain provider engine mutations
Status: proposed

## Problem

Reconnecting the local engine repeats all HTTP methods after transport failure.
A committed POST whose response is lost can create another sandbox or repeat work.
SSE has the same ambiguity before the first event.
Issue: https://github.com/alibaba-agent-sandbox/python-sdk/issues/53.

## Decision

Allow one transport recovery only for GET/HEAD before observable stream output.
Return ProviderProtocolError with a reconciliation suggestion for mutations.
Retain the single discovery refresh on explicit HTTP 401 rejection: the engine's
router authenticates before provider dispatch. Do not invent an idempotency key
or assume the provider can roll back. Keep original exceptions as causes.

## API Design

EngineClient request/stream signatures are unchanged. Mutations fail with E8020
and an unknown-outcome explanation instead of automatically being submitted twice.
Callers must inspect the selected provider before manually retrying.

## Alternatives considered

- Replay every method once: duplicate resources and execution are possible.
- Add an arbitrary request ID header: there is no engine/provider deduplication contract.
- Disable all recovery: would unnecessarily remove bounded read/restart recovery.

## Dependencies

Existing httpx transport and local Node abx-engine/1 routes; no new dependency.
The CLI contract is owned by
https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md.
Registry/website aggregate the bilingual source docs; no catalog feature changes.

## Test Strategy

Exercise all mutation verbs and current connection failure types, safe reads,
authentication rejection, and streams after their first output. A real local TCP
server consumes a create POST then disconnects without a response: exactly one
request must commit. Run both package suites, lint, types, health and cloud gates.

## Acceptance criteria

- Mutation response loss sends one request for HTTP and SSE.
- GET/HEAD recover once; yielded events are never replayed.
- HTTP 401 refresh remains bounded.
- English/Chinese docs, changelog and dated verification reflect actual results.
- Required full CI and real-cloud acceptance pass before merge.
