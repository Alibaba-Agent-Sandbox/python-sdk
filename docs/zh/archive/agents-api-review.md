# Agents API 设计：对抗式评审记录

> 状态：归档。不是现行规范。

> 状态：评审记录，不是现行规范

这是对 [agents-api.md](../design/agents-api.md) 设计的两轮评审日志。它记录当时发现了什么、怎么改的，不描述现行行为。

## 读者今天应该相信什么

- 两轮评审（功能完整性与 OpenAI 兼容度；体验、安全、向后兼容、可测性）共列出 R1-1 到 R2-23 共 39 条发现，按 H / M / L 分级。
- 评审由同一作者分成多轮、各带一个视角完成，不是独立的子 Agent 或他人评审；英文页开头有如实说明。
- 条目里的小节号（如 §6.6、§9.2）指向评审当时的设计稿，现行设计页的小节可能已经变了。
- 评审结束时仍然开放的问题：真实 CLI 的行为（`cursor-agent` 的 JSONL、Qwen 的 MCP 文件、各版本的 Codex 配置）没有验证；`full_access` 默认值需要产品决定；服务端没有 YAML 解析器，服务端配置文件用 JSON；CLI 不提供 agent 命令，Agents API 是唯一入口。
- 要知道现行路由和哪些运行时可用，读 [agents-api.md](../design/agents-api.md) 的状态说明和 [../guide/agents-api.md](../guide/agents-api.md)。

## 完整英文原文

[../../en/archive/agents-api-review.md](../../en/archive/agents-api-review.md)
