# 启动和使用模板

源码模板使用 `abx --provider PROVIDER template launch SOURCE --yes` 准备并启动，再用 Python 通过返回的沙箱 ID 和同一个 Provider 连接。平台已经提供模板 ID 时，可以直接用 Python 创建。

## Python 应用调用

连接已有沙箱后，单独解析应用 HTTP，不能根据内部 Provider 传输地址判断应用不可调用：

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.connect(sandbox_id, provider="opensandbox")
try:
    async with await sandbox.application_client(9000, token=application_token) as client:
        result = await client.commands.run("hello", name="Python")
finally:
    await sandbox.close()  # 只释放本次连接；它没有创建这个沙箱
```

`application_client` 向所选 Provider 请求当前沙箱端口的应用入口。网关请求头与显式应用令牌分别处理，不复制控制面 API key。请求保留代理前缀和签名 query 原始字节；拒绝重定向、URL 用户信息、主机覆盖和编码路径越界。按操作签名的入口必须由 Provider 解析具体请求，不能当作前缀 URL 拼接。

如果 `X-Access-Token` 请求头未被占用，客户端还会通过服务端已有的这个请求头发送同一个显式应用令牌，使认证能通过 OpenSandbox 1.1.1 等会过滤 `Authorization` 的代理。已有网关请求头（包括注入 HTTP 客户端的默认请求头）不会被覆盖；需要 Bearer 的服务仍可使用原认证方式。

高级准备场景中，`launch_template` 根据已准备好的 Provider 引用创建新沙箱，并执行清单的 `start_cmd`。该引用的原生启动命令或镜像入口不能同时启动同一个服务。普通 `abx template deploy` 可能保留原生启动行为，返回的引用不自动代表应用尚未启动。如果 CLI 已启动应用，按上文连接它返回的沙箱即可。

确认准备阶段没有重复启动后，让 Python 负责启动和清理：

```python
from agent_sandbox.api import launch_template

async with await launch_template(
    "template.yaml", provider="opensandbox",
    reference=prepared_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

不再选择工作流。Python 创建一个沙箱，执行一次 `start_cmd`，检查 `ready_cmd`，
并解析 `provides` 中所有服务。SandboxServer 协议 v2 服务执行 health/discovery 检查；
其他协议由模板的就绪命令检查，返回对应客户端但不猜测其协议路由。
`session.services` 包含全部服务客户端，`session.servers` 包含 SandboxServer 客户端。
只有一个 SandboxServer 时可以使用 `session.server` 和 `session.run_command`；
多个时使用 `session.servers["服务名"].commands.run(...)` 选择调用目标。
这不会改变已经整体启动的模板内容。

Python 不构建源码；源码准备由 CLI 负责，按上文选择一个启动方。
模板也可声明固定摘要的 `image`，或者 `provider` 与 `template_id` 原生模板标识。
引用由 Provider 解释，原生 ID 不需要虚构版本。已有外部 HTTP 服务直接使用
`ServerClient`；应用部署 hook 仍由部署编排器处理。

启动器冻结 manifest、记录创建意图和所拥有的资源 ID，仅删除自己创建的沙箱。
创建结果不确定时不自动重试，可使用 `abx_template_run` 元数据核对资源。
后续服务失败也会关闭之前解析的所有客户端。日志不记录令牌、环境变量值和签名 URL，
也不等于云端验证证据。同一个最终 `ABX_SERVER_TOKEN` 同时用于沙箱环境和客户端。

收到进程启动确认后，启动器会在一个 `readiness_timeout` 预算内重复执行尚未成功的 `ready_cmd`。每次探测受剩余预算约束，退出码为 0 时才完成就绪检查；预算耗尽会抛出 `readiness-command-failed` 并删除本次创建的沙箱，取消启动同样保留资源清理。进程已经启动与应用已经就绪是两个独立条件。

## 从规范 4 迁移

改为 `spec_version: 5`，删除 `workflow_contract_version`、`default_workflow`、
`workflows`，保留完整的 `provides`、实际 `start_cmd` 和 `ready_cmd`。
CLI 命令删除 `--workflow`；Python 改用 `launch_template`，不传 `workflow_id`。
旧清单明确报告迁移错误，不自动挑选以前的默认工作流。
历史规范 4 证据保留，但不能证明规范 5 的启动链路已验证。

## 解释器操作

`ProviderSandbox.code.run(code)` 默认选择无状态的 `code.execute`。Provider 协议负责隔离，可使用原生无状态调用或临时上下文并保证清理。`mode="default-context"` 显式选择持久的默认上下文；`context_id=...` 选择 `code.context.execute`。创建、列举、重启、删除上下文分别要求精确操作。实时回调要求 `code.stream`，缓冲后回调不算实时流；结构化富结果另有操作声明。

缺少 runtime 或解释器返回 HTTP 404 时直接报错，不再自动写脚本转 shell。需要 shell 执行 Python 脚本时，显式调用 `files.write()` 和 `commands.run("python script.py")`。固定标准契约的 `Sandbox`、`AsyncSandbox`、`code_interpreter` 客户端保持独立。

## 平台托管模板

使用极速版 `base` 等原生模板时，直接调用 SDK 即可：

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(template="base", provider="alicloud-express")
try:
    result = await sandbox.commands.run("python3 --version")
    print(result.stdout)
finally:
    await sandbox.kill()  # 本段代码创建并负责删除这个沙箱
```

规范 5 清单声明 `provider: alicloud-express`、`template_id: base` 和
`provides: {}` 后，可以调用 `launch_template(manifest, provider="alicloud-express")`，
通过异步上下文管理器自动删除自己创建的沙箱。不再声明或选择工作流。

在 `code-interpreter-v1` 上运行 shell 命令，并不代表调用了解释器 API。极速版、E2B 和 REST 的项目适配器尚未接入统一解释器操作，需要时使用已记录的平台原生 SDK；CubeSandbox 和容器版接入了持久默认上下文操作。

模板作者和维护者可在[共享契约](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts)中查阅操作及验证记录格式。历史测试只说明记录中的输入和调用路径通过，不能推导所有平台、所有客户端入口都已测过。

Provider 作者仅在 CLI 适配器实现源码 `template.prepare` 时，才能声明 `workflow.source_placeholders = ["<region>", "<tag>"]`。这个可选字段描述官方基础镜像的替换能力；Python 只校验它，不因此获得源码构建能力，其他占位符名称会被拒绝。
