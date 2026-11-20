# Managed Agents API runtime adversarial review — round 1

Date: 2026-11-17. Result: **PARTIAL; release remains blocked by required acceptance**.
Scope: read-only source/evidence review. No cloud resources, credentials, containers, package installations or model calls were created by this reviewer.

## Fixed inputs

- Template PR: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/311 ; observed open/Draft, head `ee59a726bb04e9b67a79b1bcbbb0a528ced11ef1`, base `52f7653bda0b6c6406207e28095ee09a87cb5018`.
- That template pins its Server to Python SDK `b988d2a76057b6202d836ec329cc0bd90a572b26`, archive SHA256 `abefcb1f16d7c87089d9d560d4f8ebd5787a140351553b84f970a171fdd18f68`; its Guest still installs published Server `0.4.0a7`.
- CLI current task source inspected from PR249 checkout, especially `src/providers/alicloud_express/resource_executor.ts`.
- Existing root checkouts and restored November 13 worktrees are older than PR311. They must not be used to assert what that PR does. Git dubious-ownership was handled per read command without changing global trust configuration.

## Decision

The current managed topology is reasonable for a supported subset: a stable Gateway, PostgreSQL public state/outbox, revision-pinned Workers, per-Session Sandbox, and a private receipt bridge. The fixed code has meaningful failure fences that should survive the Harness expansion. This review did not reproduce a new runtime correctness defect in those mechanisms; absence of a reproduced defect does not complete the cloud acceptance gate.

Do not replace this bridge with a generic HTTP wrapper around a CLI command. Do not count each existing sandbox CLI template as an already supported hosted Agent API implementation. Keep one public protocol and per-adapter capability declarations, while validating every native process independently.

## Evidence and findings

| Priority | Finding | Evidence | Required action |
| --- | --- | --- | --- |
| Release blocker | New native-resource application has not passed final hosted PostgreSQL deployment, upgrade/retained-Session routing and real-model business acceptance. | PR311 Remaining acceptance explicitly says BLOCKED. The [template repository verification](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/048db39f5a865b07343ede2a93393ceab7f2df31/.agents/evidence/verify/2026-11-13-agents-api-native-resources.md) explicitly excludes fresh changed Server Docker build, FC candidate model task, stable alias/timer, historical Session continuation and full cloud cleanup. | Run a bounded real application deployment plus update of the same application, retaining one existing Session across update, and independently confirm owned cleanup. Keep Draft/unreleased until required gates pass. |
| Scope blocker for six Harnesses | The current stack admits only Codex and Qwen Code, with one compatible model credential shape. | `agents-api/server/bootstrap.py:28`; SDK `managed_agents/models.py`, `providers/alicloud_express/managed.py:34`, guest `server/managed.py:112`; each contains the two-adapter whitelist. | Add adapter-specific native invocation, event/error parsing, auth/protocol mapping and resume behavior through the shared bridge. Do not silently fall back to a different Harness. |
| Evidence boundary | November 12 real Qwen file tasks prove the previous local Guest, not the changed November 13 native-resource release recipe. | The [template repository's November 12 verification](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/048db39f5a865b07343ede2a93393ceab7f2df31/.agents/evidence/verify/2026-11-12-agents-api-final-local-validation.md) explicitly calls its scope local Docker/real model and excludes joint FC E2E; November 13 record calls its changed checks local. | Retain these as history. Record new checks against the exact changed code/image. |
| Product gap, declared | Active steering, external functions/MCP/subagents and session settings are unavailable in the managed profile. | SDK `managed_agents/service.py:102` publishes `features` with these values false; `_enqueue` rejects a default input while a turn is active instead of silently queuing it. | Preserve honest subset declarations and documented errors. Same route names must not be described as complete OpenAI equivalence. Protocol reviewer is checking same-name wire structures separately. |
| Operational limitation, documented | Uncertain publication has no automatic rollback/resume. | `agents-api/scripts/release.py:296-365` records publishing phases and `main` changes uncertain publication to `requires_reconcile`; README explicitly documents retaining resources and inspecting status. | Retain fail-closed behavior. Validate failure recovery before stronger lifecycle claims; do not add broad retry semantics merely to make deployment green. |

## Mechanisms reviewed and worth preserving

1. **No blind execution replay.** Worker `_sent` is persisted before submission. After a failed POST it queries the original receipt, rather than submitting into a fresh runtime (`managed_agents/worker.py:310-371`). Guest epoch changes cause an explicit uncertain/frozen state. The receipt journal is committed before staging/launch (`server/managed.py:269`).
2. **Observation lease differs from execution stop.** A lost creating/submitting claim freezes for reconciliation. Host cancellation/timeout cannot itself claim a remote process stopped. `_close` requires backend destruction confirmation; guest `ProcessDomain` treats unknown/unreadable same-UID processes conservatively (`managed_agents/worker.py:91-180,611-662`; `server/managed_process.py`).
3. **Durable public history with honest native gaps.** Public events are committed before SSE delivery; oversized/native lost events become gap events. SSE cursors are Session-bound, auth is rechecked, and PostgreSQL Session gates order deletion against frame admission (`store.py:185,370`; `http.py:235-340`; `service.py:710`). This is not a claim that all native token/tool events survive guest restart.
4. **Admission/state identity fences.** PostgreSQL transaction advisory locks coordinate application mutation; every transaction checks the pinned database identity; global/revision drain fences new admission (`store.py:235-437`; `service.py:128-143`). This favors correctness at this scale; it is not a performance benchmark.
5. **Upgrade ownership and routing.** Recipe reserve/observed checks stable function identities; publication pins database identity, enables a new Dispatcher with the old/new Worker map, verifies a candidate before switching the stable Gateway alias. Old immutable Workers remain for their Sessions (`release.py:145-174,269-365`). CLI records replaced immutable templates and changed native function names as previous resources so deletion can remove them (`resource_executor.ts:233-234,291,339-367`).
6. **Credential placement.** Gateway sees business-token digest and state/internal control config; Worker sees selected model and sandbox credentials; guest forwarding is explicit. Business/internal keys are distinct, generated private values are reused, explicit process overrides are not copied to their local key store (`bootstrap.py`; `release.py:145-172`; provider `managed.py`).

## Cross-review challenge

The Harness reviewer proposed short-lived headless turns, preserving the same bridge/receipt/process-domain. This reviewer agrees, subject to actual native resume evidence and residual-process cleanup per Harness. OpenCode or another CLI that implicitly launches a daemon needs explicit owned-process lifecycle proof; choosing a daemon mode without it is not acceptable. DeepSeek Harness final `completed` must be combined with process exit status and stop confirmation, and cannot fabricate streamed token deltas.

Protocol reviewer independently found potential same-name Turn/event wire gaps and is reporting those with exact source evidence. A documented feature subset is acceptable; an existing supported event missing fields required by its claimed shape is a separate issue and should be corrected with focused regressions.

## Minimal real acceptance after implementation

Use one controlled application/database and preserve ownership. Do not create a new database for every variant or review.

- Build the exact changed Guest and Server images; verify immutable source/package provenance and non-root startup.
- Exercise public health/auth, create with initial input, explicit queue, active-input unsupported error, idempotent repeat/mismatch, real tool/file result, independent download/content assertion, event reconnect/cursor and cancel-stop confirmation.
- For each of six native Harnesses, verify two actual turns in the same native Session/workspace, original test repair plus artifact download, actual error mapping and process cleanup. A version command or simple model text response is insufficient. Native-login prerequisites are recorded as prerequisites, never replaced by another adapter.
- Update the same deployed application; continue a retained old Session through its pinned old Worker, create a new Session on the new Worker, verify stable URL, observe timer delivery, and check a failing candidate does not switch the stable alias.
- Close/delete Sessions and drain before removing owned FC roles/templates/images selected by task ownership; independently verify no owned live compute remains. Preserve the borrowed database/role/network and report ownership.
- Repeat the independent multi-agent final review twice after code changes; any changed fix gets its own recheck. Only then merge/release components that changed and satisfy their required gates.

No tests were executed by this reviewer. Source/evidence inspection is not a runtime pass, and no new performance, security-isolation or SLA claim is made.
