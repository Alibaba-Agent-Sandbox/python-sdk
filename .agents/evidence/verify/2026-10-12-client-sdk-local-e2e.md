# Verification: client SDK local HTTP end-to-end (2026-10-12)

Subprocess `python -m easy_sandbox.server serve` on 127.0.0.1 (ephemeral port, `--base-dir` under the test temp dir). The source `ServerClient` (`easy_sandbox.api.server_client`) performed health, file upload, file read, and shell. Handlers were not called in-process. No API key and no `EBX_SERVER_TOKEN`. No server source edits.

## Command

```bash
cd python-sdk/e2e
PYTHONPATH=../server-sdk/src:../client-sdk/src python -m pytest test_client_sdk_local_e2e.py --noconftest -ra -v
```

Interpreter: Python 3.12.3, pytest 9.1.1 (`/tmp/ebxvenv`, which provides `httpx`). `--noconftest` avoids the cloud suite skip that fires when `E2B_API_KEY` is unset.

## Counts

3 passed, 0 failed, 0 skipped (0.84s).

`GET /health` via `ServerClient.health_sync` returned ok. `files.upload` / `files.read_text` round-tripped `client-sdk-local-e2e` under the server base dir. `process.shell` `echo client-sdk-local-e2e` stdout was `client-sdk-local-e2e\n` with exit code 0.
