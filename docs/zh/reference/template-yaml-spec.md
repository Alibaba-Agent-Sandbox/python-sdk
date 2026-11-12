# template.yaml 规范

使用 `specVersion: 1`，本地资源配置只需一个 `template.yaml`。完整字段类型和各 Provider 的参数子集见 [template v1 schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v1.schema.json) 与[模板规范](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/template-spec.md)。上架元信息和初始化问题属于可选的 `registry.yaml`；本地运行无需该文件，也无需 `parameters`。

| 字段 | 含义 |
| --- | --- |
| `specVersion` | 整数 `1` |
| `name` | 资源名称 |
| `sandbox.provider` | Provider ID；可由 Python 显式选择的 Provider 补全 |
| `sandbox.template` | `source`、`image`、`reference` 三选一；可带构建 `props` 和 `aliases` |
| `sandbox.instance` | 实例 TTL、环境变量、元数据及 Provider 支持的实例参数 |
| `sandbox.start`、`sandbox.ready` | 整体启动和就绪检查命令 |
| `sandbox.ports` | 可选的附加端口号，不推测协议或自动启动服务 |
| `sandbox.services` | 端点映射：协议、整数版本、端口及可选 operations |
| `deployment` | 原生 Serverless Devs 项目，直接使用组件名和原生 props |
| `application` | 显式选择应用协调器，目前为 `type: agents-api` |

`sandbox.template.props` 是准备模板时的参数，不是实例覆盖值。引用已有模板时不能声明准备参数。Python 按选定 schema 和 Provider 消费 instance 的 CPU、内存、磁盘、GPU、已有卷名称挂载、环境变量、元数据和 TTL。启动器只接受固定的 `lifecycle: {onTimeout: kill, autoResume: false}`；暂停/自动恢复协调尚未承接，会在创建前拒绝。独立 `ProviderSandbox` 生命周期 API 保持其自身契约。

普通实例 TTL 默认 300 秒，托管 Agents API 默认为 3600 秒。Python 显式 `timeout`、`cpu`、`memory`、`disk`、`gpu`、`volume_mounts` 替换对应实例值；显式 `envs` 和 `metadata` 按名称合并，启动器自己的归属标签保留。内存/磁盘单位与可用性由 Provider 决定；Express 高层 schema 使用整数 MB，不代表所有云账号都能创建这些规格。

原生 `${...}` 表达式必须由真实 Devs 解析器执行。Python 已准备模板启动器接受字面量或已解析的 v1 快照，明确拒绝未解析表达式。环境变量值按字面量使用，空字符串不会隐式读取宿主环境。调用方应自行解析秘密来源，通过 `envs` 或已解析快照传入。Python 不构建源码镜像，也不因某个组件字段存在就承诺云端支持。缺少真实 v1 校验器的自定义 Provider 会被模板启动器拒绝，独立 Provider API 仍可使用。

<a id="capability-declarations"></a>
## 服务与服务端策略

`sandbox.services` 声明端点，不会启用服务端 API 或授予 Provider 操作。启动器一次启动整个模板，检查 SandboxServer 协议 v2 的健康和发现接口；其他协议使用 `sandbox.ready`，不会推测其路由。

根 `server` 不是 v1 资源字段。SandboxServer 端点策略仍通过其运行时策略文件或 `ABX_SERVER_POLICY_FILE` / `ABX_SERVER_POLICY` 加载。独立的 `validate_server_block` 结构校验器保留，实际服务端负责校验策略值。参阅[细粒度能力](../design/fine-grained-capabilities.md)。命名命令来自 Python `@command` 注册函数，YAML 不生成函数。

## 已准备模板示例

引用的模板必须已经包含应用及服务端依赖，已有卷必须对该 Provider/账号可用。Python 只创建并拥有 Sandbox，不删除借用卷本体。

```yaml
specVersion: 1
name: python-hello
sandbox:
  provider: alicloud-express
  template:
    reference: base
  instance:
    timeout: 600
    cpu: 2
    memory: 2048
    envs:
      APP_MESSAGE: hello
    metadata:
      purpose: example
    volume_mounts:
      /data: existing-volume-name
  start: python /home/user/app/commands.py
  ready: agent-sandbox-server healthcheck --port 9000
  services:
    app:
      protocol: agent-sandbox-server
      version: 2
      port: 9000
      operations: [commands.list, commands.run]
```

源码准备时将 `reference` 换为 `source: {dockerfile: Dockerfile, context: .}` 并使用 CLI，Python 仍需准备后的引用。启动命令和镜像原生入口应只有一个启动责任方，避免同一服务启动两次。参阅[启动与清理](../guide/template-workflows.md)。

Provider 作者可覆盖可选的同步 `Provider.validate_template_input(stage, value)`，使用该版本的真实 schema。阶段为 `template.prepare`（模板对象）和 `sandbox.create`（实例对象），返回 `False` 或抛错表示拒绝。继承的默认方法不算校验器，异步校验会被拒绝。校验通过不授予操作能力，也不代表高层创建 API 自动承接了尚未实现的实例字段。

`sandbox.ports` 保留浏览器调试、数据库等可选附加端口；编译端口列表为它与服务端口的排序去重并集。`session.endpoints[端口]` 返回未归属 `sandbox.services` 的附加端口的 Provider 描述，网关请求头只在内存中。它不创建 ServerClient，也不发送 health/discovery 请求。声明端口不保证原生 TCP 或公网可达，实际地址与协议由 Provider 决定。也可单独调用 `await sandbox.application_endpoint(port)`，已有服务客户端仍在 `session.services`。
