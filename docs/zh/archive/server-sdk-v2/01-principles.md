# 01 - 原则、范围与非目标

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇给出目标设计的七条规则：每个操作只有一个点分 ID、所有操作走同一条策略管线、默认不挂载、能力由数据声明等。
- 「点分操作 ID」（如 `files.list`）是设计提议。现行服务端的唯一标识是端点 id（如 `files_list`），定义在 `server/endpoints.py` 的 `ENDPOINTS` 表里。
- 它还定义了范围（服务端是模板作者的控制面，不是 envd 的替代品）、术语表和兼容立场。
- 规则 R1 到 R7 里凡是依赖操作注册表（`Registry`、`@op`）的部分，代码都没有实现。
- 现行服务端的策略只有一层：`ServerPolicy` + `PolicyEngine`，组只是端点 id 的别名。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/01-principles.md](../../../en/archive/server-sdk-v2/01-principles.md)。
