# 模板系统

模板采用规范 5，描述完整沙箱内容、启动与就绪命令，以及所有对外服务。
启动模板不会再按工作流、单个操作或 application/exec/interpreter 类型选择其中一部分。

## 职责

模板负责应用源码、依赖、配置和启动。Provider 负责镜像上传注册、平台标识、沙箱创建和
服务地址解析。CLI 准备源码并整体启动模板。Python 消费已准备好的引用，或连接既有沙箱，
不承担 Docker 和源码构建职责。

## 启动与使用

CLI 使用 `abx --provider PROVIDER template launch TEMPLATE_REF`；Python 使用
`launch_template(manifest, provider=..., reference=...)`。启动前只检查创建、启动、
就绪和清理实际需要的操作。缺少解释器不阻止无关应用启动。执行具体操作时，
Provider 和服务端策略仍负责实际能力与权限检查。

保留 `provides` 中所有服务。SandboxServer 检查协议；其他协议返回客户端，
由作者的就绪命令检查。多服务模板只启动一次，后续选择调用地址不会改变启动内容。

## 清单与迁移

参见[字段参考](../reference/template-yaml-spec.md)和权威的
[规范 5 schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v5.schema.json)。
删除 `workflow_contract_version`、`default_workflow`、`workflows`，保留
`spec_version: 5`、`provides`、`start_cmd`、`ready_cmd` 以及应用元数据。
旧运行清单明确要求迁移，不静默选择旧默认项。源码位置、镜像引用和平台模板 ID
属于准备过程的输入，不再暴露为用户选择的启动流程。

## 资源归属与验证

启动器记录创建意图与资源 ID，不自动重放结果不确定的创建请求。
清理时尝试关闭所有客户端并删除自己创建的沙箱，保留失败记录供核对。
连接已有沙箱不代表获得删除它的所有权。

目录收录或静态计划支持不等于实测成功。历史工作流证据保留，但不认证规范 5。
模板元数据版本不代表有一个 Registry 版本存储服务器；复现应使用真实 Git 修订和运行输入。

参见 [Python 启动示例](../guide/template-workflows.md)、
[模板编写](../guide/authoring-templates.md)和[服务端 API](../guide/template-server-api.md)。
