# 构建与部署

Python SDK（`agent-sandbox`）是**运行时**客户端：创建、使用、销毁沙箱。它不构建镜像，也不注册模板。模板的构建和部署由 `abx` CLI 负责。

| 步骤 | 命令 | 说明 |
|------|------|------|
| 编写 | `abx template init` | 生成 `Dockerfile`、`template.yaml`、`commands.py` |
| 构建 | `abx template build` | 对模板目录执行 `docker build` |
| 发布 | `abx template deploy`（或 `abx deploy`） | 构建、推送到阿里云 ACR、注册模板、等待就绪 |
| 启动 | `abx create --template <TEMPLATE_ID>` 或 `Sandbox.create(template=...)` | 运行时；SDK 从这里开始 |

完整流程、全部选项和 AI 辅助编写步骤见 CLI 的[部署与构建](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)指南。

## 在 Python 里使用结果

```python
from agent_sandbox import Sandbox

async with await Sandbox.create(template="<TEMPLATE_ID 或别名>") as sandbox:
    print(await sandbox.run("hello", name="Ada"))      # 注册在模板 server 里的命令
    proc = await sandbox.commands.run("python3 --version")
```

带 `agent-sandbox-server` 的模板见[编写模板](authoring-templates.md)和[模板服务器 HTTP API](template-server-api.md)。

## 有什么变化

早期的 SDK 自带一套构建流水线（`Sandbox.deploy`、`Image`、`DockerBuilder`、`TemplateManager`、`[alicloud]` extra 和 E7xxx 构建错误码）。它们已删除：一条流水线，一个工具。如果你的代码调用过它们，换成上面的 CLI 命令（脚本里可以运行 `abx template deploy --yes`）。

## 下一步

- [编写模板](authoring-templates.md) — 通过 template.yaml 定义模板
- [SDK 使用指南](sdk-usage.md) — SDK 的运行时用法

## 相关：abx CLI

命令行的模板生命周期记录在 [`cli` 仓库](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)。
