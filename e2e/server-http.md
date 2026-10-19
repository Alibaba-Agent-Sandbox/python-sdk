# Local server HTTP end-to-end tests

`test_server_http_e2e.py` starts a real `python -m agent_sandbox.server serve` subprocess on
`127.0.0.1` and an ephemeral port, then sends HTTP from a separate client. A raw socket is used
only for `GET /v1/responses` with `Upgrade: websocket`. Handlers are not called in-process.

No cloud credentials, API keys, or the published `codex` / `qwen` binaries. The process
puts local programs named `codex` and `qwen` on `PATH` (each prints one JSON line) and
sets `ABX_SERVER_ENABLED_GROUPS=agents`.
`PYTHONPATH` is `server-sdk/src`. Traffic stays on localhost.

## Run

From `python-sdk/e2e` (the cloud `conftest.py` skips every test in this directory when
`E2B_API_KEY` is unset, so this file is run with `--noconftest`):

```bash
cd e2e
PYTHONPATH=../server-sdk/src python3 -m pytest test_server_http_e2e.py --noconftest -ra
```

The subprocess is `sys.executable -m agent_sandbox.server serve` (the same interpreter that runs pytest).

## Skipped cases

- `GET /v1/responses` with a WebSocket upgrade that still returns **400** is skipped, and the skip
  text includes that status.
- `POST /v1/files` as `multipart/form-data` is skipped when the server does not return 200, and the
  skip text includes the status the server actually sent.

A product failure on any other case stays a failed assertion. The server sources are not edited to
make a case pass.
