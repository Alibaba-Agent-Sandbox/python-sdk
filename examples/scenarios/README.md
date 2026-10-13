# Scenario: create, exec, read, kill

This is the local form of an agent loop. A real `Sandbox.create` needs a provider and an API key. The steps below use the same server the template runs (`easy-sandbox-server`) and the Python `ServerClient`. Nothing is called in-process.

```bash
python3 examples/scenarios/agent_loop_local.py
```

Recorded on 2026-10-12 from that command (exit 0). The port is chosen at runtime.

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

The same three checks are also in `e2e/test_client_sdk_local_e2e.py`. On 2026-10-12:

```text
e2e/test_client_sdk_local_e2e.py::test_health PASSED
e2e/test_client_sdk_local_e2e.py::test_write_and_read_file_under_base_dir PASSED
e2e/test_client_sdk_local_e2e.py::test_shell_stdout PASSED
3 passed in 0.37s
```

## Modal-style examples

`examples/compat-demos/modal_compute.py` and `modal_data_analysis.py` call `@sandbox` against a cloud sandbox (`code-interpreter-v1`). They were not run in this environment: that path needs a live sandbox API. The decorator's local path is covered by `client-sdk/tests/integration/test_declarative_register_e2e.py` and `test_workflow_e2e.py`, which start a real server process.

## What to set

One name per key. See the CLI guide [Credentials and configuration keys](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/docs/en/guide/providers.md#credentials-and-configuration-keys). The sandbox key is `EBX_SANDBOX_API_KEY`. Alibaba Cloud access keys stay `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.
