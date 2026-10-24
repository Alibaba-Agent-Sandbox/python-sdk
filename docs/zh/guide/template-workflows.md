# 启动和使用模板

源码模板先用 CLI 准备并启动，再用 Python 连接。平台已经提供模板 ID 时，可以直接用 Python 创建。

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

使用已准备的镜像工作流创建独立沙箱：

```python
from agent_sandbox.api import launch_workflow

async with await launch_workflow(
    "template.yaml", provider="opensandbox", workflow_id="application-image",
    reference=immutable_image_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

模板必须声明所选工作流。Python 不构建源码项目；先用 CLI 准备，再连接返回的沙箱 ID，或用构建产物的 SHA256 镜像引用启动 `image` 工作流。`managed` 工作流直接接受所声明平台的原生模板 ID，不要求平台提供版本号。外部应用使用 `service` 工作流及显式应用 URL。这个独立启动器不执行 application 部署 hooks，也不重新解释应用部署拓扑。

启动器固化 manifest 输入，核对 Provider 实际代码摘要，在创建前持久化意图并记录自有资源 ID，在调用前检查应用协议版本，只删除自己创建的沙箱。创建结果不确定时不重试创建，保留 journal，可按 `abx_workflow_run` metadata 核对资源。清理失败会保留资源 ID 并抛错。journal 不写 API key、应用令牌、环境秘密或带签名的端点 URL，也不等于可信验证收据。

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

已有声明 `input: managed` 的 manifest 时，也可以调用 `launch_workflow(manifest, provider="alicloud-express", reference="base")`；它的异步上下文管理器会删除自己创建的沙箱。启动前仍检查所属平台、所需操作及启动方式。原生 ID 没有内容摘要也可以使用，journal 会如实记录产物摘要未知，不承诺内容不可变。

在 `code-interpreter-v1` 上运行 shell 命令，并不代表调用了解释器 API。极速版、E2B 和 REST 的项目适配器尚未接入统一解释器操作，需要时使用已记录的平台原生 SDK；CubeSandbox 和容器版接入了持久默认上下文操作。

模板作者和维护者可在[共享契约](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts)中查阅操作及验证记录格式。历史测试只说明记录中的输入和调用路径通过，不能推导所有平台、所有客户端入口都已测过。

Provider 作者仅在 CLI 适配器实现源码 `template.prepare` 时，才能声明 `workflow.source_placeholders = ["<region>", "<tag>"]`。这个可选字段描述官方基础镜像的替换能力；Python 只校验它，不因此获得源码构建能力，其他占位符名称会被拒绝。
