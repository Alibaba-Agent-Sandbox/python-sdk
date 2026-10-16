# Decision: Share provider management command contracts with the Node host
Status: proposed

## Problem

Provider features describe the standard sandbox protocol, while cloud-specific resource
operations have no shared discovery, consent or invocation contract. Reusing runtime named
commands would mix infrastructure operations with functions inside a sandbox. Automatic HTTP
replay can duplicate a resource mutation after a lost response.

Owner Issue: <https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34>.
Host dependency: <https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/30>.

## Decision

Parse bounded `provider-commands/1` descriptors in Python and include complete, ID-sorted
command descriptions in installation/update consent. Missing sections and legacy receipt
fields mean empty command sets. Nonempty command sets belong to node/exec providers only.
Python performs structural validation; the Node host owns strict schema compilation, input
and output validation, confirmation, dispatch and cloud APIs. No cloud SDK is added here.

Expose a thin asynchronous engine API in `providers/commands.py`. Require explicit matching
provider identity, keep metadata discovery free of credential resolution, and send POST invocation once, with `confirm=False` unless explicitly
changed by the caller. Keep existing EngineClient retry behavior for other callers through
a backward-compatible `retry=True` default. Do not replay command POST requests even when
an operation declares itself idempotent.

The built-in provider no longer declares `ports.domain`, `storage.mount` or `network.vpc`:
no callable standard sandbox protocol exists for those tokens. Resource commands are separate
and do not imply live mounting or networking support. Other feature declarations stay scoped
outside this decision.

Final review found a documented creation-time mount contract that resource management alone
did not cover. Add `Sandbox.create(volume_mounts: dict[str, str] | None = None)` for the built-in
provider, mapping normalized absolute sandbox paths to existing Volume names. Validate before
provider lookup/construction and reject non-built-in nonempty hints with E8004 before plugin
loading. Preserve omitted/empty request behavior. This is an explicit creation option, not a
portable mount feature or runtime attach protocol. The built-in Python lifecycle still uses
the existing gRPC engine: add map field 16 to `CreateRequest`, regenerate its Python descriptor
with the matching protobuf compiler, and serialize `volumeMounts: [{name, path}]` in the
existing Python `SandboxConfig`/REST protocol. Do not reroute established sessions to Node.
The official OSS guide supplies name/Team/role semantics and mount restrictions; storage-type
limits remain backend-specific rather than applying an OSS-only limit to every Volume.
Add `HealthStatus.supported_create_options` field 4 and advertise `volume_mounts`; a client
with nonempty hints requires that capability before sending Create. An older live engine
otherwise silently discards unknown protobuf fields and could create an unmounted sandbox.
Missing support fails E8004 with an upgrade/restart hint without replacing the existing
engine. No-mount calls do not require this additive capability handshake.

## API Design

- `Manifest.commands: tuple[ProviderCommand, ...]`; descriptors contain `id`, `description`,
  `description_zh`, `input_schema`, `output_schema`, `effect`, `idempotent`.
- `providers.commands.list_commands(provider)` returns descriptor dictionaries;
  `get_command(provider, command_id)` returns one descriptor. These static metadata calls
  send only provider identity and do not resolve configuration or credentials.
- `providers.commands.run_command(provider, command_id, input=None, *, confirm=False,
  provider_options=None, **config)` returns the engine's JSON result.
- GET `/v1/providers/:id/commands` returns `{commands: [...]}`; GET
  `/v1/providers/:id/commands/:command` returns a descriptor; POST to the latter route sends
  `{input, confirm}`. Authentication and connection headers use `abx-engine/1`.
- `EngineClient.request(..., retry=True)` gains an optional retry switch. Command invocation
  always passes `retry=False`, including reads, so no POST is transparently replayed.

## Alternatives considered

- **Arbitrary CLI command registration** — conflicts with the static CLI surface; the Node
  host keeps a fixed provider management namespace instead.
- **Duplicate Python cloud implementations** — would diverge from Node handlers and schemas.
- **New entries in the fixed feature registry** — those features describe portable sandbox
  behavior, not arbitrary provider resource operations.
- **Automatic retries for declared idempotent operations** — callers need to reconcile lost
  responses and make explicit retry decisions.

## Dependencies

The existing `httpx` EngineClient, provider registry and layered configuration resolver.
The compatible shared host is maintained in the
[CLI repository](https://github.com/alibaba-agent-sandbox/agent-sandbox).
No new runtime dependency or package version change is introduced.

## Test Strategy

Manifest tests cover bounds, forbidden schema/JSON fields, duplicate IDs, descriptions,
legacy manifests, and rest-provider rejection. A real filesystem installation verifies
command additions require renewed consent. Adapter tests verify route/body/connection
shape, explicit confirmation, cleanup, metadata discovery without plugin execution, and
no replay after disconnect or HTTP 401. Existing manifest/installer/registry tests remain.
Run both package suites, lint/type checks, repository health/hygiene and real-component
E2E; record unavailable prerequisites and pre-existing gate failures separately.

Independent agents may review disjoint contracts and source in parallel, with one coordinator
reconciling cross-language changes. Suites that share fixed loopback ports run sequentially.
Each test invocation gets its own temporary root and unique Unix socket; PID-only names do
not provide isolation across namespaced tool processes sharing a filesystem. Final review
demonstrated that a reused default engine can miss a test's in-process HTTP patches; the same
integration tests pass on a unique socket. Preserve failed runs, retry with proven isolation,
and never kill or replace an unknown process to obtain a pass.

## Acceptance criteria

1. Python structural descriptor rules match the shared host and changed descriptors require consent.
2. Legacy plugin manifests/receipts remain usable with empty commands.
3. Python cloud management calls use one Node implementation and an explicit provider connection.
4. Mutations require host confirmation and command POST requests are sent at most once.
5. Built-in feature reporting excludes the three standard operations without callable protocols.
6. English/Chinese guides, public exports, changelog and honest verification evidence are provided.
7. Required CI, review and real-component gates pass before merge; this record stays proposed meanwhile.
8. Built-in create retains mount hints across the public API, real local gRPC transport and
   HTTP wire serialization; strict validation and provider gating precede resource I/O.
   A real Volume mount/read/write/cleanup run is still an outstanding acceptance gate.

## Evidence

[Verification record](../../../evidence/verify/2026-10-16-provider-management-commands.md).
[Final review and mount parity](../../../evidence/verify/2026-10-16-provider-management-final-review.md).
[Final isolated suite and main synchronization](../../../evidence/verify/2026-10-16-provider-command-integration-final.md).
