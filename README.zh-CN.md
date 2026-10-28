# Agent Sandbox Python SDK

**中文** | [English](README.md)

[![CI](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/ci.yml)

在 Python 中创建沙箱、执行代码和命令，以及操作远程文件。本仓库包含客户端 SDK 和在沙箱应用镜像内运行的服务端运行时。

[官网](https://www.agent-sandbox.cn) · [使用文档](docs/zh/README.md) · [示例](examples/README.zh-CN.md)

## 安装

需要 Python 3.10+，建议使用虚拟环境：

```bash
python -m pip install --index-url https://pypi.org/simple --upgrade --pre agent-sandbox-client
python -m pip check
```

`--pre` 表示选择预览版本。导入名为 `agent_sandbox`，安装时自动带上同版本的 `agent-sandbox-server` 依赖。固定版本、可选依赖和源码安装见[安装指南](docs/zh/guide/install-python.md)。PyPI 上的 `agent-sandbox` 属于另一个项目。

## 快速开始

通过 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和 `ABX_SANDBOX_DOMAIN` 配置极速版的 Sandbox API Key、API 地址和沙箱域名。三者应属于同一账号与地域；来源和配置方法见[认证指南](docs/zh/guide/authentication.md)与[权限指南](docs/zh/guide/permissions.md)。

```python
from agent_sandbox.code_interpreter import Sandbox

sandbox = Sandbox.create(template="code-interpreter-v1")
try:
    sandbox.files.write("/tmp/input.txt", "hello")
    print(sandbox.commands.run("cat /tmp/input.txt").stdout)
    print(sandbox.run_code("1 + 1").text)
finally:
    sandbox.kill()
```

示例需要支持解释器的模板。工作结束或发生异常时，`kill()` 都会删除沙箱。

## 选择客户端

| 入口 | 用途 |
| --- | --- |
| `from agent_sandbox import Sandbox, AsyncSandbox` | 同步或异步使用极速版的沙箱生命周期、命令和文件操作 |
| `from agent_sandbox.code_interpreter import Sandbox, AsyncSandbox` | 在持久解释器上下文中执行代码 |
| `from agent_sandbox import ProviderSandbox` | 异步使用提供方插件和模板应用服务 |

`AsyncSandbox` 和 `ProviderSandbox` 使用 `await`。提供方操作和解释器是否可用取决于所选后端与模板，详见 [SDK 用法](docs/zh/guide/sdk-usage.md)。

## 其他提供方与应用模板

极速版为内置后端。[提供方插件](https://github.com/Alibaba-Agent-Sandbox/awesome-providers)可让 `ProviderSandbox` 连接其他后端，使用前按[提供方指南](docs/zh/guide/providers.md)完成安装与配置。

应用模板封装浏览器工具、编码 Agent 等服务。先用 [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)启动模板，再根据返回的沙箱 ID 和[模板启动指南](docs/zh/guide/template-workflows.md)从 Python 连接。调用命名应用命令前，需要先启动对应服务。

## 沙箱内运行时

| 包 | 运行位置 | 指南 |
| --- | --- | --- |
| [`agent-sandbox-client`](client-sdk/) | 用户的应用中 | [客户端 SDK](docs/zh/guide/client-sdk.md) |
| [`agent-sandbox-server`](server-sdk/) | 沙箱镜像内 | [服务端 SDK](docs/zh/guide/server-sdk.md) |

服务端通过 HTTP 暴露已注册的应用命令。模板作者在镜像内安装服务端并定义启动方式。客户端与服务端使用同一版本；命令注册与认证见[服务端 API 指南](docs/zh/guide/template-server-api.md)。

## 文档

| 任务 | 指南 |
| --- | --- |
| 完成第一次 API 调用 | [快速开始](docs/zh/guide/getting-started.md) |
| 查询方法与数据模型 | [API 参考](docs/zh/reference/api-reference.md) |
| 配置凭据与端点 | [认证](docs/zh/guide/authentication.md) |
| 配置文件与进程行为 | [文件与命令控制](docs/zh/guide/file-and-command-controls.md) |
| 迁移已有 E2B 代码 | [迁移指南](docs/zh/guide/migrate-from-e2b.md) |
| 处理错误 | [故障排查](docs/zh/guide/troubleshooting.md) |

更多内容见[完整文档索引](docs/README.md)、[示例](examples/README.zh-CN.md)和[更新日志](CHANGELOG.md)。

## 相关工具：abx CLI

[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox)提供终端操作、模板构建与启动功能，需要时单独安装。

## 参与贡献

开发环境和两个包的检查要求见[贡献指南](.github/CONTRIBUTING.md)。SDK 与运行时问题请提交到[本仓库 Issues](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues)。

## 许可证

[Apache-2.0](LICENSE)，署名信息见 [NOTICE](NOTICE)。
