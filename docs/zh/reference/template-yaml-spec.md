# template.yaml 资源与 Python 运行时

本地保留一个 `template.yaml`，使用 `specVersion: 1`。完整字段以匹配模板及 CLI 修订的
[模板规范](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/template-spec.zh-CN.md)
和 [schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v1.schema.json)
为准。上架元信息和初始化问题属于 `registry.yaml`；本地运行不依赖该文件。

| 字段 | 含义 |
| --- | --- |
| `specVersion` | 整数 `1` |
| `name` | 项目／应用名称 |
| `vars` | 可选的复用值，键名由作者自定 |
| `sandbox.<名称>.provider` | 该资源的 Provider |
| `sandbox.<名称>.template` | 模板属性，包含地域、镜像／引用／构建声明 |
| `sandbox.<名称>.template.buildConfig` | Dockerfile 配合可选 context，或原生 Steps |
| `sandbox.<名称>.volumes` | 所选 Provider 支持的命名静态卷 |
| `sandbox.<名称>.actions` | 资源生命周期动作 |
| `serving.<名称>.component` | 组件来源及固定版本 |
| `serving.<名称>.props` | 组件原生属性 |
| `serving.<名称>.actions` | 资源生命周期动作 |

CLI 负责原生 Devs 表达式、资源准备和部署。该文件不声明每个动态 Sandbox 实例，
也不声明通用应用进程。具体模板提供运行时代码；模板原生 `startCommand`、`readyCommand`
保留 Provider 准备语义，不替代应用在实例创建后携带认证的启动步骤。

## Python 使用方式

将部署返回的模板 ID 交给模板的 `run.py`，或使用 `ProviderSandbox.create` 并显式启动应用。
TTL、模型凭据、运行环境与动态挂载属于实例创建或应用运行策略。已有卷保持原归属，
删除实例不会删除借用卷本体。

SDK 现有 `launch_template`／`TemplateSession` 接受较早的已准备快照格式，其 YAML 解析器
和发现投影尚未迁移到当前命名资源源码。即使先解析 `${...}`，也不会让两种结构变得相同。
当前源码文件应使用上面的直接运行路径，不要交给旧快照接口。
参阅[启动与清理](../guide/template-workflows.md)。

<a id="capability-declarations"></a>
## 应用端点与服务端策略

端口放行不代表进程已经启动、Provider 操作已获授权，也不定义业务协议。
`await sandbox.application_endpoint(port)` 返回所选 Provider 的实际端点描述；
已运行的 SandboxServer 可使用 `application_client`。网关请求头与应用令牌分属不同认证层。

SandboxServer API 权限使用独立运行时策略，通过文档说明的策略文件或
`ABX_SERVER_POLICY_FILE`／`ABX_SERVER_POLICY` 加载。命名命令来自 `@command`
注册的真实 Python 函数，YAML 不生成函数。参阅[细粒度能力](../design/fine-grained-capabilities.md)。
