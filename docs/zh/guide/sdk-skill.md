# 给写代码的 agent 的 SDK skill

`agent-sandbox-sdk/` 里的 skill 告诉编码 agent 如何编写这个 SDK 的代码。它是一份静态说明，SDK 不会执行它。

任务是写客户端，或写模板（`template.yaml`、Dockerfile、`commands.py`）时，加载这份说明。用 `abx` 或 MCP 操作一台已经存在的沙箱，用的是 `agent-sandbox` 仓库里的 CLI skill。部署、本地健康检查和发布这两个包，是 skill 末尾的一小段。

这份说明包括：

- 客户端：`Sandbox.create`、`commands.run`、`run`、`files`，以及内置提供方 `alicloud-express`
- 模板：`template.yaml`、`Dockerfile`、用 `@command` 和 `start()` 写的 `commands.py`
- 部署：`abx template deploy`（Python 包不构建镜像）
- 测试：`make test`，以及在本地启动 `commands.py` 做健康检查
- 发布：两个包同一个版本号，由 GitHub Release 发布

skill 目录是 [agent-sandbox-sdk](../../../agent-sandbox-sdk/SKILL.md)。把整个目录复制过去，让 `SKILL.md` 位于名为 `agent-sandbox-sdk` 的文件夹里。frontmatter 里的 `name` 和这个文件夹同名。模板的补充说明在旁边的 `references/templates.md`。

写一个新的提供方插件是另一份技能：[agent-sandbox-provider](../../../agent-sandbox-provider/SKILL.md)。
