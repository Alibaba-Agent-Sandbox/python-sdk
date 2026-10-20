# Application runtime image / 应用运行时镜像

Build from the repository root with a reviewed Python base, for example during
local development (production must pin the reviewed base digest):

```bash
docker build --build-arg PYTHON_IMAGE=python:3.11-slim \
  -f examples/applications/Dockerfile -t agent-application:local .
```

The image contains the real optional application runtime and its FC/PostgreSQL
adapters. The same image runs all three roles; override the command with
`python -m agent_sandbox.applications worker` or `dispatcher` for private functions.
The factory loads only trusted packaged code, never business-supplied module paths.

Required bindings and lifecycle limits are documented in the
[English guide](../../docs/en/guide/agent-applications.md) and
[中文指南](../../docs/zh/guide/agent-applications.md).
`ABX_APP_SPEC_JSON` is compiled from the optional `application:` section of the
single `template.yaml`; do not introduce an `agent-app.yaml` file.

Set FC private ingress, async Task configuration, periodic dispatcher trigger,
runtime binding secrets and a compatible immutable sandbox reference before
deployment. This example does not provision a database, credentials, IAM roles,
model account or sandbox templates, and does not claim a tested/published image.

该镜像使用真实运行时、PostgreSQL 与 FC SDK 适配器。三个角色共用镜像，通过启动命令
区分。应用配置来自单一模板，凭据由部署绑定注入。云端验收须验证 IAM、私有入口、
周期触发、模型、Sandbox 与清理；本地构建示例不代表这些资源已创建或验收通过。

Runtime testing does not require an image build or Docker. The bilingual guides
above include ordinary Python-process, real temporary PostgreSQL and real remote
sandbox test commands. This Dockerfile is for the separate image/deployment path.

运行时可直接用 Python 进程和真实临时 PostgreSQL 测试，不需要先构建镜像或安装 Docker；
上方中英文指南提供直接运行的命令。此 Dockerfile 用于独立的镜像/部署验收。
