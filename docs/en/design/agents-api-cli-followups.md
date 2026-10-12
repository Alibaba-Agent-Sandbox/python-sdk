# Agents API — required `ebx` CLI follow-ups (spec)

The `ebx` CLI now lives in the Node/TypeScript repository (`/workspace/cli`) and
was **not** edited by this workstream. This file is the spec for the CLI team.
Design context: [agents-api.md](agents-api.md).

The CLI should be a thin client over the HTTP surfaces the sandbox exposes
(Responses wire and native `/agents/**` routes), so it needs **no Python** and
no knowledge of adapters. All routes require the `agents` capability group to be
enabled on the target server (disabled by default).

## 1. Command surface

```
ebx agent host start   <sandbox-id> [--port 9100] [--install] [--agent agent.yaml]...
ebx agent host stop    <sandbox-id>
ebx agent host status  <sandbox-id>               # GET /agents/health + /agents/runtimes
ebx agent runtimes     <sandbox-id>               # GET /agents/runtimes (installed, version, experimental)
ebx agent install      <sandbox-id> <runtime>     # POST /agents/runtimes/{name}/install
ebx agent doctor       <sandbox-id> [name]        # POST /agents/runtimes/{name}/doctor + definition validation
ebx agent define       <sandbox-id> agent.yaml    # PUT /agents/definitions/{name}  (YAML→JSON client side, ${VAR} expanded from the local env)
ebx agent list         <sandbox-id>               # GET /agents/definitions
ebx agent run          <sandbox-id> <agent|runtime> "<prompt>" [--session ID | --continue] [--stream] [--json] [--timeout 1800]
ebx agent sessions     <sandbox-id> [list|get ID|cancel ID|delete ID]
ebx agent logs         <sandbox-id> <session-id> [--follow] [--after SEQ]   # GET /v1/agents/sessions/{id}/events (SSE)
ebx agent openai-env   <sandbox-id> --remote-url URL --environment-id ID    # runs `codex exec-server`, key via env OPENAI_EXECUTOR_API_KEY
```

`<sandbox-id>` resolution is the same as every other `ebx sandbox …` command.
`ebx agent run` without `host start` should auto-start a host (idempotent) unless
`--no-bootstrap` is given.

## 2. Transport details

* Endpoint URL: `https://{port}-{sandbox_id}.{domain}` (existing port-URL rule).
  Auth: send the sandbox access header (`X-Access-Token`) **and**, for the
  agents routes, `Authorization: Bearer <host token>`; `ebx agent host start`
  prints/stores the host token (keychain or `~/.config/ebx/agent-hosts.json`,
  mode 0600; never echo it unless `--show-token`).
* `host start` = same bootstrap as the Python client:
  1. `pip install easy-sandbox-server==<matching version>` when
     `python3 -c "import easy_sandbox.server.agents"` fails;
  2. start `python3 -m easy_sandbox.server.agents serve --port 9100` with env
     `EBX_SERVER_TOKEN=<random>` and `EBX_AGENTS_ALLOW_INSTALL=1`
     (**env, never argv**);
  3. wait for `GET /health`.
* Streaming: Responses SSE (`stream: true`) — print `response.output_text.delta`
  as text; `--json` prints raw events as JSON lines. Reconnect with
  `GET /v1/responses/{id}?stream=true&starting_after=<last sequence_number>`.
* Cancel: Ctrl-C → `POST /v1/responses/{id}/cancel`, then exit 130.

## 3. Config & secrets

* `agent.yaml` schema = design §4. The CLI expands `${VAR}` from the local
  environment, errors on unset variables (names the variable), and **never
  prints secret values** (`--verbose` shows `***`).
* Secrets are sent only in the `PUT /agents/definitions` body over TLS.
* `ebx agent define --lock` should print the server-side
  `EBX_AGENTS_LOCK_DEFINITIONS=1` hint; the CLI does not set it.

## 4. Exit codes

| Code | Meaning |
|---|---|
| 0 | turn `completed` |
| 1 | turn `failed` (error code printed: `authentication_error`, `rate_limit_exceeded`, `request_timeout`, `runtime_not_installed`, …) |
| 2 | CLI usage / config error (incl. unset `${VAR}`) |
| 3 | host unreachable / agents group disabled (404 "is disabled") |
| 124 | `--timeout` elapsed (CLI cancels the response first) |
| 130 | interrupted (response cancelled) |

## 5. MCP / existing commands touched

* `ebx mcp` (sandbox MCP server) may expose three tools: `agent_run`,
  `agent_cancel`, `agent_sessions`, implemented on the same routes.
* `ebx sandbox port-url` should offer `--bearer` to print
  `Authorization: Bearer …` alongside the existing headers (useful for the
  official `openai` client: `OPENAI_BASE_URL=<url>/v1`, `OPENAI_API_KEY=<host token>`).
* `ebx agent run --openai-compat` prints the `OPENAI_BASE_URL`/`OPENAI_API_KEY`
  exports for a started host.
* JSON output schema for `--json` summary line:
  `{"response_id","session_id","status","output_text","usage":{…},"error":null|{"code","message"}}`.

## 6. Tests the CLI repo should add

* Golden tests for exit codes using a stub HTTP server that replays the SSE
  transcripts in `server-sdk/tests/test_server/fixtures/agents/*.sse`.
* A test that `--verbose` never prints a secret value and that no secret is on
  any spawned process argv.
