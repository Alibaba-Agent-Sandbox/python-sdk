# 场景：创建、执行、读取、销毁

**Client SDK。** 这个脚本跑在你的机器上。它在本地拉起一个 Server SDK 进程，只是为了让客户端有服务可调。

这是智能体循环的本地形态。真正的 `Sandbox.create` 需要提供商和 API key。下面的步骤使用模板里同一个服务（`agent-sandbox-server`）和 Python `ServerClient`。没有在进程内直接调用路由。

```bash
python3 examples/scenarios/agent_loop_local.py
```

示例输出。端口在运行时选择。

```text
step 1  create
  server  http://127.0.0.1:33989
  health  True
step 2  exec
  exit    0
  stdout  '4\n'
  stderr  ''
step 3  read result
  wrote   /tmp/abx-agent-loop/base/result.txt (9 bytes)
  read    'answer=4\n'
step 4  kill
  signal  SIGTERM
  return  -15
```

`return -15` 表示进程组收到了 SIGTERM（信号 15）。

同一组检查在 `e2e/test_client_sdk_local_e2e.py`。

## Modal 风格示例

`examples/compat-demos/modal_compute.py` 和 `modal_data_analysis.py` 用 `@sandbox` 调云上沙箱（`code-interpreter-v1`）。它们需要 `ABX_SANDBOX_API_KEY`。装饰器的本地路径由 `client-sdk/tests/integration/test_declarative_register_e2e.py` 和 `test_workflow_e2e.py` 覆盖，它们会启动真实的服务进程。

## 要设置的变量

每个键只有一个名字。沙箱密钥是 `ABX_SANDBOX_API_KEY`。阿里云 AccessKey 仍是 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`。完整表在 CLI 文档「凭证与配置键」。
