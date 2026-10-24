# OpenSandbox 提供方

OpenSandbox 是由 [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox) 维护的目录 Node Provider。Python `ProviderSandbox` 通过本机 CLI 引擎使用该适配器；引擎传输地址不是应用的 HTTP 地址。平台、适配器、模板和调用客户端是不同层。

## 当前适配器（2026-10-23）

适配器清单声明操作契约 1、分别面向 CLI/Python 的精确操作，以及支持的工作流输入和启动方式。粗粒度特性元数据只用于管理和发现，不授予解释器能力，也不认证模板。安装的代码必须与清单一致。请查阅[插件当前清单](https://github.com/alibaba-agent-sandbox/awesome-providers/blob/main/opensandbox/abx-provider.toml)和[工作流指南](../guide/template-workflows.md)，不要复制历史特性表。

插件使用自己的 OpenSandbox 地址和 API Key；极速版 API Key 不是 OpenSandbox 凭据。安装、配置和 Docker 验收命令由插件中英文 README 维护。目录引擎和 WebSocket 实现要求 Node 22。

## 模板与解释器的关系

模板可以提供 Python、Jupyter 或 HTTP 应用，但这些内容不会实现项目 SDK 的协议桥接。当前项目适配器尚未实现统一解释器操作。`code.execute` 或上下文操作被拒绝，表示当前适配器/客户端路径不能调用，不代表 OpenSandbox 原生 API 没有这项能力。解释器镜像名本身也不会授予操作。

应用 HTTP 独立判断。源码应用使用自己声明的构建配置、启动方式、端口/协议及操作；预构建镜像工作流使用不可变镜像摘要；服务工作流使用显式应用 URL。每条路径都对照所选消费入口的精确操作规划。缺少解释器支持不会阻断无关的应用工作流。

Shell 执行仍是显式的 `exec.run`/`exec.stream` 路径。解释器端点缺失时不会自动改写成临时 Python 脚本或 Shell 命令。历史极速版解释器转 Shell 路径已从当前项目适配器删除；固定标准客户端保持独立契约。

## 应用端点绑定

适配器返回实际沙箱端口端点，包含 Provider ID、沙箱 ID、端口、网关认证受众、路径模式、请求头及可选有效期。Python 使用 `await sandbox.application_client(port, token=application_token)` 获取。网关凭据与应用令牌是不同身份。代理路径前缀和不透明签名查询值保留；重定向、命名空间穿越、歧义域名/查询覆盖在发送负载前被拒绝。

`engine://opensandbox/<id>` 是内部传输标识，不会通过猜测主机或路由改写成 HTTP 应用地址。按操作签名的端点需要显式操作解析器，不能直接按前缀拼接。

## 验证范围

静态 T/F/U 计划、Provider 成熟度、访问者环境与实际部署证据分别记录。T 只允许进入本地检查；账号、网络和运行应用仍需执行时检查。历史 OpenSandbox 原生 Stable 结果不证明新的 CLI/Python 工作流。作者提交的 PASS JSON 不是项目认证。

Provider 仓库负责 Docker T4，覆盖插件生命周期/文件、安装后 SDK 集成和可移植应用工作流。验收记录必须绑定精确源码、清单、Provider、消费端、工作流、端点等身份，以及必要检查和清理结果。只有独立审批的 CI 来源能使目录回执获得认证。见[模板工作流](../guide/template-workflows.md)。

## 历史调研

早期 exec 插件调研保留在[归档](../../en/archive/provider-opensandbox-research.md)。历史特性表、镜像名推断及 Shell 替代都不是当前契约。当前实现和验收证据由各自仓库维护。
