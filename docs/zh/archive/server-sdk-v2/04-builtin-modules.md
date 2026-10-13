# 04 - 内置模块与操作目录

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇列出目标设计里的内置操作目录（文中的默认注册表是 105 个操作），按模块和组划分：`core`、`files`、`commands`、`terminal`、`system`、`devtools`、`browser`、`custom`、`agents`。
- 表里的点分 ID、生成命令 `python -m agent_sandbox.server describe --markdown` 和漂移测试，代码都没有实现。
- 现行服务端声明了 118 个端点（其中 70 个属于 Agents API；PTY WebSocket 是虚拟端点 `pty_connect`），都在 `ENDPOINTS` 表里。
- 组（如 `file_ops`、`process`、`terminal`、`dev_tools`、`browser`、`commands`、`agents`）现行存在，但只是展开成端点 id 的别名。
- 要查某个端点是否可用，用现行的 `GET /capabilities`，不要用本页的目录。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/04-builtin-modules.md](../../../en/archive/server-sdk-v2/04-builtin-modules.md)。
