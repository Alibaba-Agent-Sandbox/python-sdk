# 07 - 客户端镜像：Python `ServerClient` 与 Node CLI

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计从同一份操作目录生成 Python `ServerClient`、`operations.json` 和 TypeScript 客户端，并统一客户端错误码范围 E3100-E3111。
- 代码没有生成客户端，没有 `ServerClient` 和 `operations.json`。
- 现行客户端与服务端通过同一张端点表里的 id 对齐；对照关系见 [`../../design/client-server-alignment.md`](../../design/client-server-alignment.md) 和 [`../../design/server-api.md`](../../design/server-api.md)。
- 07 第 6 节的「每个操作的客户端对应项」台账是目标清单，不是已完成的对照表。
- 错误码以 [`../../reference/error-codes.md`](../../reference/error-codes.md) 为准。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/07-client-mirror.md](../../../en/archive/server-sdk-v2/07-client-mirror.md)。
