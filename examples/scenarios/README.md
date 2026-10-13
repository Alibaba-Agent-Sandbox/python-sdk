# Scenario: create, exec, read, kill

This is the local form of an agent loop. A real `Sandbox.create` needs a provider and an API key. The steps below use the same server the template runs (`easy-sandbox-server`) and the Python `ServerClient`. Nothing is called in-process.

```bash
python3 examples/scenarios/agent_loop_local.py
```

Example output. The port is chosen at runtime.

```text
step 1  create
  server  http://127.0.0.1:33989
  health  True
step 2  exec
  exit    0
  stdout  '4\n'
  stderr  ''
step 3  read result
  wrote   /tmp/ebx-agent-loop/base/result.txt (9 bytes)
  read    'answer=4\n'
step 4  kill
  signal  SIGTERM
  return  -15
```

`return -15` is the process group receiving SIGTERM (signal 15).

The same checks are in `e2e/test_client_sdk_local_e2e.py`.

## Modal-style examples

`examples/compat-demos/modal_compute.py` and `modal_data_analysis.py` call `@sandbox` against a cloud sandbox (`code-interpreter-v1`). They need `EBX_SANDBOX_API_KEY`. The decorator's local path is covered by `client-sdk/tests/integration/test_declarative_register_e2e.py` and `test_workflow_e2e.py`, which start a real server process.

## What to set

One name per key. See the CLI guide [Credentials and configuration keys](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/providers.md#credentials-and-configuration-keys). The sandbox key is `EBX_SANDBOX_API_KEY`. Alibaba Cloud access keys stay `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.
