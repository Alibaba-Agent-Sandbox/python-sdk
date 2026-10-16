# MCP 沙箱生命周期工具

Python MCP server 现在提供十个工具：除 [MCP 集成](mcp-integration.md) 中原有七个执行和
文件工具外，新增 `list_sandboxes`、`get_sandbox`、`set_sandbox_timeout`。它们复用现有
SDK API，仍受 provider 能力和平台权限限制。本文仅覆盖生命周期管理，不代表 Team 管理
或完整 MCP/Skills 产品规划已经实现。

## 列表和查询

`list_sandboxes` 返回当前授权账户及 provider 可见的沙箱，不会创建沙箱、选择默认沙箱或
将列表中的沙箱加入会话关闭清理。可选参数为 `status`（`SandboxStatus` 状态）、`limit`
（1–100，默认 100）、`offset`（非负整数，默认 0）、`provider`、`region`。
增加 `offset` 获取下一页；返回结果不承诺总数或下一页游标。

```json
{"name":"list_sandboxes","arguments":{"status":"running","limit":10,"offset":0}}
```

`get_sandbox` 通过 `Sandbox.refresh_info()` 获取平台最新元数据。指定 `sandbox_id` 查询
对应沙箱；省略则查询会话已有默认沙箱。没有默认沙箱时返回工具错误，查询不会创建沙箱
或延长生命周期。显式 ID 不改变默认沙箱。切换 provider 时可用 SDK 的
`provider:sandbox_id` 限定格式。查询会话未管理的 ID 时使用临时客户端，查询后仅关闭
该客户端连接，不会将沙箱加入会话关闭销毁清理。

```json
{"name":"get_sandbox","arguments":{}}
```

这两个工具的元数据结果仅包含 `sandbox_id`、`template`、`status`、`region`、
`started_at`、`end_at`、`cpu_count`、`memory_mb`、`disk_size_mb`。时间为 ISO 8601
字符串或 null，缺失的资源字段为 null。不返回访问令牌、环境变量、账户标识、用户
metadata、任意 lifecycle 对象或端点 URL。列表结果的 `sandboxes` 包含上述对象，另带
请求的 `limit`、`offset`。

## 创建和续期

`create_sandbox` 在原有 `template`、`timeout`、`envs` 基础上支持 `region`、`cpu`
（正整数，单位核）、`memory`（正整数，单位 MB）、`provider`（已配置的 provider ID）。
省略资源参数时保留 SDK/provider 默认值。资源组合仍由后端限制，通过输入校验不代表必然
可用。SDK 没有对应 Team 参数，因此不提供 Team 选择。

```json
{"name":"create_sandbox","arguments":{"template":"base","timeout":600,"cpu":2,"memory":1024}}
```

创建后该沙箱成为默认沙箱。秘密应保存在 MCP 进程已有授权配置中；工具参数和结果可能对
连接的模型可见。

`set_sandbox_timeout` 必须提供整数 `timeout`，范围 1–86400 秒，表示从现在起的生命周期，
而不是 HTTP 请求超时。可选 `sandbox_id` 省略时使用已有默认沙箱，不会隐式创建。
`Sandbox.set_timeout()` 成功后同步更新会话续期策略，后续执行/文件工具按该时长续期。
平台更新失败时保留之前的策略。
显式指定会话未管理的 ID 时只修改平台超时，随后关闭临时客户端，不会接管该沙箱或在
会话关闭时将其销毁。

```json
{"name":"set_sandbox_timeout","arguments":{"timeout":600}}
```

成功返回 `{"success":true,"sandbox_id":"...","timeout":600}`。非法整数（包括布尔值）、
越界 limit/timeout、显式空 ID、不支持的生命周期参数在调用平台前返回工具错误。创建工具
也校验资源整数及 `envs` 字符串键值。Provider/API 错误通过 `isError: true` 返回。

生命周期错误仅返回固定的失败类别、可用的 HTTP 状态，或 SDK 错误码及静态恢复建议。
工具结果和 MCP 生命周期错误日志均不包含 provider 原始错误消息、请求 URL、响应校验输入
或异常堆栈。输入校验仅指出无效字段，不回显字段值。

## 实现与验证

列表、查询、续期分别委托给 `Sandbox.list`、`refresh_info`、`set_timeout`，没有新增或
虚构平台端点。Python STDIO 与 Streamable HTTP 共用 schema 和 handler。Node.js CLI
有独立 MCP 实现，是否支持这些工具需要单独核对。

单元测试位于 `client-sdk/tests/test_agent/test_mcp_lifecycle.py`，覆盖输入边界、SDK 委托、
默认沙箱解析、续期失败和元数据泄漏检查。Mock 测试不能证明真实 provider 支持；云端结果
必须另行记录在仓库验证证据中。接口参考
[官方 MCP tools 规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)。
