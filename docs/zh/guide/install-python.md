# 安装 Python 配套包

下列命令选择配套的 **0.5.0a0 预览版**。可用版本以
[发布记录](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases)为准。
验证检出源码时，按下文的源码安装方式操作。需要 Python 3.10 或更高版本，
建议使用虚拟环境：

```bash
python -m venv .venv
# Linux 或 macOS：
source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.5.0a0'
python -m pip check
```

基础客户端支持标准 `Sandbox` / `AsyncSandbox`、`ProviderSandbox`、`ServerClient`、
模板 YAML 和远程装饰器 `@sandbox(...)`，不安装本机服务端运行时。
导入名为 `agent_sandbox`；PyPI 上名为 `agent-sandbox` 的发行包属于另一个项目。

检查已安装的客户端版本：

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'))"
```

[abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) 需要独立安装。
不同发行版的 CLI 命令可能不同；先检查已安装版本的帮助，并配置所选 Provider。

本项目配置统一使用 `ABX_SANDBOX_API_KEY`、`ABX_SANDBOX_BASE_URL` 和
`ABX_SANDBOX_DOMAIN`，标准 Sandbox / AsyncSandbox 与 ProviderSandbox 均支持。
公开关键字参数仍遵循各入口的文档契约；标准入口的 `api_key=` 仍然有效。

## 本机命令注册与服务启动

本机使用 `@sandbox.register` 或 `sandbox.server` 时，安装配套运行时：

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[server]==0.5.0a0'
python -m pip check
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
```

`[server]` 将 `agent-sandbox-server` 固定为与客户端相同的版本。
注册代码属于应用服务程序，不会把本机函数上传到已有沙箱。

## 可选依赖

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client[all]==0.5.0a0'
```

`[all]` 和 `[dev]` 包含配套的 `[server]` 运行时。可用 `[mcp]`、`[session]` 或
`[fast]` 选择对应子集。模板 YAML 与远程装饰器无需 extra。
浏览器自动化需要在沙箱镜像内安装 Playwright。

## 镜像内只安装服务端

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-server==0.5.0a0'
```

服务端负责在镜像内运行应用，安装它不会创建沙箱。宿主机安装不会更新已有沙箱镜像；
使用新服务端版本需要重新构建镜像。命令注册与启动见[服务端指南](server-sdk.md)，
缓冲式 base64 上传与下载策略限制见[文件传输说明](template-server-api.md#file_ops)。

## 从 0.4 预览版调整

0.5 基础客户端不再自动安装 `agent-sandbox-server`。本机代码需要注册命令或启动
运行时时，加装 `[server]`；访问远程服务仍可只安装基础客户端。

模块级 `sandbox.run` 和 `sandbox.run_async` 已删除。先部署应用并连接，再通过
`ServerClient.commands.run` 调用命名命令；见[模板应用启动与连接](template-workflows.md)。
`ProviderSandbox.run` 与远程装饰器 `@sandbox(...)` 继续保留。

## 从检出源码进行开发

在仓库根目录同时安装两个本地发行包：

```bash
git rev-parse HEAD
python -m pip install -e ./server-sdk -e './client-sdk[dev]'
python -m pip check
```

只开发客户端时，使用 `python -m pip install ./client-sdk`。
需要本机注册且无需开发工具时，使用
`python -m pip install ./server-sdk './client-sdk[server]'`。
复现源码安装时记录提交，两个包都使用同一份检出。复现发行版时，先检出对应 tag。
贡献者校验与发布要求见
[CONTRIBUTING](https://github.com/Alibaba-Agent-Sandbox/python-sdk/blob/main/.github/CONTRIBUTING.md)。
