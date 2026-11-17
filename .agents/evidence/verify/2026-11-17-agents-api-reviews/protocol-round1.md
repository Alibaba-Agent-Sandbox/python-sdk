# Agents API protocol review — round 1

Date: 2026-11-17. Reviewer: protocol_audit. Result: PARTIAL; useful implementation, unresolved wire-shape defects and incomplete six-Harness/cloud acceptance.

## Scope and evidence

Reviewed template PR [311](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/311), head `ee59a726bb04e9b67a79b1bcbbb0a528ced11ef1`, and its pinned runtime `b988d2a76057b6202d836ec329cc0bd90a572b26`. The root workspace checkouts are older and must not be substituted for these sources. PR 311 remains Draft/open and explicitly records missing PostgreSQL-backed cloud publication, retained-Session upgrade and model-turn acceptance. No cloud resources, model calls or OpenAI API requests were made by this review.

The current official OpenAI API includes a real managed Agents API. Its [architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture) runs the Codex harness at OpenAI; `self_hosted` describes the connected executor/environment. This project's entire Harness/model/tool loop runs in each Session Sandbox. The shared path spelling does not make the execution topology equivalent.

## Conclusion

Preserve one project protocol, `agent-sandbox-managed-agents/v1`, and make each template select its Harness. A common lifecycle, input, durable receipt, output, artifact and error contract is reasonable. Identical advertised capabilities across Harnesses are neither necessary nor truthful. Keep unavailable features explicitly rejected and described in capabilities. Do not market this as a full OpenAI implementation or universal OpenAI SDK endpoint.

This is the newer managed implementation, not the earlier guest-only in-memory API. Its PostgreSQL control plane, durable submissions, native receipt/epoch checks, owner scoping and explicit uncertain/reconciliation outcomes address the most serious earlier reliability objections. They still need the actual cloud acceptance already required by the owner records.

## Alignment matrix

| Area | Official OpenAI contract | Current managed implementation | Assessment |
| --- | --- | --- | --- |
| Agent/session resources | Saved Agent configuration plus per-session overrides | Agent CRUD, saved configuration and per-session override; metadata-only session updates | Shared basic model; narrower settings |
| Creation/input | Create can include initial input or streaming; later input is asynchronous | 201 creation, 202 empty input acceptance with project receipt header; initial stream supported | Core HTTP behavior aligned; receipt is an explicit extension |
| Busy-session input | [Run/continue](https://developers.openai.com/api/docs/guides/agents-api/sessions) describes mid-turn steering | `active_turn_not_steerable` 409, separate explicit queue endpoint | Honest feature gap, not equivalent steering |
| Request formats | [Create reference](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/create) includes environments, image inputs, tools/settings and more | String or user `input_text`; 256 KiB text; fixed self-hosted workspace, no none/openai_hosted branch | Deliberate subset; document limits and reject unsupported values |
| Input events | [Events create](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/subresources/events/methods/create) supports message/cancel/tool and approval results | Exactly one text-message or cancel event; no function result/approval workflow | Basic event envelope aligned; unsupported workflows remain explicit |
| Turns/items | [Turn reference](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/subresources/turns/methods/retrieve) has public identity, timestamps, status, error, agent/subagent and usage | Durable turns/items and specific-turn retrieval, but missing some existing same-name fields | Repair wire projection; see findings |
| Streams | [Event schema](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/subresources/events/methods/stream) includes typed events and embedded turns; [recovery](https://developers.openai.com/api/docs/guides/agents-api/sessions/events) uses saved state/items | Durable SSE with replay cursor, 20-second connections, explicit native/output gaps | Useful project extension; no claim SDK stream helpers transparently reconnect |
| Files/artifacts | [Files guide](https://developers.openai.com/api/docs/guides/agents-api/environments/files) distinguishes self-hosted provider files from OpenAI-hosted published artifacts | Multipart Gateway files, immutable input references, captured per-turn artifacts from project's own Sandbox | Useful managed feature; it is not native OpenAI self-hosted publication |
| Delete/close | [Delete reference](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/delete) removes public Session, requires execution to stop first; physical cleanup may continue | 200 public deletion, busy 409, separate project close Operation retains results | Good semantic separation |
| Tools/settings/platform features | [Configuration](https://developers.openai.com/api/docs/guides/agents-api/configuration) and [management](https://developers.openai.com/api/docs/guides/agents-api/sessions/manage) expose tools, settings and required actions | capabilities explicitly set steering/functions/MCP/subagents/session_settings false; empty required_actions/vault_ids | No silent emulation; not full feature completeness |
| Harnesses | OpenAI-managed Codex | Config and guest bridge currently whitelist only codex/qwen-code | Six-Harness requested delivery not implemented yet |

## Findings and minimal changes

### P1 — Same-name Turn and in-progress event shapes are incomplete

At the pinned SDK, `client-sdk/src/agent_sandbox/managed_agents/worker.py` lines 439–451 creates a public Turn without `agent_id`, `started_at` or `subagent_id`. `service.public()` converts timestamps only for Sessions, so Turn timestamps are floats. The OpenAI Turn schema exposes integer-second timestamps, Agent identity and nullable subagent identity. Its documented helpers use `event.turn.subagent_id` to distinguish root from subagent outcomes.

More directly, `_ingest()` lines 479–486 strips the guest `turn` object from all forwarded events and does not replace it for `agent.session.turn.in_progress`; that same-name event's official schema requires a Turn object. This is avoidable even when arbitrary OpenAI SDK interoperability is out of scope.

Minimal repair: record stable Agent identity and observed start time on new Turns; project nullable subagent identity; convert public Turn timestamps to integer seconds without changing internal precision; attach the host's public Turn to forwarded in-progress events. Never expose native guest Session/Turn identities. Add regressions for HTTP Turn retrieval and SSE Turn events, including saved Agent and inline Agent Sessions. Preserve old-record behavior explicitly rather than inventing a new identity on every read.

Initial local reproduction attempt was blocked at import by missing Pydantic in system Python. A dedicated dependency environment is being prepared; this report is static evidence until that probe runs.

### P2 — Capabilities should distinguish common contract from selected Harness

`service.capabilities()` has global feature booleans, and `/v1/agents/runtimes` reports installed=true from configuration alone. That does not prove a binary exists in the target Guest or that a native mode supports continuation/stream detail. As the Harness set grows, publish concrete selected adapter features and stream granularity. Do not conflate “runtime configured”, “binary present” and “real task accepted”.

The existing model-to-adapter binding is one-to-one. Independent `agents-api-{harness}` deployments naturally support the same model through different Harnesses without introducing ambiguous runtime routing into the public API. Keep model identity separate from template/Harness identity.

### P1 — “Complete and usable” remains an acceptance result, not a route count

Configuration currently admits only Codex/Qwen. The requested Qoder, Claude Code, OpenCode and DeepSeek Harness adapters need native version-pinned command mappings, same-session continuation, actual tool-produced artifacts, bounded streaming/output, process cancellation and own-resource cleanup. Existing CLI templates or `run command` access are not managed adapters. A deterministic fake CLI proves the envelope and control logic only.

## Adversarial position

Rejected alternative: forcing all six Harnesses to emulate every OpenAI feature would manufacture steering or approval semantics and expand this task into a different hosted platform. Rejected alternative: calling protocol equality sufficient while emitted same-name Turn/events omit required fields; these are low-cost concrete correctness fixes. Accepted boundary: one stable project protocol with a tested shared core and explicit per-Harness capabilities, plus documented OpenAI alignment/differences.

Cross-review request sent to runtime_audit and harness_audit. This first report is not either of the user's required final two post-implementation review rounds.

## Follow-up: concrete reproduction and approved repair

The isolated dependency environment later ran the original source probe successfully:
Turn keys lacked `agent_id`/`started_at`/`subagent_id`, `created_at` was a float,
and the in-progress event keys lacked `turn`. All four added regressions failed
before the repair, including actual official OpenAI typed validation.

Runtime review challenged inline snapshot identity, old-record migration and observed
start-time precision. The revised patch freezes an inline snapshot identity, preserves
saved identity without definition lookups, supplies old-record values only through
projection, and leaves unknown historical start times null. The runtime reviewer
accepted this scope and required the saved-definition update/delete counterexample.

The resulting four regressions passed, including OpenAI 3.52.0 typed parsing and its
real local HTTP Turn retrieval/event-stream consumption. Existing managed tests had
91 passes and eight raw-socket failures; those failures are recorded separately and
are not converted into cloud/model or full-SDK interoperability passes. Owner records:
`python-sdk/.agents/notes/proposed/feature/2026-11-17-managed-turn-wire.md` and its
verification file. The user's two final review rounds are still pending.
