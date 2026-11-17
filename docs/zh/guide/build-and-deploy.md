# 构建与部署

Python SDK 负责运行时调用。源码获取、构建、部署和源码版本发布由 CLI 负责。以下为当前源码入口，安装版用法以 `abx --help` 为准。

```bash
abx template init ./my-template --template python
abx deploy ./my-template --name my-app --yes
abx status my-app
abx delete my-app --yes
```

重复部署时，可先用 `abx template build ./my-template --out ./.abx/build.json --yes` 准备构建，再用 `abx deploy --build ./.abx/build.json --name my-app --yes` 复用。构建不创建运行实例。删除应用后，独立构建仍保留；用 `abx template build --clean ./.abx/build.json --yes` 清理不再被应用使用的构建资源。镜像等需手动清理的资源会明确列出。

Sandbox 资源部署后返回可复用模板 ID。按所选模板的 `run.py` 说明创建并启动动态实例，或调用 `await ProviderSandbox.create(template=template_id, provider=provider)` 后显式启动应用。后续通过该 Sandbox ID 连接；删除已准备资源前，先关闭／删除自有动态实例。SDK 较早的 `launch_template` 快照接口不接受当前命名资源源码，详见下方运行指南。

[CLI 模板编写](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/guide/authoring-templates.md) · [SDK 应用连接](template-workflows.md)
