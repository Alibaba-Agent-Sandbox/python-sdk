# Decision: project truthful Session fields in the managed Agents API

Status: proposed

## Problem

The actual official Python SDK3.49.0 accepts the managed Session routes with permissive decoding,
but strict validation rejects fractional Unix timestamps and absent empty action/vault lists,
alongside larger agent/environment topology differences. This is independently reproduced over
real local HTTP and SQLite, without a Worker, model, cloud resource or mocked HTTP response.

## Decision

Project Session `created_at` and `last_active_at` as integer Unix seconds. Return
`required_actions: []` and `vault_ids: []`: this managed implementation exposes no supported
client-required action or Vault binding. Preserve all internal timestamps, deadlines and durable
precision. Keep unsupported inputs explicitly rejected; do not manufacture official settings or
executor connection URLs merely to satisfy a client type.

## API Design

The common public Session projection applies to create/get/list/update/events without changing
the stored Session object. Other resource types keep their existing timestamp contract.
Unsupported `vault_ids` and `required_actions` request fields continue returning400. No new
required-action resource or Vault capability is introduced. Actual default official SDK
create/retrieve/list decode; strict validation still fails on unrelated agent/environment fields.

## Alternatives considered

- Change shared storage timestamps: rejected because internal lease/deadline ordering needs
  its existing precision, and only the wire projection requires integer seconds.
- Fill every missing official field with defaults: rejected; the actual CLI/model effective
  settings and OpenAI self-hosted executor topology do not follow from field names.
- Return null lists: rejected; current official reference/SDK requires arrays, and empty arrays
  truthfully describe the unavailable action/Vault capability.

## Dependencies

Part of [delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309),
stacked after [narrow input PR163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/163).
Official [Create Session reference](https://developers.openai.com/api/reference/resources/beta/subresources/agents/subresources/sessions/methods/create)
returns timestamps as integer seconds and both fields as arrays. The actual SDK probe was isolated
from project dependencies and does not add an `openai` runtime dependency or create a release.

## Test Strategy

Use real authenticated loopback HTTP and both temporary SQLite/PostgreSQL. Assert create/get/list
projections, exact fractional values in the underlying stored object and no fabricated remote URL.
Pair empty response fields with rejected unsupported request fields. Re-run existing managed
runtime tests in a private PID/proc namespace, lint/type/format/hygiene and the actual official SDK
probe. Preserve earlier full CI scope; no local/cloud acceptance claims are extended.

## Acceptance criteria

- All public Session projections use integer seconds and truthful empty lists.
- Existing stored timestamp/deadline values remain unchanged by observation.
- Unsupported action/Vault requests fail before Sandbox creation.
- Default SDK decode success is distinguished from remaining strict-schema failure.
- Required local/remote/cloud gates and the need to rebuild a final Server image are explicit.

## Evidence

[Verification](../../../evidence/verify/2026-11-12-managed-session-projection.md).
