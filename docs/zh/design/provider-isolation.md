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
| 极速版 SDK、AK/SK 签名和换取凭据、FC/ACR 部署、CLI 参数和提示、AI 管理工具定义 | `providers/alicloud_express/` |
| 可复用的 E2B/envd 协议及 token 头格式 | `providers/shared/e2b/`，由 Provider 显式选用 |

发行包的组装入口注册内置适配器、配置描述、CLI 扩展和 AI 扩展。生成的配置目录属于
声明式兼容数据。历史 `api`、`protocol`、`transport` 路径保留导出兼容层，不保留第二份
实现或核心兜底。共享 HTTP/Connect 传输处理帧和连接复用；认证和协议由 Provider 选择，
传输层不选择云后端。

## SDK 契约

内置默认项和插件均通过 `Provider.build_infra(config)` 构建基础设施。
`session_protocols`、`prepare_session`、`resolve_session_url`、`open_terminal`
负责各自会话。极速版直接使用原生 HTTP/Connect/WebSocket 适配器；已退役的
Python gRPC 引擎及生命周期钩子保持删除。外部 Node 引擎/EPP 客户端仍是独立的
Provider 契约。

`TransportConfig(provider="external")` 和 `load_config` 均不补上未声明的域名或
region，显式端点保持有效。创建绑定失败回收本次新建资源；连接失败保留借用资源。
公开兼容导出保留历史 monkeypatch 的模块身份。缺失可选协议返回 E8004，不回退极速版。

CLI 模板工厂及 CLI/AI 发现归属 CLI 仓库，本次不新增 Python 镜像部署 API，详见
[CLI 边界契约](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/design/provider-isolation.md)。
内置 Provider 继续随匹配的 SDK 版本更新。适配器隔离不代表 SDK 零改动迁移，也不会
产生后端本身没有的能力。

调用方显式选择的 Provider 优先于环境默认项。内置配置纯数据归属
`utils/bundled_config.py`；传输层只消费 `_provider_schema.py` 契约及注入的
发现函数，不导入可执行的注册表。
