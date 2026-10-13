# Agents API

HTTP sessions inside the sandbox. Codex and Qwen Code are supported today. The base image does not install either CLI. Install the one you are about to call.

This is not the [built-in agent design](../design/built-in-agents.md). That page is `sb.agent.*`, sugar over `commands.run()`. The Agents API is a different set of routes: `/v1/agents/sessions`.

Field-by-field refusals are in [Hosted agents](hosted-agents.md). This page is the path you can finish.

## Install a CLI

Install one CLI. Installing both into the base image makes the image large. When the request does not name an adapter, the server uses the first in the product order: `codex`. Name Qwen Code in the request, or set `EBX_AGENTS_DEFAULT=qwen-code`, to use the other one.

```bash
npm install -g @openai/codex          # binary name: codex
npm install -g @qwen-code/qwen-code   # binary name: qwen
```

Codex reads `OPENAI_API_KEY` or `CODEX_API_KEY` when it actually calls a model. Qwen Code reads `OPENAI_API_KEY`. Inject the key when the sandbox is created. Do not bake it into the image, and do not put it in the case below.

The [agents-cli](https://github.com/Easy-Sandbox/awesome-templates/tree/main/agents-cli) template does not turn on `file_ops` or `process`. `groups.agents: true` is only the gate. `endpoints` sets `*` to `enabled: false`, then turns on `agents_sessions_create`, `agents_sessions_events_create`, `agents_sessions_items_list`, and `agents_runtimes_list` one by one. `POST /shell` and `POST /v1/agents` (definitions) stay 404. The Dockerfile leaves the one `npm install` line for the CLI you call.

## Not the built-in agent API

| | Agents API | Built-in agent design |
|---|---|---|
| Entry | `POST /v1/agents/sessions` | The `sb.agent.code()` sketch |
| What runs | `codex` or `qwen` on `PATH` | A CLI the sketch assumed was already in the template, wrapped as `commands.run()` |
| CLIs in the base image | No | The sketch mentioned preinstall. The product does not put both CLIs in the base image |
| Other names | `claude-code`, Cursor, and Qoder are 404 | Not these HTTP routes |

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
X-Easy-Sandbox-Local: 1
```

`GET /v1/agents/runtimes` uses the same paging as the other lists, so the default `order` is `desc`. Pass `order=asc` to see the product order `codex`, then `qwen-code`. `default: true` marks the runtime used when the request does not name one. The flag does not follow the array index. With no config it is on `codex`. After `EBX_AGENTS_DEFAULT=qwen-code` it moves to `qwen-code`.

Name the other one:

```text
POST /v1/agents/sessions  {"adapter":"qwen-code","agent":{"model":"gpt-5"}}  200
agent.id: qwen-code
agent.model: gpt-5
```

An adapter name that is not supported today, for example `claude-code`:

```text
POST /v1/agents/sessions  adapter=claude-code  404
X-Easy-Sandbox-Local: 1
type: not_found_error
code: agents.not_implemented_locally
message: adapter 'claude-code' is not available in this slice (codex, qwen-code)
```

`GET /v1/agents/runtimes` currently returns `codex` and `qwen-code`, each with `install_steps` (`npm install -g ...`). `installed` is whether that binary is on this process's `PATH`.

One Codex turn:

```text
POST /v1/agents/sessions  {"agent":{"model":"codex"}}  200
object: agent.session
X-Easy-Sandbox-Local: 1

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
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server serve --port 9000

python examples/agents/hosted_codex.py http://127.0.0.1:9000
python examples/agents/hosted_qwen.py http://127.0.0.1:9000
```

That process must already see the binary you name. If it does not, the turn reports that the runtime is not installed. The base image does not carry it in advance.
