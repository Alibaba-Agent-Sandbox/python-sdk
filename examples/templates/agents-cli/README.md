# agents-cli

> **Fixture**: this directory is an offline example in the SDK repository, not the
> publishing source. Publishable templates live in
> [Easy-Sandbox/awesome-templates](https://github.com/Easy-Sandbox/awesome-templates).

Codex 和 Qwen Code 的 Agents API 模板。镜像里**不预装**这两个 CLI。要用哪一个，再安装哪一个。

English follows the Chinese section.

## 这是什么

沙箱里的 `easy-sandbox-server` 提供一组默认关闭的 Agents API（`/v1/agents/sessions` 等）。这个模板只做三件事：

1. 打开 `agents` 组作为门，再用 `ServerPolicy.only(...)` 只放出会话创建、读取、列表、事件、条目和 runtimes。`file_ops`、`process`、`POST /shell`、`POST /v1/agents`（定义）保持关闭。
2. 按请求里的名字选择 CLI：`codex`，或 `qwen-code`（别名 `qwen`、`qwencode`）。
3. 在 `PATH` 上找到对应二进制，跑一轮，再把输出写成会话条目。

这和下面两样不是同一件事：

| | 做什么 |
|---|---|
| **本模板 / Agents API** | HTTP 会话。服务端拉起你安装的 `codex` 或 `qwen`。 |
| **内置 Agent 高级 API**（`sb.agent.code()`） | 设计文档里的 `commands.run()` 语法糖，不是这组 HTTP。 |
| **`codex-agent-api` 模板** | 自己写的一套路由，并且在镜像里安装 Codex。新的案例用本模板。 |

Claude Code、Cursor、Qoder 以及其他名字返回 HTTP 404 `not_found_error`，响应头 `x-should-retry: false`。

## 按需安装 CLI

基础镜像只有 Python 和 `easy-sandbox-server`。两个 CLI 都装上会把镜像做大，所以默认都不装。

只在你的 Dockerfile 里加上你要用的那一行：

```dockerfile
# Codex
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && npm install -g @openai/codex && rm -rf /var/lib/apt/lists/*

# 或者 Qwen Code
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && npm install -g @qwen-code/qwen-code && rm -rf /var/lib/apt/lists/*
```

也可以在已经跑起来的沙箱里安装，装完再开会话。Codex 读 `OPENAI_API_KEY` 或 `CODEX_API_KEY`。Qwen Code 读 `OPENAI_API_KEY`（以及它自己的 `OPENAI_BASE_URL`）。密钥在创建沙箱时注入，不写进镜像。

## 调用

服务监听 **9000**。客户端示例在 Python SDK 仓库的 `examples/agents/`：

```bash
export EBX_SERVER_ENABLED_GROUPS=agents
python -m easy_sandbox.server serve --port 9000

python examples/agents/hosted_codex.py http://127.0.0.1:9000
python examples/agents/hosted_qwen.py http://127.0.0.1:9000
```

```python
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:9000/v1/agents/sessions",
    data=b'{"agent":{"model":"codex"}}',
    headers={"Content-Type": "application/json"},
    method="POST",
)
print(urllib.request.urlopen(req).read().decode())
```

每个响应都带 `X-Easy-Sandbox-Local: 1`。计算发生在这台沙箱里，不在 OpenAI 托管环境里。

## 本地测试

不安装真实 CLI，也不需要模型密钥。`e2e-bin/` 里的脚本只在 `E2E_RUN_LLM=0` 时进入 `PATH`。

```bash
E2E_RUN_LLM=0 EBX_SERVER_PORT=9000 python3 commands.py
E2E_BASE_URL=http://127.0.0.1:9000 python3 e2e_test.py
```

测试会检查：健康检查、未指定适配器时 400、`claude-code` 为 404、名为 `codex` 与 `qwen` 的本地程序各完成一轮并带回文本。

## English

This template turns on the sandbox Agents API for **Codex** and **Qwen Code**. The image does not install either CLI. Add the `npm install -g` line for the one you call, or install it inside a running sandbox. Other adapter names, including Claude Code, Cursor, and Qoder, are HTTP 404.

The server listens on port **9000**. Point `examples/agents/hosted_codex.py` or `hosted_qwen.py` at it. When `E2E_RUN_LLM=0`, `e2e_test.py` puts the local programs in `e2e-bin/` on `PATH`. Those programs are named `codex` and `qwen`.
