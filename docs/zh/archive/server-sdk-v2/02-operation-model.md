# 02 - 操作模型

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计 `@op` 装饰器、操作注册表、点分 ID 语法、HTTP 绑定规则和统一请求管线。
- 代码里没有 `@op`、`Registry`，也没有 `POST /ops/{id}`、`GET /ops`、`core.describe`、`core.check` 和 `GET /openapi.json`。
- 现行的发现接口是 `GET /capabilities` 和 `POST /capabilities/check`。
- 现行的自定义能力是 `CommandRegistry`（`command` 装饰器、`GET /commands`、`POST /commands/{name}`），不是 02 第 8 节的「自定义操作」。
- 现行请求管线只有一条：`SandboxRequestHandler`（匹配、鉴权、准入、重复查询参数检查、体积限制、处理、审计）。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/02-operation-model.md](../../../en/archive/server-sdk-v2/02-operation-model.md)。
