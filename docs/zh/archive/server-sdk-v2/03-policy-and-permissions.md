# 03 - 策略与权限

> 状态：归档。不是现行规范。

> 状态：目标设计，代码没有实现

现行服务端用端点 id 和一个策略引擎，不是本页描述的操作模型。先读 [README](README.md) 看已实现和未实现的清单；现行服务端的行为以 [`../../design/server-api.md`](../../design/server-api.md) 为准。

## 读者今天应该相信什么

- 这一篇设计一套按操作 ID 写 `allow` / `deny` 规则的策略模型，含预设、路径范围、命令范围、钩子、限额、配置分层和 v2.1 的加固规则。
- `Policy().allow(...)`、`PathScope`、`CommandScope`、`UrlScope`、`AgentScope`、只能否决的钩子、按主体 `role:` / `id:` 匹配，代码都没有实现。
- 现行策略是 `ServerPolicy` 数据：`groups`、`endpoints` 选择器（`enabled`、`scopes`、`paths`、`limits`、`params`）和 `audit`；最具体的选择器优先（端点 id、通配符、组、`@defaults`）。
- 现行防护包括路径边界（默认 `/home/user`）、命令允许/拒绝参数、体积限制、限流和并发上限、审计。
- 03 第 15 节的 Host/Origin 白名单、套接字超时、一次性 PTY 票据没有实现，不要当作已有的安全属性。

## 完整英文原文

长篇目标设计只有英文版：[../../../en/archive/server-sdk-v2/03-policy-and-permissions.md](../../../en/archive/server-sdk-v2/03-policy-and-permissions.md)。
