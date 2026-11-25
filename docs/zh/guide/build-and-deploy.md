# 构建与部署

Python SDK 负责运行时调用。源码获取、构建、部署和源码版本发布由 CLI 负责。以下为当前源码入口，安装版用法以 `abx --help` 为准。

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
```

部署会处理源码准备。后续通过部署名称查询和删除，此流程不需要传递内部构建或收据文件。删除前，可用部署返回的沙箱 ID 从 Python 连接，按照[应用连接指南](template-workflows.md)调用注册的 `hello` 函数。

目标已绑定 OpenAPI 合同时，`abx sandbox my-app --help` 列出业务操作，`abx sandbox my-app OPERATION --help` 展示参数。操作名来自该合同；只注册 Python 函数不会自动建立 CLI 绑定。详见 [CLI API 指南](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/sandbox-api.md)。

使用已有平台模板时，Python 可直接 `await ProviderSandbox.create(template=template_id, provider=provider)`。CLI 创建的应用则用其返回的沙箱 ID 连接，避免再创建一个实例。`launch_template` 是高级运行时入口：调用者必须确保镜像入口或平台启动命令不会重复启动清单中的服务。

使用完 CLI 创建的部署后，通过名称删除：

```bash
abx delete my-app --yes
```

[CLI 模板编写](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md) · [SDK 应用连接](template-workflows.md)
