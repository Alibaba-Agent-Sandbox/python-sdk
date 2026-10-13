# Agents API

沙箱里的 HTTP 会话。70 条路由全部已实现。有本地后端的运行时有两个：**Codex** 和 **Qwen Code**。`claude-code`、`cursor` 和 `command` 是已声明、没有本地后端的适配器，`GET /v1/agents/runtimes` 会如实标出。基础镜像不预装这两个 CLI。要用哪一个，再安装哪一个。

这是在沙箱里运行 Agent 的唯一方式：`/v1/agents/sessions` 下的路由。SDK 没有 `sb.agent.*` 辅助方法。

每个字段怎么拒绝，见 [托管代理](hosted-agents.md)。路由表在 [Agents API 参考](../reference/agents-api.md)。本页是能照着做完的说明。

## 安装 CLI

默认只装一个。两个都装进基础镜像会把镜像做大。没在请求里点名时，服务端用产品顺序里的第一个：`codex`。要用 Qwen Code，在请求里写出来，或用 `ABX_AGENTS_DEFAULT=qwen-code` 把默认换成它。

```bash
npm install -g @openai/codex          # 二进制名 codex
npm install -g @qwen-code/qwen-code   # 二进制名 qwen
```

Codex 在真正调用模型时读 `OPENAI_API_KEY` 或 `CODEX_API_KEY`。Qwen Code 读 `OPENAI_API_KEY`。密钥在创建沙箱时注入，不写进镜像，也不放进下面这个案例。

模板 [agents-cli](https://github.com/alibaba-agent-sandbox/awesome-templates/tree/main/agents-cli) 用细粒度策略，不把 `file_ops` 或 `process` 整组打开。怎么写策略、有哪些端点 id，见 [细粒度能力](fine-grained-capabilities.md)。`endpoints` 里 `*` 设为 `enabled: false`，再逐个打开 `agents_sessions_create`、`agents_sessions_events_create`、`agents_sessions_items_list`、`agents_runtimes_list`。因此 `POST /shell` 和 `POST /v1/agents`（定义）保持 404。Dockerfile 里留了按需安装 CLI 的那一行。

## 完整案例

案例脚本自己拉起本地服务，在 `PATH` 上放名为 `codex` 和 `qwen` 的本地程序，用来演示请求和响应，不读取模型密钥。安装上面的真实 CLI 之后，同一组请求会调用对应二进制。

```bash
python examples/agents/complete_case.py
```

下面是响应形状。会话 id 由服务端生成。

未给出适配器名时，用顺序里的第一个（`codex`）。模型 id `gpt-5` 传给这个 CLI，不用来换适配器：

```text
POST /v1/agents/sessions  {"agent":{"model":"gpt-5"}}  200
agent.id: codex
agent.model: gpt-5
X-Agent-Sandbox-Local: 1
```

`GET /v1/agents/runtimes` 和其他列表一样，默认 `order=desc`。加上 `order=asc` 才是产品顺序：`codex`、`qwen-code`，然后是只声明的适配器。`default: true` 标出没点名时会用的那一个，不看它在数组里的位置。没有配置时标在 `codex` 上。`ABX_AGENTS_DEFAULT=qwen-code` 之后改到 `qwen-code`。

要点名另一个：

```text
POST /v1/agents/sessions  {"adapter":"qwen-code","agent":{"model":"gpt-5"}}  200
agent.id: qwen-code
agent.model: gpt-5
```

已声明但没有本地后端的适配器，例如 `claude-code`：

```text
POST /v1/agents/sessions  adapter=claude-code  404
X-Agent-Sandbox-Local: 1
type: not_found_error
code: agents.not_implemented_locally
param: adapter
message: adapter 'claude-code' is declared but has no local backend; GET /v1/agents/runtimes reports which runtimes are implemented (codex, qwen-code) and installed
```

`GET /v1/agents/runtimes` 列出每个已声明的运行时。每一项有 `implemented`（服务端有本地后端）、`installed`（这个进程的 `PATH` 上有该二进制）、`install_steps` 和 `default`：

```text
GET /v1/agents/runtimes?order=asc  200
codex        implemented: true   installed: false  default: true
qwen-code    implemented: true   installed: false  default: false
claude-code  implemented: false  installed: false  default: false
command      implemented: false  installed: true   default: false
cursor       implemented: false  installed: false  default: false
```

未实现的运行时，不管 `installed` 是什么都会被拒绝。有四条路由专门用同样的类型化 `404` 拒绝（`agents_cannot_*`：`POST /v1/responses/input_tokens`、`DELETE /v1/models/{id}`、执行器注册和通道）。它们的响应体同样指向 `GET /v1/agents/runtimes`。

Codex 一轮：

```text
POST /v1/agents/sessions  {"agent":{"model":"codex"}}  200
object: agent.session
X-Agent-Sandbox-Local: 1

POST /v1/agents/sessions/{id}/events  202
body: {}

GET /v1/agents/sessions/{id}/items  200
content[0].text: hello-from-fake-codex
```

Qwen Code 一轮（`qwen`、`qwencode` 是别名）：

```text
POST /v1/agents/sessions  {"agent":{"model":"qwen-code"}}  200
POST /v1/agents/sessions/{id}/events  202
GET /v1/agents/sessions/{id}/items  200
content[0].text: hello-from-fake-qwen
```

对着已经开着的服务，而不是这个脚本自己起的服务：

```bash
export ABX_SERVER_ENABLED_GROUPS=agents
python -m agent_sandbox.server serve --port 9000

python examples/agents/hosted_codex.py http://127.0.0.1:9000
python examples/agents/hosted_qwen.py http://127.0.0.1:9000
```

那个进程的 `PATH` 上要有你要调用的二进制。没有的话，回合会告诉你运行时没安装，而不是在镜像里事先放好。
