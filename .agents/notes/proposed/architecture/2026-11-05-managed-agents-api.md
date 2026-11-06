# Decision: Managed per-Session Agents API and restart-aware guest bridge

Status: proposed

## Problem

Applications should configure one stable endpoint while coding agents execute in isolated,
reusable per-Session sandboxes. The existing local Agents API has process-local receipts and
events; storing a host submission alone cannot prove guest acceptance or authorize replay after
an uncertain create, submission, restart or cancellation. The older draft application runtime
also models per-run execution rather than the reviewed managed Session contract.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/155.
Related historical work: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/74 and
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/75.
Template dependency: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/295.

## Decision

Add the optional `agent_sandbox.managed_agents` client-package runtime with Gateway, Worker and
Dispatcher entrypoints. Add the separate `agent_sandbox.server.managed` private guest listener,
reusing `AgentRuntime` and its real Codex/Qwen parsers without changing the legacy public routes.
The Store persists a random non-secret state identity. An expected identity must exist and match before bootstrap; every subsequent connection verifies the frozen identity. Empty databases and warm-instance backend replacement are rejected. Private database CA input is bounded to 64 KiB/eight certificates, materialized with mode 0600 and passed explicitly to libpq without lowering verify-full.

PostgreSQL is authoritative for owner-scoped acceptance, ordering, public identity, publication,
delete and cleanup. Explicit local SQLite is supported outside FC only.

A Session lazily allocates one owned Express Sandbox and pins its configuration and Worker
revision. Only actual execution creates a public Turn. Explicit enqueue creates a Submission.
Guest receipts persist before staging/launch, bind the original request digest and runtime epoch,
and cannot authorize replay into a new runtime. Uncertain execution freezes the entire Session;
its owned resources continue occupying capacity until independent provider absence is confirmed.

Cooperative process-domain observation includes marked children after leader exit, `setsid` and
reparenting. Incomplete attribution refuses reuse and releases the whole Sandbox. This is not an
audit or isolation guarantee against hostile same-UID code. Tool deadlines start at observed
native start events. Guest limits and independent host projection/stream limits remain finite.
Attachment admission has a 10 MiB aggregate ceiling, including repeated references, before acceptance. Guest RPCs have whole-context wall deadlines clipped to the remaining turn budget. Budget exhaustion preserves unknown outcomes and advances owned cleanup; PostgreSQL statement/lock acquisition have explicit finite server-side timeouts and all acquisition failures close their connections.
Artifacts are immutable regular-file snapshots under `outputs/`, opened through no-follow directory
FDs with bounded enumeration, bytes, depth and time.

Every SSE frame holds a separate cross-process Session gate while a short application transaction
rechecks visibility/authentication, commits and then performs a bounded write. DELETE takes the
same gate before its application transaction. Socket writes never hold the application lock;
bytes already in the network cannot be withdrawn. PostgreSQL uses a separate advisory lock;
local SQLite uses a process-shared file lock. Unknown epochs and native event gaps are explicit.

## API Design

- `ManagedConfig.from_dict(compiled: dict) -> ManagedConfig`: strict non-secret deployment input.
- `ManagedStore(database_url, application_id, local=False)`: shared transactions and stream gates.
- `ManagedService.handle(owner, method, path, body=None, query=None, key='')`: finite business operations.
- `ManagedWorker.run(session_id, submission_id=None) -> bool`: finite claim-fenced execution/observation.
- `ManagedDispatcher.invoke(payload)`: signed dispatch/status/drain with durable admission fences.
- `python -m agent_sandbox.managed_agents gateway|worker|dispatcher`: role-specific HTTP listeners.
- `python -m agent_sandbox.server.managed --port 9000`: authenticated private bridge.

The frozen independent HTTP inventory is `client-sdk/tests/fixtures/managed_api_v1.json`.
The contract uses selected OpenAI-inspired wire shapes and does not claim OpenAI SDK interoperability.
FILE/JSON configuration sources are mutually exclusive. Only Worker receives model credentials.
Explicit provider endpoint, domain, region and API key avoid HOME, registry or Node-engine selection.
TLS verification stays enabled with an optional explicit CA bundle and without inherited proxies.

## Alternatives considered

- **Copy the older run-only draft runtime** — would preserve incompatible per-run ownership and omit
  Session reuse, native receipts and durable operation semantics.
- **Treat a database acceptance or lease expiry as permission to retry** — cannot prove native work
  did not start; may duplicate filesystem or external side effects.
- **Treat native CLI cancellation as complete process stopping** — a detached child can survive
  leader exit. Reuse requires cooperative domain evidence or whole-Sandbox destruction.
- **Hold the global application lock during streaming** — a slow reader would block unrelated
  Sessions. A distinct per-Session gate and bounded write preserve deletion ordering.
- **Enable arbitrary provider discovery or HTTP environment inheritance** — risks selecting an
  unrelated configured account or proxy. Explicit service configuration is narrower.

## Dependencies

The optional `managed-agents` client extra installs psycopg and the official FC Python SDK. The
base server reuses its existing CLI runtime and stdlib HTTP/SQLite. The template repository owns
specification 6, the managed bridge profile and recipes; the CLI owns frozen deployment plans,
credential resolution, FC role/revision routing and public ingress. Both distributions retain
version lockstep; new public template installation requires an actual new matching release.

## Test Strategy

Test all 39 frozen operations through real HTTP with positive behavior and authentication
rejection, against both disk SQLite and real PostgreSQL. Exercise real fixture CLI subprocesses,
files, two-turn continuity, tool wall deadlines, detached descendants, response loss, cancellation,
uncertainty freeze, stream revocation and bounded retention. Run normal coexistence in an isolated
PID namespace so unrelated contributor processes cannot create false process-domain confidence.
Keep deterministic fixtures separate from real cloud/model acceptance. Run all repository gates,
build and fresh-install checks, and record full results independently of public artifact release.

## Acceptance criteria

- All advertised V1 operations pass their observable HTTP behavior and owner/auth boundaries.
- Cancellation/close/delete never claim confirmed stop without cooperative proof or provider absence.
- Restart/response loss never replay uncertain input; frozen Sessions cannot execute queued successors.
- Limits, retention and cleanup remain bounded even with retained tombstone history.
- Existing local Agents API behavior and required package test/CI gates remain green.
- Real Express/model use, independent artifact consumption, cleanup and published-package template
  installation are verified before declaring final delivery or moving this decision to implemented.

## Implementation

The pre-commit Ruff pin is aligned to v0.17.3 and its official `ruff-check` hook, matching the declared client dev toolchain. The old v0.4.9 falsely required eager runtime imports for the existing lazy provider facade. All rule selections, secret checks and Bandit remain enabled; required native Express implementation lives under its provider, with a lazy explicit facade export.

The 2026-11-06 continuation moves the shared `ManagedError` definition into the dependency-free
models layer. Its original `managed_agents.models` path re-exports the same class, preserving
exception identity and the HTTP envelope. The native provider no longer imports the upper
managed application package merely to report a bounded error. A fresh-interpreter regression
demonstrated the previous eager application imports and verifies their absence after the change.
Latest-candidate verification is recorded separately in
[the continuation evidence](../../../evidence/verify/2026-11-06-managed-agents-release-candidate.md);
earlier evidence remains unchanged.

The same continuation makes the existing libpq kwargs precise to the current psycopg type
contract and annotates the host-generated numeric timeout intermediate without changing runtime
expressions. The real provider E2E no longer asserts the obsolete claim that pause is unimplemented;
eligible-template pause/resume remains separately opt-in and is not inferred from base-template
HTTP rejection. Initial failures and corrected replays are retained in the new evidence.

The exact runtime commit passes the complete remote matrix and both public runtime fixtures.
The selected CI distribution identities and the local-filesystem archive-mode difference are
recorded in [the CI artifact evidence](../../../evidence/verify/2026-11-06-managed-agents-ci-artifacts.md).
Public release and managed FC qualification remain separate acceptance conditions.
