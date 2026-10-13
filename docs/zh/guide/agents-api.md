# Agents API

沙箱里的 HTTP 会话。目前支持 **Codex** 和 **Qwen Code**。基础镜像不预装这两个 CLI。要用哪一个，再安装哪一个。

这不是 [内置 Agent 高级 API](../design/built-in-agents.md)。那一份是 `sb.agent.*` 的设计稿，本质是 `commands.run()` 的语法糖。Agents API 是另一组路由：`/v1/agents/sessions`。

路由参考（每个字段怎么拒绝）在 [托管代理](hosted-agents.md)。本页是能照着做完的说明。

## 安装 CLI

默认不装。两个都装进基础镜像会把镜像做大。

```bash
npm install -g @openai/codex          # 二进制名 codex
npm install -g @qwen-code/qwen-code   # 二进制名 qwen
```

Codex 在真正调用模型时读 `OPENAI_API_KEY` 或 `CODEX_API_KEY`。Qwen Code 读 `OPENAI_API_KEY`。密钥在创建沙箱时注入，不写进镜像，也不放进下面这个案例。

模板 [agents-cli](https://github.com/Easy-Sandbox/awesome-templates/tree/main/agents-cli) 用细粒度策略，不把 `file_ops` 或 `process` 整组打开。怎么写策略、有哪些端点 id，见 [细粒度能力](fine-grained-capabilities.md)。`groups.agents: true` 只是这组路由的门。`endpoints` 里 `*` 设为 `enabled: false`，再逐个打开 `agents_sessions_create`、`agents_sessions_events_create`、`agents_sessions_items_list`、`agents_runtimes_list`。因此 `POST /shell` 和 `POST /v1/agents`（定义）保持 404。Dockerfile 里留了按需安装 CLI 的那一行。

## 和内置 Agent 的差别

| | Agents API | 内置 Agent 高级 API |
|---|---|---|
| 入口 | `POST /v1/agents/sessions` | 设计稿里的 `sb.agent.code()` |
| 运行的东西 | `PATH` 上的 `codex` 或 `qwen` | 设想为模板里预装的 CLI，再包一层 `commands.run()` |
| 默认是否装上 CLI | 否 | 设计稿写过预装。当前产品不把两个 CLI 打进基础镜像 |
| 其他名字 | `claude-code`、Cursor、Qoder 是 404 | 不是这组 HTTP |

## 完整案例

案例脚本自己拉起本地服务，在 `PATH` 上放名为 `codex` 和 `qwen` 的本地程序，用来演示请求和响应，不读取模型密钥。安装上面的真实 CLI 之后，同一组请求会调用对应二进制。

```bash
python examples/agents/complete_case.py
```

下面是响应形状。会话 id 由服务端生成。

未给出适配器名，模型 id `gpt-5` 不会用来选 CLI：

```text
POST /v1/agents/sessions  400
X-Easy-Sandbox-Local: 1
code: agents.adapter_required
```

目前未支持的适配器名称，例如 `claude-code`：

```text
POST /v1/agents/sessions  adapter=claude-code  404
X-Easy-Sandbox-Local: 1
type: not_found_error
code: agents.not_implemented_locally
message: adapter 'claude-code' is not available in this slice (codex, qwen-code)
```

`GET /v1/agents/runtimes` 目前返回 `codex` 和 `qwen-code`，并带上 `install_steps`（`npm install -g ...`）。`installed` 表示这个进程的 `PATH` 上是否有该二进制。

Codex 一轮：

```text
POST /v1/agents/sessions  {"agent":{"model":"codex"}}  200
object: agent.session
X-Easy-Sandbox-Local: 1

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
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server serve --port 9000

python examples/agents/hosted_codex.py http://127.0.0.1:9000
python examples/agents/hosted_qwen.py http://127.0.0.1:9000
```

那个进程的 `PATH` 上要有你要调用的二进制。没有的话，回合会告诉你运行时没安装，而不是在镜像里事先放好。
