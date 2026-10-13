# 09 - 面向 AI 写配置的可用性

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计给 AI 用的服务端配置参考卡、带修复提示的错误目录、反模式清单和 `llms.txt` / `SKILL.md` 产物。
- 参考卡里的规则使用点分操作 ID 和 `Policy()` 写法，现行服务端不接受，照抄不会生效。
- 写现行配置请看 [`../../guide/template-server-api.md`](../../guide/template-server-api.md) 和 [`../../guide/file-and-command-controls.md`](../../guide/file-and-command-controls.md)。
- 错误目录里的「作为数据实现于 `core/errors.py`」没有对应实现；现行错误码见 `reference/error-codes.md`。
- 第 7 节的 AI 使用者模拟流程是评审方法，不是产品功能。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/09-ai-codegen-usability.md](../../../en/archive/server-sdk-v2/09-ai-codegen-usability.md)。
