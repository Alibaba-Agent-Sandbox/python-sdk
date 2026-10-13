# 05 - 作为内置能力的 Agents API

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计把 OpenAI Agents API 重新表达成操作族，并把官方 47 个操作分成四个梯队。
- 文中的操作 ID 命名、梯队划分、适配器协议和 `llm:` 端点配置是目标设计，代码没有按它实现。
- 现行 Agents API 是 70 条真实路由，每条都有表驱动测试，说明见 [`../../design/agents-api.md`](../../design/agents-api.md)（英文）和 [`../../guide/agents-api.md`](../../guide/agents-api.md)。
- 本地后端只有 `codex` 和 `qwen-code`；`claude-code`、`cursor`、`command` 是已声明的适配器，没有本地后端（`GET /v1/agents/runtimes` 里 `implemented: false`）。
- `/v1/responses` 现行存在，每次响应是一次本地 `codex` 或 `qwen-code` CLI 回合；05 里其余适配器的本地后端和梯队划分没有实现。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/05-agents-api.md](../../../en/archive/server-sdk-v2/05-agents-api.md)。
