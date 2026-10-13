# Hosted agents (Codex and Qwen Code)

The sandbox server speaks a local Agents API. Codex and Qwen Code are supported today.

The examples `hosted_codex.py` and `hosted_qwen.py` do not start a server and do not embed an API key. They are HTTP clients. Pass the server origin as the first argument, or set `ABX_TEMPLATE_URL`.

## Enable the group

The `agents` capability group is off until you opt in. On the server process:

```bash
export ABX_SERVER_ENABLED_GROUPS=agents
# optional, when the server was started with a token
export ABX_SERVER_TOKEN=your-token
python -m agent_sandbox.server
```

Point `base_url` at that process. The template server listens on **port 9000** (`http://127.0.0.1:9000`). Official OpenAI clients use `base_url=http://127.0.0.1:9000/v1` and `Authorization: Bearer`. These examples accept either `http://127.0.0.1:9000` or a URL that already ends in `/v1`.

## Adapters

| Adapter | Body selector | Real binary | Install only when you use it |
|---|---|---|---|
| Codex | `codex` (alias `openai-codex`) | `codex` | `npm install -g @openai/codex` |
| Qwen Code | `qwen-code`, `qwen`, `qwencode` (alias `qwen_code`) | `qwen` | `npm install -g @qwen-code/qwen-code` |

Any other adapter name (`claude-code`, `cursor`, `command`, …) is HTTP 404 `not_found_error` with `x-should-retry: false`. If the body does not name one of these two and `agents.default` is unset, the server uses the first in the product order: `codex`. Set `adapter` to `qwen-code` to use the other one. `GET /v1/agents/runtimes` marks the current default with `default: true`.

`agents.default` is `ABX_AGENTS_DEFAULT` or, in the JSON file `ABX_AGENTS_CONFIG`, a top-level `default` or `agents.default` string.

```bash
python hosted_codex.py http://127.0.0.1:9000
python hosted_qwen.py http://127.0.0.1:9000
```

A model API key is not required to *call* these routes. The CLI on the server needs its own credentials only when you run a real binary (`OPENAI_API_KEY` / `CODEX_API_KEY` for Codex, `OPENAI_API_KEY` for Qwen Code).

## Local programs

Tests and `local_files_and_session.py` do not install Codex or Qwen. They put a shell script named `codex` (or `qwen`) on `PATH`. The script discards stdin and prints one JSON object per line. No model API key is written into the script or the environment.

```sh
#!/bin/sh
cat >/dev/null
printf '%s\n' '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"hello-from-fake-codex"}}'
printf '%s\n' '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}'
exit 0
```

`local_files_and_session.py` writes that script, starts a local server with `ABX_SERVER_ENABLED_GROUPS=agents`, uploads one file with `POST /upload`, reads it back with `GET /download`, and opens one Codex session. With no arguments it does not need a server you started yourself, and it does not read an API key. A base URL you pass is a server that is already running on this machine; the upload then uses `/home/user/abx-note.txt` (the default `ABX_SERVER_BASE_DIR`), and that process must already have a local program named `codex` on `PATH`.

```bash
python local_files_and_session.py
python local_files_and_session.py http://127.0.0.1:9000
```

## 中文

目前支持 **Codex** 和 **Qwen Code**。先让服务端打开 `agents` 组（`ABX_SERVER_ENABLED_GROUPS=agents`），把客户端的 base URL 指到 **9000** 端口。二进制是 `codex`（npm `@openai/codex`）和 `qwen`（npm `@qwen-code/qwen-code`），要用哪一个再安装哪一个。`hosted_codex.py` 和 `hosted_qwen.py` 自己不启动服务，也不带模型 API key。

本地程序是放在 `PATH` 上、名为 `codex`（或 `qwen`）的 shell 脚本：丢弃 stdin，每行打印一个 JSON。脚本和环境里都不写模型 API key。`local_files_and_session.py` 会写好这个脚本，启动本地服务，用 `POST /upload` 和 `GET /download` 传一个文件，并开一个 Codex 会话。不带参数时它自己起服务，也不读取 API key。传入基址时，上传路径是 `/home/user/abx-note.txt`（默认的 `ABX_SERVER_BASE_DIR`），并且那个进程的 `PATH` 上已经有名为 `codex` 的本地程序。
