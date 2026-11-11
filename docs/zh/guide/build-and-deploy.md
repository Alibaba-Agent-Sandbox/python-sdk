# 构建与部署

Python SDK 负责运行时调用。源码获取、构建、部署和源码版本发布由 CLI 负责。以下为当前源码入口，安装版用法以 `abx --help` 为准。

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
abx sandbox command run my-app hello --arg name=Ada
abx delete my-app --yes
```

重复部署时，可先用 `abx template build ./my-template --out ./.abx/build.json --yes` 准备构建，再用 `abx deploy --build ./.abx/build.json --name my-app --yes` 复用。构建不创建运行实例。删除应用后，独立构建仍保留；用 `abx template build --clean ./.abx/build.json --yes` 清理不再被应用使用的构建资源。镜像等需手动清理的资源会明确列出。

使用已有平台模板时，Python 可直接 `await ProviderSandbox.create(template=template_id, provider=provider)`。CLI 创建的应用则用其返回的沙箱 ID 连接，避免再创建一个实例。`launch_template` 是高级运行时入口：调用者必须确保镜像入口或平台启动命令不会重复启动清单中的服务。

[CLI 模板编写](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md) · [SDK 应用连接](template-workflows.md)
