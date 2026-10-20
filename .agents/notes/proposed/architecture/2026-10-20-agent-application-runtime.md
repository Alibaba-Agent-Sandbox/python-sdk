# Decision: Optional application run control plane
Status: proposed

## Problem

External Agent loops need durable execution independently of a sandbox-local CLI.
Moving the existing local API behind a cloud gateway does not move its loop, and
exposing all local management endpoints would cross ownership boundaries. The SDK
must keep sandbox creation independent of application deployment.

## Decision

Add explicit upper-layer `agent_sandbox.applications` in the client distribution,
without default imports or default PostgreSQL/cloud dependencies. Runtime wiring
comes from the single template's application section through a trusted deployment
factory. Separate HTTP gateway, finite worker and durable-outbox dispatcher roles.
Use PostgreSQL for FC and file-backed SQLite only for explicit local execution.
Keep the existing core local Agents runtime unchanged.

Conditional claims, immutable revision snapshots, transactional acceptance/events/
outbox, cancellation intent and no lease takeover protect uncertain side effects.
An external Python model loop sends shell/files tools to an exclusively owned
sandbox. A narrow in-sandbox adapter reads authoritative final turns/items only.
Bounded small artifacts persist in the database; object-store offload, complete
local event relay, TTL pruning, checkpoints and automatic incident resolution are
explicit later work, not claimed features.

## API Design

`ApplicationRuntime(store, applications, executor_factory, send_task, authenticate)`
provides `create(principal, key, body)`, `dispatch(limit=20, max_seconds=20)` and
`await work(run_id)`. `ApplicationClient` exposes typed async create/get/cancel/
events/result/artifact methods. Public HTTP paths are `/v1/agent-runs`, its run
detail, cancel, events, result and artifact-content resources. Worker/dispatcher
receive private `POST /invoke`; readiness is `GET /healthz` with protocol/revision.
`python -m agent_sandbox.applications gateway|worker|dispatcher` is the entrypoint.

## Alternatives considered

- Add deployment to sandbox create: rejected because it creates hidden cloud side
  effects and strong SDK/cloud dependencies.
- Move the complete local Agents endpoint table externally: rejected because local
  credentials, workspaces and CLI process control have different trust semantics.
- Resume expired leases in the same workspace: rejected because database fencing
  does not fence unknown remote commands or side effects.
- Use SQLite inside FC: rejected because instance-local files are not durable state.
- Persist every artifact in an object store immediately: deferred; P0 bounded
  database retention is implemented and does not claim object-store capability.

## Dependencies

Existing client HTTP/Pydantic dependencies and stdlib HTTP/SQLite. Optional
`applications-postgres` installs psycopg; `applications-fc` adds official FC SDK
and credential chain. Template schema and host deployment ownership remain in
[awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates) and
[agent-sandbox](https://github.com/alibaba-agent-sandbox/agent-sandbox).

## Test Strategy

Lifecycle fault and ownership tests; multi-thread conditional claim/admission;
cancel/success races; expired leases and uncertain cleanup; outbox crash/redelivery;
real PostgreSQL schema/admission/claim/restart locks; separate gateway/dispatcher/
worker subprocesses driving the actual SandboxServer file API through SDK HTTP.
Run repository test/lint/type checks, engineering record and packaging gates.
Cloud acceptance must validate real FC, IAM, model and provider lifecycle with
cleanup evidence; local model fixtures cannot substitute for that gate.

## Acceptance criteria

- Six owned/scoped API operations and explicit typed clients work end to end.
- Accepted runs survive process restart; duplicate requests/tasks do not repeat work.
- Confirmed cleanup precedes cancellation/terminal claims; uncertainty stays visible.
- PostgreSQL enforces concurrency and immutable inputs across processes.
- Template configuration remains single-file; SDK create/import never invokes hooks.
- English/Chinese docs, changelog and verification evidence accompany the change.
- Required full checks and real cloud/model/provider evidence pass before release.

## Evidence

- [Verification](../../../evidence/verify/2026-10-20-agent-application-runtime.md)
- [Direct-process and PostgreSQL verification](../../../evidence/verify/2026-10-20-agent-application-direct-process.md)
- [Runtime guide](../../../../docs/en/guide/agent-applications.md)

- Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/74
- CLI dependency: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/80
- Template dependency: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/139
