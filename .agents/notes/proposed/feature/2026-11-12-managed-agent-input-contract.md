# Decision: Preserve the managed Agent input and saved-configuration contract

Status: proposed

## Problem

The managed Gateway rejects a user message containing the optional `type: "message"`
discriminator accepted by the current OpenAI Create Session reference. Explicit false-like
Agent IDs can bypass lookup and fall back to an inline configuration, while other non-string
IDs are coerced to strings. Rate-limit and unavailable-service errors use the same category
as invalid requests. These mismatches affect clients before native execution begins.

## Decision

Accept only the optional literal message discriminator without widening the supported
user/input_text subset. Validate an explicitly supplied Agent ID as a string and perform
the existing owner-aware lookup even for an empty string. Preserve saved Agent plus inline
overrides and verify that they create independent Session snapshots. Categorize the directly
documented HTTP429 and503 cases while retaining existing codes, messages and field paths.

## API Design

`text_input(value)` accepts the existing string and user-message forms plus optional
`type: "message"`. Unknown types, non-user roles, images and oversized text still fail.
`create_session` requires any supplied `agent_id` to be a string: non-string400; unknown,
foreign, deleted or empty ID404. Supplying `agent_id` and supported inline `agent` fields
remains valid; the latter override only the new Session's configuration.
ManagedError reports `rate_limit_error` for429 and `service_unavailable_error` for503.
Other status categories are unchanged; this is not a claim of full OpenAI compatibility.

## Alternatives considered

- Reject `agent_id` together with `agent`: rejected after reading the current official
  reference, which explicitly permits per-session overrides. The local API's older rule
  is not authority for the managed contract and is outside this change.
- Require nonempty IDs: not inferred from the upstream schema, whose string minimum is0.
  Existing lookup gives404 for an empty ID without creating a Session.
- Copy a universal error-category map or expose every local Agent feature: rejected;
  the verified authoritative examples and current task only justify this bounded patch.

## Dependencies

No new dependency, adapter, schema language, cloud resource or package release.
Authoritative references: [Create Session](https://developers.openai.com/api/reference/resources/beta/subresources/agents/subresources/sessions/methods/create)
and [Error codes](https://developers.openai.com/api/docs/guides/error-codes).
Current managed runtime and template work are independent of the broader YAML migration;
these corrections do not establish migration completion or real model acceptance.
Owner issue: [python-sdk162](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/162).
Delivery tracker: [templates309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

## Test Strategy

First run new consumer regressions against unchanged production code to demonstrate the
typed-input, ID-lookup/type and category failures. Exercise all three input entry points,
atomic invalid-input rejection, saved overrides, owner/missing-ID behavior and a real local
HTTP listener's accepted request, quota rejection and safe dependency-error conversion.
Run both package suites, lint, typecheck and repository health/hygiene. Preserve the required
cloud/model E2E gate as pending until the encompassing delivery runs it.

## Acceptance criteria

- Typed and untyped supported messages are accepted without allowing new input kinds.
- Invalid input and invalid Agent IDs leave no accepted Session or Submission.
- Saved Agent overrides do not mutate the source Agent or previous Sessions.
- 429/503 response categories are correct and private exception text remains hidden.
- Required local checks and current-head remote gates are reported accurately.
- Real cloud/model validation and publication remain explicit incomplete gates.

## Evidence

[Verification](../../../evidence/verify/2026-11-12-managed-agent-input-contract.md).
