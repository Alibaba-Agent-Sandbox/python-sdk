# Recorded Agents API alignment boundary

This is the 2026-11-12 review snapshot for SDK source
c4d43a24f40412bb8ab303509a7cb5bf7030da3c and official Python SDK3.49.0. It archives the
earlier comparison, not a new official-API lookup, model run or cloud acceptance.
Beta references and later source must be checked again before extending claims.

The project runs the complete Agent CLI/model/tool loop inside Sandbox. The official hosted
harness with a self-hosted exec-server connection is a different topology. A matching URL
path does not establish that topology or its behavior.

| Surface | Recorded Managed implementation and boundary |
| --- | --- |
| Model/runtime/capability discovery | Explicit admitted Codex/Qwen mapping and project capability endpoint. Adapter classes do not admit other runtimes to HTTP. One ordinary deployment has one actual model binding. |
| Saved Agent and Session | Selected owner-scoped resource subset; create201 and supported initial text. Saved Agent plus inline supported overrides creates a Session snapshot without changing the saved object. The earlier mutual-exclusion hypothesis was rejected. |
| Typed input | String/user input_text subset and optional message discriminator. Unsupported image/audio/tool forms are rejected rather than implied. |
| Active input | Cannot steer the current native turn through this path; busy input is rejected. Explicit durable submissions enqueue a later turn and are a project extension. |
| Turns/items/events | Implemented persistent query/event paths and replay boundaries. Actual FC realtime streaming still needs a live streaming ingress check; a completed buffered response is insufficient. |
| Input files/artifacts | Fixed input snapshots and immutable per-turn output bytes with budgets and retention. These are project-managed extensions, distinct from official hosted files and from the older broad local server's in-memory files. |
| Cancel and uncertainty | Cancellation needs confirmed stop; uncertain native delivery remains reconcilable. Lease expiry or a database receipt alone does not prove remote side effects stopped or exactly-once execution. |
| Close/delete | Close releases compute while retaining published results; DELETE removes public access and has separate busy/cleanup rules. Do not describe retained close results as resources still available after DELETE. |
| Official SDK decoding | Actual loopback HTTP/SQLite create/retrieve/list decode in default mode. Strict response validation still fails on Agent/harness/environment fields. See retained typed results; no Worker/model was started. |
| Narrow response projection | Public integer timestamps and truthful empty required_actions/vault_ids; internal clock precision is retained. No invented remote_url, inline saved-Agent ID, service tier, reasoning or multi-agent state. |
| Other known differences | Metadata limits and future-turn configuration do not match the full official reference. Arbitrary external tools/MCP, subagents, automations, webhooks, vault and trace are not delivered by this Managed subset. |
| Broad local server | Separate persistence, input/lifecycle and saved-Agent override behavior remain. Managed fixes cannot be described as fixes to every server entrypoint. |

Recorded primary references:

- [Official architecture](https://developers.openai.com/api/docs/guides/agents-api/architecture).
- [Session semantics](https://developers.openai.com/api/docs/guides/agents-api/sessions).
- [Create Session reference](https://developers.openai.com/api/reference/resources/beta/subresources/agents/subresources/sessions/methods/create).
- [Files/environments](https://developers.openai.com/api/docs/guides/agents-api/environments/files).

The model protocol prerequisite is separately retained in model-protocol-preflight.json:
the configured model's Chat tool-result probe returned200 and Responses tool-result400.
That is not a general conclusion about other accounts/services, and not a real Codex task.
New FC/Qwen/Codex acceptance, revision routing and cleanup still require the owner operations
and their separate dated evidence. No success article is authorized by this comparison alone.
