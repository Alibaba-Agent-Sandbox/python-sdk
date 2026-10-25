# SDK 入口对照

根据代码实际使用的 API 选择入口。下列入口共用本项目的配置
`ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL`、`ABX_SANDBOX_DOMAIN`，
各自保留其方法签名和结果模型。

| 入口 | 用途 | 前提 |
|---|---|---|
| `from agent_sandbox import Sandbox` | 标准同步生命周期、命令和文件 API | 阿里云支持的固定标准契约；极速版账号 |
| `from agent_sandbox import AsyncSandbox` | 在异步代码中使用同样的标准操作 | 对异步方法使用 await |
| `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` | 标准解释器结果和上下文 | 使用 `code-interpreter-v1` 等包含解释器的模板 |
| `from agent_sandbox import ProviderSandbox` | 显式提供方扩展、会话和应用客户端 | 所选提供方实现了请求的操作 |
| `from agent_sandbox.declarative import sandbox` | 将 Python 函数放到远程执行 | 模板包含所需 Python 环境及依赖 |
| `from agent_sandbox.server import command, start` | 在镜像内注册并提供应用命令 | 镜像内安装同版本服务端运行时 |

安装[已发布的 Python 包](install-python.md)。Python 包不包含独立的
[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)。

## 标准解释器

```python
from agent_sandbox.code_interpreter import Sandbox

with Sandbox.create(template="code-interpreter-v1") as sandbox:
    result = sandbox.run_code("print(1 + 1)")
    assert result.error is None
    print(result.text)
```

迁移已有 E2B 应用请按[固定迁移契约](migrate-from-e2b.md)操作。替换导入不会消除
后端权限、账号限制或运行时前提。第三方库仍使用其原生配置。

## Provider 命令和文件操作

```python
from agent_sandbox import ProviderSandbox

async with await ProviderSandbox.create(template="base") as sandbox:
    result = await sandbox.commands.run("printf hello")
    assert result.exit_code == 0
    await sandbox.files.write("/home/user/note.txt", result.stdout)
    assert await sandbox.files.read("/home/user/note.txt") == "hello"
```

这里在极速版 `base` 上使用命令和文件操作，不是解释器 API，也不会启动应用服务。
极速版 ProviderSandbox 适配器未实现解释器操作，应通过上面的标准解释器入口调用。
其他提供方的操作声明、账号实际可用性和云端验证是不同的内容，见[提供方指南](providers.md)。

## 模板应用

使用 `abx template launch <reference>` 准备并启动完整模板。高级 `template build` /
`template deploy` 可单独准备镜像。启动后通过
`await sandbox.application_client(9000, token=application_token)` 绑定应用客户端，
再调用 `client.commands.run("hello", name="Python")`。前提是运行中的模板注册了 hello，
普通 `base` 不包含该服务。见 [Express 快速开始](express-quickstart.md)和
[模板启动](template-workflows.md)。

应用令牌与平台凭据分开使用。提供方负责网关解析，保留所需请求头及 URL 前缀。
借用的客户端只关闭连接；仅删除自己拥有的沙箱和构建资源。

## 验证范围

接口签名一致或提供方声明支持，并不等于已经通过真实云测试。
[云端示例](cloud-examples.md)提供可复现脚本及前提。每条验证记录只覆盖其实际账号、
模板、提供方及调用路径。本文不做跨平台启动耗时、GPU、最长寿命或价格对比；
这些取决于平台和账号条件，不能通过 API 对照得出。
