# Agents API

HTTP sessions inside the sandbox. This slice hosts **Codex** and **Qwen Code** only. The base image does not install either CLI. Install the one you are about to call.

This is not the [built-in agent design](../design/built-in-agents.md). That page is `sb.agent.*`, sugar over `commands.run()`. The Agents API is a different set of routes: `/v1/agents/sessions`.

Field-by-field refusals are in [Hosted agents](hosted-agents.md). This page is the path you can finish.

## Install a CLI

Neither CLI is installed by default. Installing both into the base image makes the image large.

```bash
npm install -g @openai/codex          # binary name: codex
npm install -g @qwen-code/qwen-code   # binary name: qwen
```

Codex reads `OPENAI_API_KEY` or `CODEX_API_KEY` when it actually calls a model. Qwen Code reads `OPENAI_API_KEY`. Inject the key when the sandbox is created. Do not bake it into the image, and do not put it in the case below.

The [agents-cli](https://github.com/Easy-Sandbox/awesome-templates/tree/main/agents-cli) template only turns the `agents` group on. Its Dockerfile leaves the one `npm install` line for you to add.

## Not the built-in agent API

| | Agents API | Built-in agent design |
|---|---|---|
| Entry | `POST /v1/agents/sessions` | The `sb.agent.code()` sketch |
| What runs | `codex` or `qwen` on `PATH` | A CLI the sketch assumed was already in the template, wrapped as `commands.run()` |
| CLIs in the base image | No | The sketch mentioned preinstall. The product does not put both CLIs in the base image |
| Other names | `claude-code`, Cursor, and Qoder are 404 | Not these HTTP routes |

## Complete case

The case starts a local server and puts two stand-in programs named `codex` and `qwen` on `PATH`. It does not read a model key. The stand-ins prove the HTTP session. After the `npm install` lines above, the same requests run the real CLIs.

```bash
python examples/agents/complete_case.py
```

Ran locally on 2026-10-13, exit code 0. The transcript below keeps the stable parts. Session ids change every run.

A model id such as `gpt-5` does not select a CLI:

```text
POST /v1/agents/sessions  400
X-Easy-Sandbox-Local: 1
code: agents.adapter_required
```

`claude-code` is outside this slice:

```text
POST /v1/agents/sessions  adapter=claude-code  404
X-Easy-Sandbox-Local: 1
type: not_found_error
code: agents.not_implemented_locally
message: adapter 'claude-code' is not available in this slice (codex, qwen-code)
```

`GET /v1/agents/runtimes` lists only `codex` and `qwen-code`, each with `install_steps` (`npm install -g ...`). `installed` is whether that binary is on this process's `PATH` right now.

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
