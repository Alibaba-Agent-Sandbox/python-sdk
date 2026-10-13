# 06 - 延迟安装、清单与 `agent-sandbox-server` 命令

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计 Agent CLI 的延迟安装：清单格式、校验和、安装算法、镜像与离线、`prepare` 子命令、只读文件系统和慢安装返回 202 加任务 id。
- 代码没有实现这套安装机制，也没有清单文件。
- 现行 `python -m agent_sandbox.server` 只有四个子命令：`serve`、`healthcheck`、`check-config`、`version`。`prepare`、`doctor`、`explain`、`describe` 不存在。
- 本页的延迟安装不存在；需要哪个 Agent CLI，由镜像或模板自己准备。
- `GET /v1/agents/runtimes` 只报告 `implemented` 和 `installed`，不会替你安装。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/06-lazy-install.md](../../../en/archive/server-sdk-v2/06-lazy-install.md)。
