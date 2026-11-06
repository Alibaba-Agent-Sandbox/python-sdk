# Managed Agents API

[中文](../../zh/guide/managed-agents-api.md)

Use one Gateway URL and a business bearer token to run coding agents in isolated sandboxes.
A Session creates its sandbox on the first input and reuses its workspace for subsequent turns.
The optional runtime supports the built-in Express provider and explicitly configured Codex or
Qwen Code models. It implements selected OpenAI-inspired resource shapes; it does not claim
OpenAI SDK compatibility or OpenAI-managed harness behavior.

Install the matching client and server packages with the managed deployment dependencies:

```bash
python -m pip install --pre 'agent-sandbox-client[managed-agents]==0.4.0a7'
```

The [agents-api template](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/tree/main/agents-api)
provides the application configuration. Deploy it with the matching
[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox). Applications connect to the
returned Gateway endpoint; they do not configure individual sandbox endpoints.

## Send input and read results

Set `AGENTS_API_URL` to the Gateway URL and `AGENTS_API_KEY` to your business token. The token is
issued by your deployment operator. It is separate from the Sandbox API Key, cloud credentials,
model API Key and sandbox application token. The template deployment prepares the private sandbox
application token automatically.

```python
import os
import httpx

with httpx.Client(
    base_url=os.environ["AGENTS_API_URL"],
    headers={"Authorization": "Bearer " + os.environ["AGENTS_API_KEY"]},
) as api:
    response = api.post(
        "/v1/agents/sessions",
        json={
            "agent": {"model": "your-deployment-model"},
            "input": "Write outputs/report.txt containing a short summary.",
        },
        headers={"Idempotency-Key": "report-session-1"},
    )
    response.raise_for_status()
    session_id = response.json()["id"]
    print(session_id)
    print(response.headers["X-Agent-Sandbox-Submission-Id"])
```

Creation returns `201`. Input reception returns a durable Submission, while a public Turn appears
when execution starts. Poll the Session and its `/turns` and `/artifacts` collections. Download a
published artifact through `/v1/agents/sessions/{id}/artifacts/{artifact_id}/content`.
A subsequent `POST /v1/agents/sessions/{id}/events` with `{"input":"Continue"}` returns `202`,
an empty body, a Submission ID header and its `Location`. Repeat the same idempotency key and body
to retrieve the original acceptance; use a different key for a new input.

Input during an active turn returns `409 active_turn_not_steerable`. Explicit queuing uses
`POST /v1/agent-sandbox/sessions/{id}/submissions`, requires `Idempotency-Key`, and returns `202`
with a Submission object. Queuing schedules another turn; it does not steer the active turn.

## Files and events

Upload files with multipart `POST /v1/files`, fields `purpose=user_data` and `file`. Attach an
uploaded file to input using `x_agent_sandbox.input_files: [{"file_id":"file_...",
"path":"/workspace/input/data.csv"}]`. Paths must be normalized beneath the deployment's
`input` directory. Existing files cannot be overwritten. The input snapshot is fixed when the
submission is accepted; deleting the public File does not revoke an already accepted attachment.
A submission accepts at most 10 MiB of attachments in total (`max_total_input_file_bytes`), counting every reference even when the same File is reused. An oversized batch returns `413` before a Session or Submission is accepted.
Only regular files under `outputs/` are published as immutable artifacts. Symbolic links,
unreadable or changing files are rejected and reported as partial publication.

Subscribe with `GET /v1/agents/sessions/{id}/events`. Supply `Last-Event-ID` or `after` to resume;
`after=0` replays from the beginning, while omission tails new events. Streams close periodically;
reconnect using the last received event ID. Public events are durable during result retention. Deletion stops new frame writes across Gateway instances; a frame already in the network may finish arriving. Slow readers are disconnected, and oversized frames report a gap; use the durable items API for full content.
A native event gap is reported explicitly. Raw reasoning and provider secrets are not exposed.
The Gateway sends HTTP/1.1 chunked event-stream responses. An FC deployment needs a Web Gateway
which supports streaming responses; events received only after completion do not establish live streaming.

## Close, cancel and delete

Cancel a queued Submission through its `/cancel` endpoint. Cancel active work by its exact Turn
or Submission ID, then poll the returned Operation until `stop_confirmed` is true. A cancellation
request is not proof that execution has stopped. Cooperative process observation may allow Session
reuse. If stopping cannot be established, the runtime releases the whole sandbox and closes the
Session. An unresolved provider result remains `requires_reconcile` and occupies capacity.

`POST /v1/agent-sandbox/sessions/{id}/close` returns `202` and an Operation. It stops admission for
that Session, releases compute and retains published results until their retention deadline.
`DELETE /v1/agents/sessions/{id}` returns `200` and immediately removes public access; active
execution returns `409` until cancelled or closed. Physical cleanup may continue asynchronously.
Closing and deleting have different effects. Always close Sessions when finished and inspect
Operation results before treating resource cleanup as complete.

## Supported resources and limits

| Resource | Operations |
| --- | --- |
| Platform | Health, capabilities, model list/detail, runtime list |
| Agents | Create, list, read, update, delete saved configurations |
| Sessions | Create, list, read, metadata update, delete, input/events, items |
| Turns | List, read, per-turn items, exact cancellation |
| Artifacts | List, metadata, byte download, delete published snapshot |
| Files | Multipart upload, list, metadata, byte download, delete |
| Environments | Read-only list and detail |
| Managed lifecycle | Close, Operations, Submission enqueue/list/detail/cancel |

`GET /v1/agent-sandbox/capabilities` returns the supported routes and deployment budgets.
Lists accept `limit`, `order` and `after`; use `last_id` or the scoped `next_cursor` for the next page.
Session updates support metadata only. Function tools, arbitrary MCP configuration, subagents,
steering, image/audio input and dynamic model/settings changes are rejected. Shell/file tools
provided by the selected CLI remain available inside its sandbox. Tool wall deadlines begin at
observed native tool-start events. Unknown runtime epochs or uncertain submission receipts freeze
execution; they never automatically replay an input.

The Gateway requires PostgreSQL for FC deployment. SQLite is restricted to explicit local mode.
Storage, queues, execution time, events and subscribers have finite deployment budgets; quota
rejection returns `429`. Expired results return `410`; deleted resources return `404`. Cleanup
preserves private ownership records required to resolve uncertain resources.

## Operator configuration

Run `python -m agent_sandbox.managed_agents gateway|worker|dispatcher`. The guest image runs
`python -m agent_sandbox.server.managed --port 9000`; it requires Codex or Qwen Code installed.

Each configuration document accepts exactly one `_FILE` or `_JSON` source:

| Variable prefix | Document |
| --- | --- |
| `ABX_MANAGED_CONFIG` | Compiled revision, application ID, template, model/adapter allowlist, `modelEnvAllowlist`, Session/storage/execution budgets, `expectedStateId` and retained Worker mapping |
| `ABX_MANAGED_AUTH` | `tokens: [{sha256,owner,scopes,expiresAt?}]`; scopes are `agents:read` and `agents:write` |
| `ABX_MANAGED_MODEL_CONFIG` | Worker-only `{apiKey,baseUrl,model,adapter}` |
| `ABX_MANAGED_PROVIDER_CONFIG` | Worker/Dispatcher `{provider:"alicloud-express",apiKey,baseUrl,domain,region}` |

`ABX_MANAGED_DATABASE_URL` identifies PostgreSQL. The deployment pins its persistent state identity; replacing the database with empty state is rejected, including by warm instances. Credential and CA rotation on the same state remains supported. `ABX_MANAGED_INTERNAL_TOKEN` authenticates private
role invocations and must remain stable while retained revisions drain.
`ABX_MANAGED_FC_ENDPOINT` selects the explicit FC service host for dispatch.
`modelEnvAllowlist` must explicitly allow `OPENAI_API_KEY`, `OPENAI_BASE_URL` and `OPENAI_MODEL`.
Credentials are passed only to roles which need them, and never put in images or public resources.
File-backed business authentication is reread for revocation; optional token expiry is enforced.

Normal revision updates reuse the existing application and database through the previous
deployment receipt. Destroying the complete deployment retains externally managed PostgreSQL
data and leaves that application identifier closed. To create another deployment afterward,
use a new template/application name or a new empty PostgreSQL database. Retain the original
receipt for cleanup and reconciliation.

TLS certificate verification remains enabled. The private bridge HTTPS client uses the system trust store without
inheriting HTTP proxy settings. To trust a private CA, set `ABX_MANAGED_TLS_CA_FILE` to a readable
PEM CA bundle. Invalid CA configuration fails; it does not disable verification.

For a database which requires a private CA, supply `ABX_MANAGED_DATABASE_CA_PEM` to the three Server roles. It accepts only 1–8 PEM certificates, at most 64 KiB. The runtime writes a private temporary CA file and passes it to libpq while preserving the connection URI’s `sslmode=verify-full`. This setting is separate from the guest HTTPS CA setting and is never sent to the sandbox.

Deployments with limited environment-variable space can pass the public CA bundle as
`--database-ca-base64 BASE64_PEM` after the role name. Use canonical Base64 of ASCII PEM; this
argument and `ABX_MANAGED_DATABASE_CA_PEM` are mutually exclusive. Keep database credentials,
model keys and internal tokens in their existing credential configuration. The same certificate
validation and private temporary file apply. The runtime's 64 KiB decoded bound does not guarantee
that a deployment platform accepts startup arguments of that size; platform limits still apply.
The argument accepts multiple Base64 segments, concatenated before validation. The FC deployer
splits the public certificate value into bounded arguments to satisfy its per-argument limit.

Guest HTTPS exchanges have a total wall deadline of 30 seconds, clipped to the remaining execution budget during a turn. If that budget expires with an unknown result, the runtime attempts owned compute cleanup and retains an uncertain Submission; a public Turn reports the Gateway failure separately from the unconfirmed agent outcome. PostgreSQL connections use a 10-second connection/statement timeout and a 5-second lock timeout. URI `options` overrides are rejected.
