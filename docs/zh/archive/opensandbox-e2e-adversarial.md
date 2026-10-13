# OpenSandbox 提供方：对抗式端到端记录

> 状态：归档。不是现行规范。

> 状态：评审记录，不是现行规范

这是 2026-10-13 在本机 OpenSandbox 服务端（`opensandbox-server==1.1.1`，Docker 运行时，镜像 `python:3.12-slim`）上跑出来的测试记录，不是规范。

## 读者今天应该相信什么

- 被测的插件在 [awesome-providers](https://github.com/alibaba-agent-sandbox/awesome-providers) 的 `opensandbox/` 目录，不在本仓库；本仓库只保留宿主侧和本地服务端脚手架（`e2e/opensandbox/`）。
- 复现并修复了三条缺陷：默认入口 `python3 commands.py` 在通用镜像里退出导致创建失败；`abx sandbox kill` 因先 `get` 而不幂等；同一个 `Sandbox` 对象第二次 `kill()` 报 `E8021`。
- 记录里验证过的路径：钉住提交的 `abx provider install`、同步 / 流式 exec、含空格和引号的 Unicode 文件路径、端口 URL、pause / resume、错误 API key（`E1001`，错误文本不含密钥）。
- `process.stdin`、PTY、代码解释器、模板构建被声明为不支持，没有单独对着服务端验证。
- 记录里的部分错误码已被之后的重跑取代（例如未知沙箱的 `connect` / `info` 现在是 `E2009`，不再是 `E8005`）；英文页末尾有说明。
- 英文页里「中文」一节是同一份记录的中文摘要。

## 完整英文原文

[../../en/archive/opensandbox-e2e-adversarial.md](../../en/archive/opensandbox-e2e-adversarial.md)
