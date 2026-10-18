# Provider 实现边界

所有生命周期操作均选择一个 `Provider`，内置极速版也走同一条路径，不再用 null
绕过 Provider。核心 API 依赖结构化协议和认证契约，不实例化云 SDK、不交换云凭据、
不推导后端地址，也不替后端选择协议。

## 职责归属

| 职责 | 归属 |
| --- | --- |
| Provider 选择、授权同意、完整性校验、输出、通用配置优先级、客户端资源关闭 | 宿主 |
| 认证、端点、协议映射、后端错误和状态、生命周期、可选创建参数 | 所选 Provider |
| 模板认证、构建、注册、轮询、删除以及 Docker/镜像仓库细节 | Provider 模板实现 |
| 模板源码搜索下载、项目生成、运行时验证 | 宿主，通过所选 Provider 的元数据和工厂调用 |
| 极速版 SDK、管理面签名、显式自定义凭据交换、FC/ACR 部署、CLI 参数和提示、AI 管理工具定义 | `providers/alicloud_express/` |
| 可复用的 E2B/envd 协议及 token 头格式 | `providers/shared/e2b/`，由 Provider 显式选用 |

发行包的组装入口注册内置适配器、配置描述、CLI 扩展和 AI 扩展。生成的配置目录属于
声明式兼容数据。历史 `api`、`protocol`、`transport` 路径保留导出兼容层，不保留第二份
实现或核心兜底。共享 HTTP/Connect 传输处理帧和连接复用；认证和协议由 Provider 选择，
传输层不选择云后端。

## SDK 契约

内置默认后端和插件均通过 `Provider.build_infra(config)` 构建基础设施。
`session_protocols`、`prepare_session`、`resolve_session_url` 和 `open_terminal`
组装 Provider 自己的会话。极速版创建和连接都使用原生 HTTP 控制面及数据面，不再安装、
选择或恢复本地 gRPC daemon。目录插件继续使用独立的 Node Provider 引擎。
普通沙箱调用需要显式沙箱 API Key；AK/SK 用于管理面。兼容的自定义凭据交换回调
必须显式设置，不会自动创建 API Key。

`TransportConfig(provider="external")` 和 `load_config` 均不补上未声明的域名或
region，显式端点保持有效。创建绑定失败回收本次新建资源；连接失败保留借用资源。
公开兼容导出保留历史 monkeypatch 的模块身份。缺失可选协议返回 E8004，不回退极速版。

CLI 模板工厂及 CLI/AI 发现归属 CLI 仓库，本次不新增 Python 镜像部署 API，详见
[CLI 边界契约](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/design/provider-isolation.md)。
内置 Provider 继续随匹配的 SDK 版本更新。适配器隔离不代表 SDK 零改动迁移，也不会
产生后端本身没有的能力。

显式 Provider 选择优先于无关的环境默认值。HTTP 回归在旧 daemon 不可用时检查空和非空
Volume 参数。会话 URL 由所选协议适配器构建；历史 TransportConfig URL 方法只委托
组合入口注入的构建器，不用于选择其他后端。

配置 Schema 解析由包的组合入口注入。读取内置 Schema 只加载纯元数据，不发现注册表；
Provider 包的公共导出保持延迟加载。兼容名称、常量和生成的配置声明保留为公共数据，
每项后端行为只在适配器中保留一份运行时实现。

## 端口与文件 URL 的归属

同步端口访问和项目服务的网关鉴权头由所选适配器实现。只有异步端口发现能力的
Provider 应调用 `await sandbox.network.resolve(port)`；同步辅助方法返回 E8004，
不会猜测极速版或 E2B 地址，也不会发送其他后端的令牌。独立构造网络模块时仍保留
已文档化的内置兼容行为。文件传输 URL 是文件系统适配器的可选钩子；即便会话地址
使用 HTTP，缺少钩子也返回 E8004。核心不会为其他 Provider 构造 `/files` 路由。

Python 中立传输和协议模块的导入不会加载内置认证或具体协议；显式请求历史兼容
导入时再延迟解析。
