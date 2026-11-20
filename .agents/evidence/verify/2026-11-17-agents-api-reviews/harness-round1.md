# Harness adaptation review — round 1

Date: 2026-11-17. Scope: read-only source and official documentation investigation, not cloud/model acceptance.

## Decision

Proceed with one shared Managed Agents API contract and six explicitly named deployment templates. Keep Gateway, durable submissions, files/artifacts, Worker, reconciliation and owned cleanup shared. Implement each native harness adapter behind the existing AgentRuntime invocation/parser boundary. A copied Dockerfile and renamed catalog entry alone do not deliver an adapter.

Do not advertise universal OpenAI equivalence. Preserve the same API request/resource/event envelopes; report unsupported capabilities and streaming granularity honestly. Native session restoration and actual process termination must be verified separately for every harness.

## Baseline and concrete gaps

Reviewed Python main `a9a572d81847fe99216bf1bb454b91810dacc676` and templates PR311 `ee59a726bb04e9b67a79b1bcbbb0a528ced11ef1` in the task's isolated checkouts. Old workspace roots are stale and were not treated as the new implementation.

1. `server-sdk/src/agent_sandbox/server/managed.py:111` allows only `codex` and `qwen-code`, and creates a ProviderSpec from OPENAI environment variables. Its capabilities endpoint repeats the same two-binary list.
2. `client-sdk/src/agent_sandbox/managed_agents/models.py:148` restricts model bindings to those two adapters; line 183 allows only three OPENAI variable names.
3. `client-sdk/src/agent_sandbox/providers/alicloud_express/managed.py` requires an exact four-field model object and those two adapter names, requires exactly the OPENAI allowlist, and injects those names into the guest. Qoder's native PAT cannot use this shape truthfully.
4. `server-sdk/src/agent_sandbox/server/agents/adapters/__init__.py` registers Codex, Claude Code, Cursor, Qwen Code and generic Command adapters. Qoder, OpenCode and official DeepSeek Harness are absent. Claude Code exists in the core runtime but is unavailable in the managed bridge.
5. `agents-api/server/bootstrap.py:25` repeats the two-adapter restriction and requires OPENAI key/HTTPS endpoint for every Worker. `agents-api/Dockerfile` installs only Codex 0.162.1 and Qwen Code 0.23.0.
6. The existing `deepseek-harness` template is explicitly a repository-owned Python Chat Completions tool loop. It is not the official DeepSeek Harness and cannot satisfy a request for that native harness under a new label.

## Native interfaces and authentication

| Harness | Existing/new runtime | Native headless interface | Native continuation | Authentication/configuration |
| --- | --- | --- | --- | --- |
| Codex | existing `codex` adapter | `codex exec --json`, prompt via stdin | `codex exec resume ID` | OPENAI_API_KEY plus explicit Responses endpoint/model |
| Qwen Code | existing `qwen-code` adapter | positional prompt, `--output-format stream-json --include-partial-messages` | `--resume ID` | OPENAI_API_KEY/BASE_URL/MODEL for the existing compatible-service path |
| Claude Code | existing `claude-code`, extend managed integration | `claude -p --output-format stream-json --verbose --include-partial-messages` | `--resume ID` | ANTHROPIC_API_KEY or native bearer/OAuth credentials; Messages API endpoint |
| Qoder | new `qoder` adapter | `qoder --print --output-format stream-json` | `--resume ID` | QODER_PERSONAL_ACCESS_TOKEN for native service; model selection uses Qoder model IDs |
| OpenCode | new `opencode` adapter | version-specific `opencode run --format json` | `--session ID` | explicit provider/model config; do not assume arbitrary OPENAI env alone configures a provider |
| DeepSeek Harness | new `deepseek-harness` adapter | `dsh --profile headless --json -` | `--session-id ID` with same DSH_HOME and cwd | DEEPSEEK_API_KEY, explicit route config; official package `@deepseek-ai/dsh` |

Official Codex documentation demonstrates automation through `codex exec --json` and observable command events. The existing pinned adapter still needs actual two-turn testing after managed template migration. [OpenAI official documentation](https://developers.openai.com/blog/eval-skills).

Qwen's headless JSON mode returns structured session, assistant, and terminal result messages; optional partial events provide finer streaming. A terminal result can precede process exit because managed memory work may still be running. Keep the supervisor's exit check. [Official headless guide](https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/).

Claude's programmatic CLI supports structured streaming and explicit resume. SIGTERM leaves the active turn unfinished; SIGINT or SDK interrupt can end it first. Background commands/MCP work have separate lifecycle behavior, so CLI success alone does not establish all work stopped. [Official headless guide](https://code.claude.com/docs/en/headless).

Qoder documents headless JSON, stream-json, session IDs and exact resume. Its PAT is obtained from account integrations and passed as QODER_PERSONAL_ACCESS_TOKEN. BYOK is account/plan/catalog dependent, configured through its wizard; the documentation explicitly rejects inventing manual settings.json BYOK configuration. The first managed adapter should use native PAT/model selection. [CLI reference](https://docs.qoder.com/cli/cli-reference), [authentication](https://docs.qoder.com/cli/authentication), [custom models](https://docs.qoder.com/cli/custom-models).

OpenCode currently has two published npm lines: existing templates pin `opencode-ai@1.19.0`, while current docs show `@opencode/cli` v2 and new flags such as standalone. Pick one fixed line and verify its help/events; do not infer v1 behavior from v2 examples. Both document headless tasks, JSON output, model choice and exact session continuation. [Official current command guide](https://opencode.ai/docs/cli/commands), [model config](https://opencode.ai/docs/models/).

Official DeepSeek Harness is real, developed by DeepSeek AI, and in developer preview. Pinned tag `dsh-v0.2.2-rc.1`, commit `66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db`, documents the native headless path. Its JSON text events come from committed steps, not token deltas. Preserve the terminal final reason: completed requires both exit 0 and `final.reason.kind == completed`; a tool_result alone is insufficient. Resume requires the same home/cwd and persisted identity. [Official project](https://github.com/deepseek-ai/deepseek-harness), [pinned headless interface](https://github.com/deepseek-ai/deepseek-harness/blob/66491b05e3f05ad35bcdd4f6cd7ed26041d9e3db/packages/bundle/headless/README.md).

Registry metadata observed: Codex latest 0.169.0, Claude Code 2.1.326, Qwen Code 0.27.4, Qoder CLI 1.1.90, DSH 0.2.2-rc.1, OpenCode v1 1.19.5/v2 2.3.0. These are discovery results, not recommendations to upgrade working pins. DSH requires Node >=24.9; the template's Node 24.16 meets that requirement. All runtime installations must remain exact-version pinned and checked in the final image.

## Minimal implementation boundary

- Keep existing model-to-adapter binding and deploy independent `agents-api-{harness}` applications. The same model may be used by different harness deployments without overloading model identity.
- Add three real adapters and register their canonical IDs/aliases. Reuse parser helpers only when captured native event schemas match. Test malformed/truncated events, errors and resume IDs as well as success.
- Put managed adapter-to-native environment mapping in one stdlib-only shared module; validate exact credentials/configuration per adapter, preserve explicit endpoints and prevent arbitrary environment forwarding. Qoder does not need a fake OPENAI endpoint.
- Preserve serialized turns, durable native receipt/epoch handling, output bounds, cancellation, process-domain quiescence and owned Sandbox destruction. Do not let adapter changes bypass uncertainty handling.
- Default to one headless subprocess per turn. Avoid unrelated native daemon/server management until needed by a verified harness path.
- Use one shared template bridge/release implementation and reviewed harness-specific pins/configuration. Separate template IDs may share maintained source code without copying Gateway state machines six times.

## Acceptance and release gates

Local parser/invocation fixtures prove adapter mappings only. Each harness requires an installed native CLI smoke, two real model turns on one native session, file input, generated source/report download and independent execution, cancellation while a tool runs, bounded failure output, process absence or owned Sandbox deletion, and close/delete semantics. One shared real FC/PostgreSQL application plus controlled per-harness guest sessions can establish core hosting behavior without creating six databases. Keep revised-template deployment/update/old-session continuation as their own gate.

Do not rename unverified evidence into passes. An unavailable account or model route is a concrete BLOCKED harness acceptance, even if installation succeeds. Preserve Beta/experimental until the applicable full acceptance policy is met.

## Cross-examination

- Runtime reviewer agrees with short-lived headless invocation and preserving receipt/epoch/no-replay rules. A final JSON message cannot replace actual exit/stop confirmation. Revised FC/PostgreSQL recipe and old-session upgrade remain unverified release gates.
- Protocol reviewer agrees that create/input/files/turns/items/events/cancel/close/delete and genuine resume form the shared baseline. Steering, functions, MCP and subagents require honest capability boundaries. Committed-step streaming is valid when reported as such, but must not be represented as token streaming.
- No evidence supports requiring a separate public protocol for each harness. Native capabilities differ; HTTP resource identity and ownership rules should stay shared.

No product file, credential or cloud resource was changed during this review. Follow-on implementation was separately assigned after this report's findings were shared.
