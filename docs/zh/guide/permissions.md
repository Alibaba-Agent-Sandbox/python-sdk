# 极速版功能与权限

共享 Provider 实现和完整的“功能 → RAM Action → 资源范围”策略表由 [CLI 权限指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/permissions.md)维护，包括 Key 准备/复用/续期、Team/模板/Volume/Quota/Template Cache、ACR、存储执行角色及管理员授权步骤。

已有 API Key 用户无需额外 AccessKey，显式 Key 始终优先。只有 AK/SK 时，SDK 只解析已经准备的 Key，不弹交互提示，不静默创建或续期。该可选路径需安装配套 `abx`（或设置 `ABX_BIN`）；直接用 API Key 的 SDK 调用不需要 CLI。

向调用身份授予 `sandbox:CreateApiKey`、`sandbox:DescribeApiKey`、`sandbox:UpdateApiKey`，限定在 `acs:sandbox:<region>:<account-id>:teams/<team-id>/apikeys/*`，然后显式确认准备：

```python
from agent_sandbox.providers.alicloud_express import prepare_api_key_sync
from agent_sandbox import Sandbox

prepare_api_key_sync(confirm=True)  # 创建/续期本机私有的 30 天管理 Key
sandbox = Sandbox.create(template="base")
try:
    print(sandbox.commands.run("echo ready").stdout)
finally:
    sandbox.kill()
```

异步使用 `await prepare_api_key(confirm=True)`，然后可用 `AsyncSandbox` 或 `ProviderSandbox`。默认 `confirm=False` 在引擎/云端 I/O 前拒绝。准备只返回元数据，不返回明文。复用时检查云端状态，临近到期需要重新显式准备；已构造客户端不会后台续期。禁用和删除不会被绕过。引擎负责有效期和共享私有存储，Python 不重复实现云 SDK。

可选 `team_id=` 必须与后续引擎选择一致。建议用 `abx config set team_id <TEAM_ID>` 持久化，使 CLI/SDK 使用同一上下文；省略时均使用接口默认 Team。CI 可先运行 `abx --ci sandbox list --format json` 明确授权准备，再启动 SDK 应用。未知写入结果的恢复步骤和精确清理权限见上述完整指南。
