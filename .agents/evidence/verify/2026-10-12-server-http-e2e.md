# Verification: local server HTTP end-to-end (2026-10-12)

Subprocess `python -m agent_sandbox.server serve` on 127.0.0.1 (ephemeral port). Checks are a separate HTTP client, plus a raw socket for the websocket upgrade. Handlers were not called in-process. `PYTHONPATH=server-sdk/src`, `ABX_SERVER_ENABLED_GROUPS=agents`, fake `codex` and `qwen` on `PATH`. No server source edits.

## Command

```bash
cd python-sdk/e2e
PYTHONPATH=../server-sdk/src python3 -m pytest test_server_http_e2e.py --noconftest -ra -v
```

Interpreter: Python 3.12.3, pytest 9.1.1. `--noconftest` avoids the cloud suite skip that fires when `E2B_API_KEY` is unset.

## Counts

18 passed, 0 failed, 0 skipped (0.46s).

`GET /v1/responses` with `Upgrade: websocket` returned 101 and completed a `response.create` frame (not the 400 skip). Multipart `POST /v1/files` returned 200 (not rejected).
