# Decision: Preserve managed Turn identities and lifecycle event shapes

Status: proposed

## Problem

Managed Turn retrieval omitted the Agent and root-agent identity fields and exposed
fractional timestamps. The in-progress lifecycle event dropped its native Turn without
replacing it with the host's public Turn. Consumers of the existing same-name resources
could not consistently associate lifecycle events with retrieved results.

## Decision

Keep public Session/Turn identities separate from the guest runtime. Freeze an inline
Agent snapshot identity with its Session, preserve saved Agent identity, and include
that same identity on each Turn. Inline identities identify snapshots, not separately
retrievable saved Agent definitions. Project integer Unix seconds without reducing
internal timestamp precision. Reconstruct only the in-progress Turn event's embedded
Turn from host state; terminal events use the same public projection.

For retained older records, derive the same inline snapshot identity from their stable
Session identity, and project unknown start time as null. Do not rewrite historical
records or look up a subsequently changed/deleted saved Agent definition.

## API Design

`public(row, *, session=None) -> dict[str, Any]` adds Session context when projecting
older Turns. Public Turns carry `agent_id`, `subagent_id: null`, and integer/null lifecycle
timestamps. New Turns prefer native start time; if absent, the Worker records the first
execution observation time. No steering, subagent or external tool ability is added. Capabilities retain the adapter
ID list and add per-configured-adapter stream/tool timing and per-tool-timeout
support. OpenCode completed-only tool events do not claim an enforceable per-tool deadline.
Runtime inventory identifies configured adapters and returns `installed: null`; a Gateway
cannot inspect a Guest that does not yet exist.

## Alternatives considered

- **Leave same-name shapes incomplete** — rejected because a concrete in-progress
  event cannot be consumed using its documented embedded Turn.
- **Resolve the current saved Agent during each read** — rejected because a Session
  freezes its original configuration and survives later definition update/deletion.
- **Create saved definitions for all inline configurations** — rejected because it
  silently changes Agent collection and retention behavior.
- **Use the read time as the start time of older Turns** — rejected because that
  would invent a lifecycle observation that never occurred.

## Dependencies

The existing managed service, worker, database and HTTP listener. The optional OpenAI
package is used only for a local interoperability regression, never as a runtime
requirement or evidence of complete SDK/API parity.

## Test Strategy

Reproduce the failure before fixing it. Verify stable inline/saved identities, immutable
legacy projection, private clock precision, and matching retrieved/event Turn shapes.
Optionally validate with official OpenAI typed models and use that SDK against a real
local HTTP listener and durable event replay. Run the owning repository's full gates;
retain cloud/model and raw-socket failures separately.

## Acceptance criteria

- New and retained Turns expose stable frozen Agent identity and root-agent identity.
- Retrieval and in-progress/terminal events agree on host Turn and Session identity.
- Public timestamps use integer seconds; unknown historical start times remain null.
- Saved Agent update/deletion does not change an existing Session's snapshot identity.
- Regression, lint, type/health/hygiene gates pass, and real managed cloud acceptance is
  recorded before full delivery is claimed.

## Evidence

- [Verification](../../../evidence/verify/2026-11-17-managed-turn-wire.md).
