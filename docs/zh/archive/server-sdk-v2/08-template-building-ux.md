# 08 - 模板构建体验

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计 `template.yaml` 的 `server:` 段、Python 写法、作者旅程、本地开发循环、迁移步骤和作者可见的错误与提示。
- `server:` 段和构建时注入的现行行为，以 [`../../guide/template-server-api.md`](../../guide/template-server-api.md) 和 [`../../reference/template-yaml-spec.md`](../../reference/template-yaml-spec.md) 为准。
- 文中依赖点分操作 ID 和 `Policy()` 构建器的写法，现行代码不接受。
- `legacy_compat` 预设不会存在：项目未发布，没有兼容层。
- 文中的 `explain`、`doctor`、热重载等本地开发命令没有实现。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/08-template-building-ux.md](../../../en/archive/server-sdk-v2/08-template-building-ux.md)。
