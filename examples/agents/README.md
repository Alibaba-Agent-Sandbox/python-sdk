# Hosted agents (Codex and Qwen Code)

This slice of the sandbox server speaks a subset of the OpenAI Agents API for two CLIs only: **Codex** and **Qwen Code**. Vaults, the Responses API, and other adapters are not part of this slice.

The examples `hosted_codex.py` and `hosted_qwen.py` do not start a server and do not embed an API key. They are HTTP clients. Pass the server origin as the first argument, or set `EBX_TEMPLATE_URL`.

## Enable the group

The `agents` capability group is off until you opt in. On the server process:

```bash
export EBX_SERVER_ENABLED_GROUPS=agents
# optional, when the server was started with a token
export EBX_SERVER_TOKEN=your-token
python -m easy_sandbox.server
```

Point `base_url` at that process. The template server listens on **port 9000** (`http://127.0.0.1:9000`). Official OpenAI clients use `base_url=http://127.0.0.1:9000/v1` and `Authorization: Bearer`. These examples accept either `http://127.0.0.1:9000` or a URL that already ends in `/v1`.

## Adapters

| Adapter | Body selector | Real binary | Install only when you use it |
|---|---|---|---|
| Codex | `codex` (alias `openai-codex`) | `codex` | `npm install -g @openai/codex` |
| Qwen Code | `qwen-code`, `qwen`, `qwencode` (alias `qwen_code`) | `qwen` | `npm install -g @qwen-code/qwen-code` |

Any other adapter name (`claude-code`, `cursor`, `command`, …) is HTTP 404 `not_found_error` with `x-should-retry: false`. If the body does not name one of these two and `agents.default` is unset, the server returns 400 `agents.adapter_required`.

`agents.default` is `EBX_AGENTS_DEFAULT` or, in the JSON file `EBX_AGENTS_CONFIG`, a top-level `default` or `agents.default` string.

```bash
python hosted_codex.py http://127.0.0.1:9000
python hosted_qwen.py http://127.0.0.1:9000
```

A model API key is not required to *call* these routes. The CLI on the server needs its own credentials only when you run a real binary (`OPENAI_API_KEY` / `CODEX_API_KEY` for Codex, `OPENAI_API_KEY` for Qwen Code).

## Fake CLI

Tests and `local_files_and_session.py` do not install Codex or Qwen. They put a shell script named `codex` (or `qwen`) on `PATH`. The script discards stdin, prints one JSON object per line, and exits 0. No model API key is written into the script or the environment.

```sh
#!/bin/sh
cat >/dev/null
printf '%s\n' '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"hello-from-fake-codex"}}'
printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}'
exit 0
```

`local_files_and_session.py` writes that script, starts a local server with `EBX_SERVER_ENABLED_GROUPS=agents`, uploads one file with `POST /upload`, reads it back with `GET /download`, and opens one Codex session. With no arguments it does not need a server you started yourself, and it does not read an API key. A base URL you pass is a server that is already running on this machine; the upload then uses `/home/user/ebx-note.txt` (the default `EBX_SERVER_BASE_DIR`), and that process must already have the fake `codex` on `PATH`.

```bash
python local_files_and_session.py
python local_files_and_session.py http://127.0.0.1:9000
```

## 中文

这一切片只托管 **Codex** 和 **Qwen Code**。先让服务端打开 `agents` 组（`EBX_SERVER_ENABLED_GROUPS=agents`），把客户端的 base URL 指到 **9000** 端口。真实二进制是 `codex`（npm `@openai/codex`）和 `qwen`（npm `@qwen-code/qwen-code`），只有真正要用时才安装。`hosted_codex.py` 和 `hosted_qwen.py` 自己不启动服务，也不带模型 API key。

假 CLI 是放在 `PATH` 上、名为 `codex`（或 `qwen`）的 shell 脚本：丢弃 stdin，每行打印一个 JSON，然后以 0 退出。脚本和环境里都不写模型 API key。`local_files_and_session.py` 会写好这个脚本，启动本地服务，用 `POST /upload` 和 `GET /download` 传一个文件，并开一个 Codex 会话。不带参数时它自己起服务，也不读取 API key。传入基址时，上传路径是 `/home/user/ebx-note.txt`（默认的 `EBX_SERVER_BASE_DIR`），并且那个进程的 `PATH` 上已经有假 `codex`。
