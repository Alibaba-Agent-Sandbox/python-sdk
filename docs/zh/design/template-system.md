# 模板系统

模板包含可复用应用源码与命名 Sandbox／Serving 资源。使用 `specVersion: 1`、可选的
作者自定义 `vars`、`sandbox.<名称>.template` 和组件原生 `serving.<名称>.props`。
[字段参考](../reference/template-yaml-spec.md)提供规范入口及 Python 当前消费边界。

## 职责

模板负责应用源码、依赖和运行启动代码。Provider 负责原生准备、实例生命周期与端点解析。
CLI 处理资源表达式、构建和部署；部署 Sandbox 资源不代表创建未来每个运行实例。

Python 通过 ProviderSandbox 使用已准备 ID，或连接已有实例。模板脚本负责动态创建实例，
携带私有运行配置启动应用。托管 Agents API 由 Worker 管理每个 Session 的实例，
业务客户端只调用同一个 Gateway。

## 运行与源码配置

当前命名资源 template.yaml 由 CLI 消费。SDK 现有 launch_template／TemplateSession
快照接口与发现投影尚未迁移到这些源码文件。保留其独立支持边界，不能因为版本编号相同
就推断当前源码格式已经可用。

直接运行路径不需要再增加一套 YAML 解析器或 Python 部署引擎。原生 Devs 负责表达式；
应用运行配置与服务端策略独立于资源准备。

## 资源归属与清理

只删除所属应用创建的实例和资源。关闭本地连接不会删除借用实例。托管 Session 的关闭、
清理 Operation 与公开删除分开；检查操作结果后再将计算资源视为释放。

参阅 [Python 运行示例](../guide/template-workflows.md)、
[模板编写](../guide/authoring-templates.md)和[服务端 API](../guide/template-server-api.md)。
