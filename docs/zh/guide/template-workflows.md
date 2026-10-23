# 显式模板工作流

模板规范 4 把模板提供的软件服务、Provider 适配器操作和具体客户端的调用能力分开。应用 HTTP 服务不依赖统一代码解释器。Provider 的 Beta 表示成熟度，不代表所有工作流都可用或不可用。

| 层次 | 声明或检查的内容 |
| --- | --- |
| 模板 | `provides`、显式 `workflows`、唯一 `default_workflow`、输入和启动方式 |
| Provider | 操作契约 1、各消费入口的精确操作、支持的输入和启动方式 |
| SDK/CLI | 所选操作的实际协议桥接、调用位置和网络绑定 |
| 验证 | 当前内容身份、最低检查集、清理结果和独立认可的 CI 来源 |

权威契约、验收范围、收据 schema 和共享用例位于 [`contracts`](https://github.com/alibaba-agent-sandbox/python-sdk/tree/main/contracts)。静态规划的 T 表示所需实现已接入，F 表示明确不匹配或项目适配器/客户端未接入，U 表示信息未确定。任意 F 优先于 U。T 只允许进入本地检查，不表示运行测试通过。“项目适配器未实现”不能推断为平台原生 API 不具备该能力。

当前运行时不翻译旧 schema。模板中的 `capabilities`、`tested_on` 和手填 Provider 兼容声明被拒绝。未知远端引用不再默认获得解释器能力。历史记录保留为历史。

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

使用已准备的镜像工作流创建独立沙箱：

```python
from agent_sandbox.api import launch_workflow

async with await launch_workflow(
    "template.yaml", provider="opensandbox", workflow_id="application-image",
    reference=immutable_image_reference, application_token=application_token,
) as session:
    result = await session.run_command("hello", name="Python")
```

模板必须实际声明所选工作流。Python 不准备源码项目；先使用 CLI 显式构建配置，再选择不可变的 `image` 工作流；`managed` 启动在 Provider 能解析不可变身份前明确拒绝。外部应用使用 `service` 工作流及显式应用 URL。这个独立启动器不执行 application 部署 hooks，也不重新解释应用部署拓扑。

启动器固化 manifest 输入，核对 Provider 实际代码摘要，在创建前持久化意图并记录自有资源 ID，在调用前检查应用协议版本，只删除自己创建的沙箱。创建结果不确定时不重试创建，保留 journal，可按 `abx_workflow_run` metadata 核对资源。清理失败会保留资源 ID 并抛错。journal 不写 API key、应用令牌、环境秘密或带签名的端点 URL，也不等于可信验证收据。

## 解释器操作

`ProviderSandbox.code.run(code)` 默认选择无状态的 `code.execute`。Provider 协议负责隔离，可使用原生无状态调用或临时上下文并保证清理。`mode="default-context"` 显式选择持久的默认上下文；`context_id=...` 选择 `code.context.execute`。创建、列举、重启、删除上下文分别要求精确操作。实时回调要求 `code.stream`，缓冲后回调不算实时流；结构化富结果另有操作声明。

缺少 runtime 或解释器返回 HTTP 404 时直接报错，不再自动写脚本转 shell。需要 shell 执行 Python 脚本时，显式调用 `files.write()` 和 `commands.run("python script.py")`。固定标准契约的 `Sandbox`、`AsyncSandbox`、`code_interpreter` 客户端保持独立。

## 验证范围

规范 profile 绑定消费入口及工作流类型；上下文 profile 还要求完整的精确上下文操作。模板可以增加 `required_checks`，不能删减最低检查项。必需项失败、跳过、缺失或输入变化都不能算已验证。源码、manifest、构建、产物、Provider、消费入口、工作流、绑定和契约身份均需匹配。作者填写 PASS 或 runner 不能自证通过；Registry 必须独立核对认可的 CI 来源和匹配产物。guest HTTP、host HTTP、原生 SDK、统一 Python/CLI 分别记录。

当前项目适配器：Express、E2B 和 REST 尚未接入统一解释器，猜测 RPC 实现已删除；CubeSandbox 和容器版仅接入持久的默认上下文操作。平台原生和固定标准客户端独立。托管工作流还需要 Provider 解析不可变引用，无法解析的原生 ID 会被拒绝；已准备镜像必须包含不可变 SHA256 摘要。
