# Agents API

HTTP sessions inside the sandbox. All 70 routes are implemented. Two runtimes have a local backend: Codex and Qwen Code. `claude-code`, `cursor` and `command` are declared adapters without a local backend, and `GET /v1/agents/runtimes` says so. The base image does not install either CLI. Install the one you are about to call.

This is the one way to run an agent in a sandbox: the routes under `/v1/agents/sessions`. The SDK has no `sb.agent.*` helpers.

Field-by-field refusals are in [Hosted agents](hosted-agents.md). The route table is in the [Agents API reference](../reference/agents-api.md). This page is the path you can finish.

## Install a CLI

Install one CLI. Installing both into the base image makes the image large. When the request does not name an adapter, the server uses the first in the product order: `codex`. Name Qwen Code in the request, or set `ABX_AGENTS_DEFAULT=qwen-code`, to use the other one.

```bash
npm install -g @openai/codex          # binary name: codex
npm install -g @qwen-code/qwen-code   # binary name: qwen
```

Codex reads `OPENAI_API_KEY` or `CODEX_API_KEY` when it actually calls a model. Qwen Code reads `OPENAI_API_KEY`. Inject the key when the sandbox is created. Do not bake it into the image, and do not put it in the case below.

The [agents-cli](https://github.com/alibaba-agent-sandbox/awesome-templates/tree/main/agents-cli) template does not turn on `file_ops` or `process`. `endpoints` sets `*` to `enabled: false`, then turns on `agents_sessions_create`, `agents_sessions_events_create`, `agents_sessions_items_list`, and `agents_runtimes_list` one by one. `POST /shell` and `POST /v1/agents` (definitions) stay 404. The Dockerfile leaves the one `npm install` line for the CLI you call.

## Complete case

The case starts a local server and places programs named `codex` and `qwen` on `PATH` so the requests and responses can be shown without a model key. After the `npm install` lines above, the same requests run the real CLIs.

```bash
python examples/agents/complete_case.py
```

The shapes below are what the server returns. The server assigns the session id.

When the request does not name an adapter, the server uses the first in the product order (`codex`). A model id such as `gpt-5` is passed to that CLI. It does not switch the adapter:

```text
POST /v1/agents/sessions  {"agent":{"model":"gpt-5"}}  200
agent.id: codex
agent.model: gpt-5
X-Agent-Sandbox-Local: 1
```

`GET /v1/agents/runtimes` uses the same paging as the other lists, so the default `order` is `desc`. Pass `order=asc` to see the product order: `codex`, `qwen-code`, then the declared-only adapters. `default: true` marks the runtime used when the request does not name one. The flag does not follow the array index. With no config it is on `codex`. After `ABX_AGENTS_DEFAULT=qwen-code` it moves to `qwen-code`.

Name the other one:

```text
POST /v1/agents/sessions  {"adapter":"qwen-code","agent":{"model":"gpt-5"}}  200
agent.id: qwen-code
agent.model: gpt-5
```

A declared adapter with no local backend, for example `claude-code`:

```text
POST /v1/agents/sessions  adapter=claude-code  404
X-Agent-Sandbox-Local: 1
type: not_found_error
code: agents.not_implemented_locally
param: adapter
message: adapter 'claude-code' is declared but has no local backend; GET /v1/agents/runtimes reports which runtimes are implemented (codex, qwen-code) and installed
```

`GET /v1/agents/runtimes` lists every declared runtime. Each entry has `implemented` (the server has a local backend), `installed` (the binary is on this process's `PATH`), `install_steps`, and `default`:

```text
GET /v1/agents/runtimes?order=asc  200
codex        implemented: true   installed: false  default: true
qwen-code    implemented: true   installed: false  default: false
claude-code  implemented: false  installed: false  default: false
command      implemented: false  installed: true   default: false
cursor       implemented: false  installed: false  default: false
```

A runtime that is not implemented is refused whatever `installed` says. Four routes exist only to refuse with the same typed `404` (`agents_cannot_*`: `POST /v1/responses/input_tokens`, `DELETE /v1/models/{id}`, executor registration and channel). Their body also points to `GET /v1/agents/runtimes`.

One Codex turn:

```text
POST /v1/agents/sessions  {"agent":{"model":"codex"}}  200
object: agent.session
X-Agent-Sandbox-Local: 1

POST /v1/agents/sessions/{id}/events  202
body: {}

GET /v1/agents/sessions/{id}/items  200
content[0].text: hello-from-fake-codex
```

One Qwen Code turn (`qwen` and `qwencode` are aliases):

```text
POST /v1/agents/sessions  {"agent":{"model":"qwen-code"}}  200
POST /v1/agents/sessions/{id}/events  202
GET /v1/agents/sessions/{id}/items  200
content[0].text: hello-from-fake-qwen
```

Against a server you already started:

```bash
export ABX_SERVER_ENABLED_GROUPS=agents
python -m agent_sandbox.server serve --port 9000

python examples/agents/hosted_codex.py http://127.0.0.1:9000
python examples/agents/hosted_qwen.py http://127.0.0.1:9000
```

That process must already see the binary you name. If it does not, the turn reports that the runtime is not installed. The base image does not carry it in advance.
