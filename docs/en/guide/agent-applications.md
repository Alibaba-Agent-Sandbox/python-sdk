# Agent applications: external and in-sandbox execution

The optional `agent_sandbox.applications` upper layer runs an application control
plane independently from the sandbox-local Agents API. The default SDK imports,
`Sandbox.create()` and `ProviderSandbox.create()` do not deploy applications or run
template hooks. Application configuration stays in the optional `application:`
section of `template.yaml`; there is no second application manifest.

The template schema and host deployment workflow belong to the
[template catalog](https://github.com/alibaba-agent-sandbox/awesome-templates) and
[abx CLI](https://github.com/alibaba-agent-sandbox/agent-sandbox). This guide covers
the Python runtime. These changes are source-checkout functionality pending cloud
acceptance; do not assume an already published wheel contains this module.

## Two placements

* **External:** a trusted Python model/tool loop runs in a worker. Its shell and
  file tools use an exclusively owned remote sandbox. Generated code is never
  executed in the gateway or worker process.
* **In-sandbox:** the existing core Agents API runs the CLI locally in a sandbox.
  Direct clients continue to use that API. `InSandboxAgentExecutor` additionally
  supports a managed gateway with a narrow session/input/turn/items adapter. It
  checks actual endpoint discovery and terminates the whole owned sandbox during
  cleanup. It does not forward arbitrary local endpoints or implement a complete
  relay of the local in-memory progress-event buffer. P0 publishes final output.

Moving a gateway to FC does not move an Agent loop. `runtime.driver` identifies
the integration (`python-remote-tools` or `sandbox-local-api`); the local CLI name
is separately selected by `ABX_APP_LOCAL_AGENT` (`codex` by default). The managed
adapter requires `server-core-agents`; legacy template-specific protocol overrides
are not accepted.

## Source installation and entrypoints

From this repository checkout:

```bash
pip install -e ./server-sdk -e './client-sdk[applications-fc]'
python -m agent_sandbox.applications gateway
python -m agent_sandbox.applications worker
python -m agent_sandbox.applications dispatcher
```

Each command starts an HTTP service on `ABX_APP_BIND` / `ABX_APP_PORT` (defaults
`0.0.0.0:9000`). Run them in separate processes, containers or functions; use
distinct ports when sharing a host. The gateway exposes
the six business operations below. Worker and dispatcher expose only private
`POST /invoke`; a worker response is returned after work and cleanup, with no
background continuation after a `202`. FC custom containers forward signed
InvokeFunction payloads to this `/invoke` path.
[Official FC invocation protocol](https://www.alibabacloud.com/help/en/functioncompute/code-development-in-custom-container-runtimes).

All roles expose `GET /healthz` (`/health` alias). Gateway readiness returns
`status: ok`, the configured revision, `protocol: agent-sandbox-runs/v1`, and the
implemented `operations` list. Factories initialize state before readiness. A
health response establishes protocol/configuration readiness, not IAM, model or
sandbox execution acceptance.

`--once` on worker/dispatcher instead reads one JSON invocation from stdin and
exits; it is for local verification. FC uses the HTTP listener.

## Production configuration

`ABX_APP_FACTORY=module:function` optionally loads trusted packaged code returning
`ApplicationRuntime`. The default is
`agent_sandbox.applications.config:default_factory`. This is deployment code, never
a module/path supplied in a business request.

The default factory consumes the following deployment bindings:

| Variable | Meaning |
| --- | --- |
| `ABX_APP_SPEC_JSON` | Non-secret application subsection, compiled from the single template: runtime, sandbox, state, bindings and limits |
| `ABX_APP_REVISION` | Immutable deployed application revision |
| `ABX_APP_SANDBOX_TEMPLATE` | Actual prepared provider template/reference |
| `ABX_APP_SANDBOX_PROVIDER` | Provider identity for that prepared reference |
| `ABX_APP_DATABASE_URL` | Resolved PostgreSQL connection secret, supplied at runtime |
| `ABX_APP_AUTH_FILE` | Mounted JSON token-hash/owner/revision/scope allowlist |
| `ABX_APP_INTERNAL_TOKEN` | Separate private invocation credential, at least 32 characters |
| `ABX_APP_FC_ENDPOINT` | Account FC API hostname, without URL scheme |
| `ABX_APP_WORKER_FUNCTION` | Existing deployed FC Task function name |
| `ABX_APP_MODEL_ENDPOINT` | HTTPS Chat Completions-compatible endpoint, external placement only |
| `ABX_APP_MODEL`, `ABX_APP_MODEL_API_KEY` | External model identity and separately bound credential |
| `ABX_APP_LOCAL_AGENT` | Core local CLI adapter, in-sandbox placement only |

Binding references in YAML are names; the runtime never interprets them as secret
values. Resolve them into environment variables or mounted files through the
deployment environment. Sandbox API configuration uses the existing SDK's
authentication configuration. The B sandbox must separately receive its own local
CLI/model credentials through its template or a trusted custom sandbox factory.
Control-plane database, cloud and business credentials must not be injected into
the generated-code workspace. A local CLI and code running with the same sandbox
UID do not have credential isolation from each other.

The FC sender uses the official `alibabacloud-fc20230330` SDK, default credential
chain/function role, asynchronous invocation and the run ID as native task ID.
It signs a role-scoped HMAC JSON invocation envelope in the event body; the raw
private token is never included. This does not depend on arbitrary API headers
being forwarded by FC. A direct private HTTP caller may alternatively use
`X-ABX-Internal-Token`. Require private ingress, least-privilege function roles and async Task
configuration. The dispatcher must have a periodic external trigger with a presigned dispatcher
envelope. `sign_invocation({"limit": 20}, token, role="dispatcher")` generates it.
FC time triggers place this serialized envelope in their configured `payload`
string; the runtime unwraps documented triggerTime/triggerName/payload metadata
and verifies the inner signature. Invocation replay is safe through run/outbox
claims; key rotation must coordinate pending invocations.
[Official timer event format](https://www.alibabacloud.com/help/en/functioncompute/time-triggers).
The dispatcher must be triggered externally; gateway
acceptance is durable even if no dispatcher is currently running. Dispatcher
batches are capped at 100 and a 20-second scheduling window plus one bounded SDK
call; allow at least 60 seconds per dispatcher invocation. Worker timeout must
exceed `maxRunSeconds` plus cleanup margin.

Token allowlist format (store only a SHA256 digest of a sufficiently random
bearer token; the example digest is deliberately invalid):

```json
{"tokens":[{"sha256":"REPLACE_ME_SHA256","owner":"team-a","revisions":["revision-a"],"scopes":["runs:read","runs:write"]}]}
```

The file is reloaded on every request and during SSE polling so removal revokes
access. A custom factory can provide an expiring OIDC/JWT authenticator instead.

## Run API and client

| Operation | Endpoint |
| --- | --- |
| Accept input | `POST /v1/agent-runs` |
| Read state | `GET /v1/agent-runs/{id}` |
| Request cancel | `POST /v1/agent-runs/{id}/cancel` |
| Read committed events | `GET /v1/agent-runs/{id}/events` |
| Read terminal result | `GET /v1/agent-runs/{id}/result` |
| Download owned artifact | `GET /v1/agent-runs/{id}/artifacts/{artifact_id}/content` |

```python
from agent_sandbox.applications import ApplicationClient

async def submit(base_url: str, business_token: str) -> str:
    async with ApplicationClient(base_url, business_token) as client:
        run = await client.create("revision-a", "Analyze the files", idempotency_key="request-1")
        async for event in client.events(run.id):
            print(event.seq, event.type)
        return run.id
```

Create requires `Idempotency-Key` (1–128 printable ASCII characters) and exactly
`{"applicationRevision":"revision-a","input":{"text":"..."}}`. The authenticated
principal supplies ownership; requests cannot select another owner. A matching
owner/revision/key/body replays the same run; a changed body returns 409. Foreign
and missing runs return the same 404. Missing authentication is 401, missing scope
403, capacity exhaustion 429, unavailable state 503. Result reads return 409 until
terminal. All six client methods are explicit; mutations are not automatically
retried.

SSE returns up to a 20-second connection; reconnect with the last decimal sequence
in `Last-Event-ID` / client `after`. Network disconnect never cancels a run. Events
are committed before transmission. No exactly-once event delivery is promised.
P0 retains all bounded run events; automatic TTL pruning, expired-cursor 410 and
object-store artifact offload are not implemented.

## Durability, cancellation and budgets

PostgreSQL acceptance commits the run, first event and dispatch outbox together.
Revision snapshots include ready sandbox identity, placement, model identity,
binding references and execution/admission budgets. Reusing a revision with changed
inputs fails closed. Application-wide row locking enforces admission and worker
concurrency across processes. Native task delivery may be duplicated; conditional
claims create one attempt. Transient send failure keeps the outbox for bounded
backoff until the run deadline. Unclaimed runs can safely expire without creating
a sandbox.

Cancellation commits intent before reporting it. The worker checks before model,
tool and resource calls, cancels its cooperative coroutine, and confirms remote
sandbox cleanup before recording `cancelled`/`timed_out`/other terminal outcomes.
A committed cancellation wins a concurrent success. Cleanup failure, ambiguous
creation, or an expired worker lease yields `requires_reconcile`; no new worker
takes over that workspace. Database lease fencing alone cannot stop a remote shell.
An operator must inspect/terminate the tagged exclusive sandbox and prove the
old native worker cannot continue, including pending creation. Trusted
`Store.resolve_uncertain(run_id, expected_attempt, verify_quiesced)` accepts an
operator-supplied verifier outside database locks and compares the observed
attempt/resource again before finalizing. Unknown creation requires a search by
run metadata, not merely checking an absent receipt. A false verification leaves
the run fenced and capacity occupied; no business HTTP operation exposes this
method. Resolve only after real native task and sandbox verification; automatic resource reconciliation and resume/checkpoint are not part of
P0. Snapshot TTLs bound sandbox lifetime but do not prove side effects stopped at
the instant a worker disappears.

The external loop defaults to 30 model steps and explicitly authorized remote
shell/read/write/artifact tools. Tool calls use `maxToolSeconds`; run/event/output
and concurrent/queued/rate budgets are captured immutably. Final output text is
capped at the smaller of `maxOutputBytes` and 65,536 UTF-8 bytes. P0 artifacts are
copied into PostgreSQL, capped at 100 files and 10 MiB total by default; content is
downloaded as octet-stream. No arbitrary artifact path or URL is accepted by the
public API. Artifacts are small-result retention, not a bulk object storage API.

## Local verification and remaining gates

Docker is not required to test the Python runtime. Gateway, worker and dispatcher
can run as ordinary Python processes, and `pgserver` supplies a real temporary
PostgreSQL server without a container. From the repository root:

```bash
python -m pip install -e ./server-sdk -e './client-sdk[dev,applications-fc]' pgserver==0.1.4
python -m pytest client-sdk/tests/test_applications -q -ra
# Real remote sandbox; requires existing E2B_API_KEY and regional SDK configuration:
python -m pytest e2e/test_10_application_runtime.py -q -ra
```

The HTTP scenario runs against both SQLite and PostgreSQL, including gateway
restart, idempotency, private invocation authentication, remote file/artifact APIs,
SSE replay and cancellation. PostgreSQL cases explicitly skip if their optional
dependencies are absent; cloud tests skip without credentials. A skip is not a pass.
The cloud scenario uses a deterministic model and real remote shell/files/artifacts.

SQLite is accepted only with `Store(url, local=True)` / `ABX_APP_LOCAL=1`, and is
rejected when FC function/instance environment markers are present. Never put an FC
control database in its ephemeral filesystem.

```bash
cd client-sdk
pytest tests/test_applications -m 'not integration'
# Optional real local PostgreSQL transaction/locking test, verification dependency only:
pip install pgserver==0.1.4 'psycopg[binary]>=3.2,<4'
pytest tests/test_applications/test_postgres.py
```

The subprocess integration test runs real gateway, worker and dispatcher HTTP
processes, a real SandboxServer file API, a deterministic model fixture, restart,
idempotency, artifacts and SSE. It does not establish cloud network/IAM, FC image
compatibility, real LLM behavior or operating-system sandbox isolation. A temporary
local PostgreSQL server is not a production managed-state binding. Image construction
can run in CI or another build environment; a local Docker installation is not
required for runtime or remote-sandbox testing. Actual FC image deployment and
its persistent state, IAM and ingress still require separate acceptance. Real FC,
model and provider acceptance plus required remote CI/review remain release gates.

Custom executor callbacks must cooperate with asyncio cancellation; blocking
application callbacks need process isolation. A pending task after bounded cleanup
stays `requires_reconcile`. The event budget must allow at least five lifecycle
events, reserving cancellation, uncertainty and verified recovery transitions.
