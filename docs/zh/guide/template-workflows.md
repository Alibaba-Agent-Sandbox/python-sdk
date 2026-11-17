# 启动和使用模板

源码模板使用 `abx --provider PROVIDER deploy SOURCE --name my-app --yes` 准备资源。普通 Sandbox 应用使用随模板提供的 `run.py` 创建和启动，再用返回的 Sandbox ID 与相同 Provider 连接。平台已经提供模板 ID 时，可以直接用 Python 创建实例。

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

## 创建并启动自有实例

源码模板的 `abx deploy` 准备可复用的 Sandbox 资源，并部署其中声明的 Serving 资源。
普通 Sandbox 模板应按自己的 README，把返回的模板 ID 交给随模板提供的 `run.py`。
运行脚本负责创建实例、启动应用并保存私有会话文件。凭据、模型配置、端口和清理操作
以该模板文档为准。只创建实例，不会自动完成要求显式启动的应用流程。

应用自行管理实例时，通过 `ProviderSandbox.create` 传入已准备模板 ID 和运行参数，
使用 `start_server` 启动文档声明的进程，再解析应用客户端。只删除自己创建的实例。
连接已有实例后关闭连接只释放本地资源，不代表取得该实例的删除归属。

## 资源配置

当前[资源格式](../reference/template-yaml-spec.md)采用命名 Sandbox 和 Serving。
原生表达式、构建和部署由 CLI 处理。Python 使用已准备 ID 和显式运行配置创建实例，
不会解析当前命名资源的 `template.yaml`。

现有高级 `launch_template` API 仍接受其较早的已准备快照格式，不接受当前命名资源源码文件。
它的 `TemplateSession` 服务及端口助手属于该独立接口；不要把当前模板的 `template.yaml`
直接交给它。当前资源格式应使用模板随附脚本或显式实例 API。
实例 TTL、环境变量、元数据与挂载覆盖值属于实例创建或应用运行策略。

部署托管 Agents API 后，业务客户端使用其 Gateway HTTP 入口；动态 Sandbox 创建及清理
由模板的 Worker 负责。参阅[托管 API 指南](managed-agents-api.md)。

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

已有卷属于借用资源，实例清理不会删除这些卷本体。

在 `code-interpreter-v1` 上运行 shell 命令，并不代表调用了解释器 API。极速版、E2B 和 REST 的项目适配器尚未接入统一解释器操作，需要时使用已记录的平台原生 SDK；CubeSandbox 和容器版接入了持久默认上下文操作。

模板作者和维护者可在[共享契约](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts)中查阅操作及验证记录格式。历史测试只说明记录中的输入和调用路径通过，不能推导所有平台、所有客户端入口都已测过。

Provider 作者仅在 CLI 适配器实现源码 `template.prepare` 时，才能声明 `workflow.source_placeholders = ["<region>", "<tag>"]`。这个可选字段描述官方基础镜像的替换能力；Python 只校验它，不因此获得源码构建能力，其他占位符名称会被拒绝。
