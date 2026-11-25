# Agents API

HTTP sessions inside the sandbox. All 70 routes are implemented. Two runtimes have a local backend: Codex and Qwen Code. `claude-code`, `cursor` and `command` are declared adapters without a local backend, and `GET /v1/agents/runtimes` says so. The SDK installs adapters, not the upstream CLI binaries. Prepare the selected CLI in the sandbox image before deployment.

This is the one way to run an agent in a sandbox: the routes under `/v1/agents/sessions`. The SDK has no `sb.agent.*` helpers.

Field-by-field refusals are in [Hosted agents](hosted-agents.md). The route table is in the [Agents API reference](../reference/agents-api.md). This page is the path you can finish.

## Prepare a CLI in the image

Install the CLI your application needs at a pinned version in its Dockerfile. The bundled `agents-cli` template prepares both Codex and Qwen Code; a custom image can include just one. When the request does not name an adapter, the server uses the first in the product order: `codex`. Name Qwen Code in the request, or set `ABX_AGENTS_DEFAULT=qwen-code`, to use the other one.

For a Node.js-enabled image, choose the matching build step (these versions are the
current `agents-cli` template pins, not a claim about every model or account):

```dockerfile
RUN npm install -g @openai/codex@0.162.1 && codex --version
# Or: RUN npm install -g @qwen-code/qwen-code@0.23.0 && qwen --version
```

After selecting the final server user, verify that the same binary is on that user's
`PATH`. Build and deploy the updated template before creating sandboxes. Requests do
not download or install a missing CLI. There is no
`python -m agent_sandbox.server.agents install` command.

Codex reads `OPENAI_API_KEY` or `CODEX_API_KEY` when it actually calls a model. Qwen Code reads `OPENAI_API_KEY`. Inject the key when the sandbox is created. Do not bake it into the image, and do not put it in the case below.

The [agents-cli](https://github.com/alibaba-agent-sandbox/awesome-templates/tree/main/agents-cli) template does not turn on `file_ops` or `process`. `endpoints` sets `*` to `enabled: false`, then turns on `agents_sessions_create`, `agents_sessions_events_create`, `agents_sessions_items_list`, and `agents_runtimes_list` one by one. `POST /shell` and `POST /v1/agents` (definitions) stay 404. Its Dockerfile installs pinned CLI versions during image preparation.

## Complete case

The case starts a local server and places programs named `codex` and `qwen` on `PATH` so the requests and responses can be shown without a model key. The script remains a local fixture; use the same API shapes with your deployed, prepared runtime for real model requests.

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

That process must already see the binary you name. If it does not, the turn reports that the runtime is not installed. Prepare it in the image before deployment; the request does not install it.
