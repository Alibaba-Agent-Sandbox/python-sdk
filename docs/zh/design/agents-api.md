# Agents API：在 Agent Sandbox 里托管编码 Agent

> 状态：现行设计

服务端部分（路由、线上格式、运行时语义）与代码一致；第 7 节的 Python 客户端和部分适配器不是现行行为，见下。

## 读者今天应该相信什么

- 跑 Agent 只有一条路：服务端的 `/v1/agents/sessions` 等路由。CLI 没有 `abx agent` 命令，SDK 没有 `sb.agent.*` 辅助方法。
- 服务端声明 70 条 Agents API 路由，全部是真实实现，每条路由有表驱动测试。
- 只有 `codex` 和 `qwen-code` 有本地后端。`claude-code`、`cursor`、`command` 是已声明的适配器，没有本地后端；`GET /v1/agents/runtimes` 对它们报告 `implemented: false`，选中它们的请求会得到 404 `agents.not_implemented_locally`。
- `POST /v1/responses` 现行存在，每次响应是一次本地 CLI 回合。
- 英文正文第 7 节的 Python 客户端（`agent_sandbox.agents`、`Agent`、`Runner`、`Session`、`sb.agents`）代码里没有；现行客户端用法以指南为准。
- 英文正文里关于 `claude-code` 和 `cursor` 适配器行为的描述没有对着真实二进制验证过，不要当作已有功能。

## 现行文档

- 指南：[../guide/agents-api.md](../guide/agents-api.md)
- 路由参考：[../reference/agents-api.md](../reference/agents-api.md)
- 服务端 API：[server-api.md](server-api.md)

## 完整英文原文

[../../en/design/agents-api.md](../../en/design/agents-api.md)。评审记录见 [agents-api-review.md](../archive/agents-api-review.md)。
