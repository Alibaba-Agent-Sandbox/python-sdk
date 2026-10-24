# 构建与部署

Python SDK（`agent-sandbox-client`）是**运行时**客户端：创建、使用、销毁沙箱。它不构建镜像，也不注册模板。模板的构建和部署由 `abx` CLI 负责。

| 步骤 | 命令 | 说明 |
|------|------|------|
| 编写 | `abx template scaffold` | 生成 `Dockerfile`、`template.yaml`、`commands.py` |
| 构建 | `abx template build` | 按所选 Dockerfile 或显式云端 steps 构建 |
| 发布 | `abx template deploy`（或 `abx deploy`） | 发布所选构建路径；创建前确认返回的实际状态 |
| 启动 | `abx create <TEMPLATE_ID>` 或 `Sandbox.create(template=...)` | 运行时；SDK 从这里开始 |

完整流程、全部选项和 AI 辅助编写步骤见 CLI 的[部署与构建](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/deploy-and-build.md)指南。

## 云端 steps 与就绪状态

Dockerfile 部署需要本地 Docker 和已配置的镜像仓库。
`abx template deploy --build steps` 使用 `template.yaml` 中的显式步骤，不需要本地
Docker 或 ACR 上传，但不会自动转换 Dockerfile，也不会自动上传本地 `COPY` 文件。
目录中的 `python-hello` 可按[公开 steps 准备指南](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/platform-steps.zh-CN.md#无-docker-运行-python-hello)操作。

CLI 0.4.11 的直接 steps 部署可能返回 `Status: submitted` 和 `TemplateID`。
受理不等于就绪：设置有限等待期限，轮询 `abx --json template info ID`，直到状态为
`ready`；构建失败则停止并清理。该版本的 `status` 是包含 Python 字典的字符串，自动化时
先解析外层 JSON，再用 `ast.literal_eval` 解析此字符串，不使用 `eval`。
就绪后才调用 `abx create ID --detach` 或 `ProviderSandbox.create(template=ID)`。
保留每个精确资源 ID，先 `abx kill SANDBOX_ID`，再 `abx template delete TEMPLATE_ID -y`，
并通过精确 ID 查询确认资源不存在。提交成功或列表为空本身不足以证明就绪或清理完成。

## 在 Python 里使用结果

```python
from agent_sandbox import ProviderSandbox as Sandbox

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
