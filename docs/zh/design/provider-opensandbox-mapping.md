# OpenSandbox 作为 Agent Sandbox 提供方：调研、API 映射、配置项与测试计划

> 状态：评审记录，不是现行规范

这是实现前的调研和映射，第 9 节补了 2026-10-13 实测之后的状态。提供方的现行规范是 [providers-and-credentials.md](providers-and-credentials.md)。

## 读者今天应该相信什么

- OpenSandbox 是基于镜像的沙箱平台：`template` 就是容器镜像 URI，Docker 运行时没有模板构建和注册表。
- 映射结论：生命周期、exec（同步和流式）、文件、端口 URL、PTY、pause / resume 是原生支持；改 TTL、列出进程等是模拟的；文件监听、签名传输 URL、模板构建是不支持的（返回带类型的错误）。
- 英文页的每条行为结论都标了 [spec]、[code] 或 [live]；只有 [spec] 或 [code] 的没有被实际运行验证过。
- 提供方插件（`exec` 类型，EPP/1 协议）在 [awesome-providers](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox)，不在本仓库。
- 第 9 节是实现后的状态：创建、exec、文件、超时、pause / resume、端口 URL 在 `abx` 和 `Sandbox.create(provider="opensandbox")` 两条路径上都跑通；`send_stdin` 是 `E8004`；网络策略的出口 sidecar 没有被实测。
- 凭证变量是 `ABX_OPENSANDBOX_API_KEY` 和 `ABX_OPENSANDBOX_BASE_URL`。
- 第 3 节的配置项和第 6 节的 EPP/1 草案缺口是提案，以第 9 节和现行提供方文档为准。

## 完整英文原文

[../../en/design/provider-opensandbox-mapping.md](../../en/design/provider-opensandbox-mapping.md)
