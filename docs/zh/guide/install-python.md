# 安装 Python 配套包

> 规范 5 的模板启动需要本指南使用的配套 alpha 包：`agent-sandbox-client==0.4.0a6` 和 `agent-sandbox-server==0.4.0a6`。旧 0.3.x 包不实现此入口。验证源码修订时，请按下文从同一份检出同时安装两个发行包。

使用 Python 3.10 或更高版本及虚拟环境：

```bash
python -m venv .venv
# Linux 或 macOS：
source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a6'
python -m pip check
```

此命令安装 alpha 客户端，并自动安装同版本的必需依赖 `agent-sandbox-server`。导入名为 `agent_sandbox`；PyPI 上名为 `agent-sandbox` 的发行包是另一个无关项目。

检查安装的配套版本：

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) 需要独立安装。本指南中的 CLI 命令对应当前 CLI 源码；较早发行版请以已安装的帮助为准。创建沙箱前先配置所选平台。

本项目配置统一使用 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和
`ABX_SANDBOX_DOMAIN`，标准 Sandbox / AsyncSandbox 与 ProviderSandbox 均支持。
公开关键字参数仍遵循各入口的文档契约；标准入口的 `api_key=` 仍然有效。

## 可选依赖

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[all]==0.4.0a6'
```

可把 `[all]` 换成 `[mcp]`、`[session]` 或 `[fast]`。模板 YAML 和声明式装饰器属于基础客户端，无需 extra。浏览器自动化需要在沙箱镜像内安装 Playwright。

## 镜像内只安装服务端

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-server==0.4.0a6'
```

服务端负责在镜像内运行应用，安装它不会创建沙箱。注册命令与启动服务见[服务端指南](server-sdk.md)。

## 当前源码的客户端与运行时边界

当前检出已将本机服务端运行时改为可选依赖。标准 `Sandbox` / `AsyncSandbox`、
`ProviderSandbox`、`ServerClient`、模板 YAML 与远程执行装饰器 `@sandbox(...)`
只需客户端：

```bash
python -m pip install ./client-sdk
```

本机使用 `@sandbox.register` 或 `sandbox.server` 时，安装匹配的运行时：

```bash
python -m pip install ./server-sdk './client-sdk[server]'
```

`[all]` 和 `[dev]` 包含 `[server]`。上文固定的公开发行版早于这项依赖调整；
源码安装不代表已有新发行版。注册代码应放在应用服务程序中，不会上传本机函数。
模块级 `sandbox.run` / `sandbox.run_async` 已删除，请通过明确选定的应用的
`ServerClient.commands.run` 调用命名命令。`ProviderSandbox.run` 与远程执行装饰器仍保留。

## 从检出源码进行开发

在仓库根目录同时安装两个本地发行包：

```bash
git rev-parse HEAD
python -m pip install -e ./server-sdk -e './client-sdk[dev]'
python -m pip check
```

复现源码安装时记录提交，两个包都使用同一份检出。复现特定发行版本时，先检出对应 tag。贡献者验证与发布要求见 [CONTRIBUTING](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md)。
