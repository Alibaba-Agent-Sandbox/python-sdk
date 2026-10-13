# 最佳实践

如何运行沙箱内的服务器。路由形状见[模板服务器 HTTP API](template-server-api.md)。路径和命令限制见[文件与命令控制](file-and-command-controls.md)。

## 服务器不携带提供者

`easy_sandbox.server` 不选择沙箱提供者，也不读取 `--provider`。模板的 `commands.py` 只导入 `easy_sandbox.server`，并在 `if __name__ == "__main__"` 下调用 `serve(port=9000)`。

Dockerfile 的 `FROM`、能否写 `CMD` 或 `ENTRYPOINT`，以及平台的 `start_cmd`，都在 CLI 提供者配置里（`ebx-provider.toml` 的 `[template]`，或内置的 `alicloud-express` 常量）。HTTP 路由不随镜像改变。客户端 SDK 也不选择这份配置。

## 只打开需要的能力组

服务器有九个能力组。`core` 保持开启（`GET /health`、`GET /capabilities`）。默认开启的是 `commands`、`file_ops`、`process`、`terminal`、`system`。默认关闭的是 `dev_tools`、`browser`、`agents`。

为一个进程关掉默认组：

```bash
export EBX_SERVER_DISABLED_GROUPS=terminal,dev_tools
```

也可以在模板策略的 `server.groups` 里写（例如 `process: false`）。列表里的 `core` 会被忽略。规则不能把已关闭的组重新打开；在 `SandboxServer` 启动时生效的 `EBX_SERVER_ENABLED_GROUPS`，以及 `serve()` 之前的 `default_table().enable_group(...)`，才是打开可选组的方式。

`shell`、`code_run` 和 PTY 可以运行一个能读取进程可见的任意路径的程序。对同时拥有这些端点的身份，路径规则守不住。只搬文件的模板从 `transfer-only` 或 `read-only` 预设开始。见[文件与命令控制](file-and-command-controls.md)。

## 在会话需要之前保持 `agents` 关闭

Agents 路由保持关闭，直到进程以 `EBX_SERVER_ENABLED_GROUPS=agents` 启动（或在 `serve()` 之前 `enable_group(CapabilityGroup.AGENTS)`）。组关闭时，这些路径返回 404，正文说明路由已禁用。

目前支持 Codex 和 Qwen Code。检查清单、本地响应头和 404 见[托管代理 — 最佳实践](hosted-agents.md#最佳实践)。

## 默认一个 agent

镜像里只安装要调用的那一个 CLI。Codex 和 Qwen Code 都装进去会把镜像做大。

服务端的顺序是 `codex`，然后 `qwen-code`。请求没有点名适配器时，用第一个。`GET /v1/agents/runtimes?order=asc` 按这个顺序返回。列表默认的 `order` 是 `desc`。`default: true` 标出当前默认，不看数组下标。

```bash
npm install -g @openai/codex
```

要用 Qwen Code，在请求里写 `adapter`、`runtime` 或请求头 `X-EBX-Adapter`，或把 `model` 写成 `qwen-code`（别名 `qwen`、`qwencode`）。`gpt-5` 这种模型 id 会传给被选中的 CLI，不会用来换适配器。

把默认从第一个换成另一个：

```bash
export EBX_AGENTS_DEFAULT=qwen-code
```

`EBX_AGENTS_CONFIG` 指向的 JSON 里，顶层 `default` 或 `agents.default` 作用相同。`claude-code`、Cursor、Qoder 仍然是 404。

## 按接口打开 Agents 路由

`groups.agents: true` 只是这组路由的门。和 `upload`、`shell` 一样，每个 Agents 路由有自己的端点 id，默认 scope 是 `agents:use`。只打开创建会话：

```python
from easy_sandbox.server import SandboxServer, ServerPolicy, default_table

policy = ServerPolicy.only("agents_sessions_create").with_options(groups={"agents": True})
server = SandboxServer(route_table=default_table(), policy=policy)
```

同一份策略写成 YAML：

```yaml
groups:
  agents: true
endpoints:
  "*":
    enabled: false
  agents_sessions_create:
    enabled: true
```

这些端点不接受 `paths` 和专用 `params`。写上会在加载策略时失败。完整端点 id 见[细粒度能力](fine-grained-capabilities.md)。

## 密钥不会被回显

`GET /env` 会略过名称里含有 `TOKEN`、`SECRET`、`KEY`、`PASSWORD` 或 `CREDENTIAL` 的变量。加载了策略时，还会略过 `EBX_SERVER_TOKEN`、`EBX_SERVER_POLICY`、`EBX_SERVER_POLICY_FILE`、每一个 `token_env` 名称，以及每一个以 `EBX_SERVER_` 开头的名称。

`POST /env` 返回它更新了的名称（`{"updated": [...]}`），不返回值。它拒绝 `PATH`、`HOME`、`USER`、`SHELL`、`EBX_SERVER_TOKEN`，以及每一个 `EBX_*` 名称。策略可以用 `env_get` 和 `env_set` 上的 `params.allow_vars` / `params.deny_vars` 再拒绝一批名称。

在带身份的策略下启动的子进程，继承的环境里已经去掉这些密钥名。在 shell 的 `env` 对象里传入其中之一会得到 `env_var_not_allowed`。

在 Agents 路由上，MCP 请求头的值返回 `"***"`。vault 凭据的值、前缀、长度和哈希不会出现在响应、错误或事件里。
