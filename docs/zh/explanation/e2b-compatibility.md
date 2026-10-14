# E2B 兼容性

本文档说明 Agent Sandbox 与 E2B Python SDK 的关系：哪些方法的形状一致、哪里不同、为什么。Agent Sandbox **不是** E2B 的直接替代品，它是另一套服务，只是方法名参考了 E2B，让迁移少改代码。

---

## 设计目标

迁移策略是：

> **让使用 E2B SDK 的用户以最小改动迁移到 Agent Sandbox，同时不被 E2B 的历史设计约束所限制。**

具体而言：
- 核心方法签名与 E2B 接近
- 环境变量不同（`ABX_*`），不读取 E2B 的 `E2B_*`
- 提供一个很小的 `compat` 模块，重新导出 `Sandbox`，简化迁移
- 只是部分对应：有两个方法会抛错（见下文），个别行为不同

---

## 共同点

### API 签名

以下方法与 E2B Python SDK 同名、调用形式一致：

| API | 状态 |
|-----|------|
| `Sandbox.create(template, timeout, metadata, envs)` | ✅ 兼容 |
| `Sandbox.connect(sandbox_id)` | ✅ 兼容 |
| `Sandbox.list()` | ✅ 兼容 |
| `sandbox.kill()` | ✅ 兼容 |
| `sandbox.is_running()` | ✅ 兼容 |
| `sandbox.pause()` | ✅ 兼容 |
| `sandbox.set_timeout(seconds)` | ✅ 兼容 |
| `sandbox.run_code(code, language, timeout)` | ✅ 兼容 |
| `sandbox.commands.run(cmd, timeout, env, cwd)` | ✅ 兼容 |
| `sandbox.files.read(path)` | ✅ 兼容 |
| `sandbox.files.write(path, content)` | ✅ 兼容 |
| `sandbox.files.list(path)` | ✅ 兼容 |
| `sandbox.files.remove(path)` | ✅ 兼容 |
| `async with await Sandbox.create() as sb:` | ✅ 兼容 |

### 环境变量

每项设置只有一个环境变量。使用这些名字，而不是 E2B 的变量名：

| 设置 | 环境变量 |
|------|------|
| 沙箱 API Key | `ABX_SANDBOX_API_KEY` |
| 平台 API URL | `ABX_SANDBOX_BASE_URL` |
| 数据平面域名 | `ABX_SANDBOX_DOMAIN` |

### 兼容层

```python
from agent_sandbox.compat import Sandbox
```

`compat` 模块是迁移辅助。它重新导出 `Sandbox` 类，无额外包装（另有别名 `E2BSandbox`），并不能让 E2B 代码原样运行。

---

## 有什么不同

### 1. `Sandbox.kill(id)` 类方法

**E2B**：`Sandbox.kill(id)` 是类方法，按 ID 销毁沙箱。

**Agent Sandbox**：类方法重命名为 `Sandbox.kill_by_id(id)`，`kill()` 保留为实例方法。

**原因**：Python 中同名的类方法和实例方法会产生歧义。将按 ID 销毁的类方法显式命名为 `kill_by_id` 更清晰，避免 `Sandbox.kill("sbx-xxxx")` 和 `sandbox.kill()` 的混淆。

### 2. `sandbox.get_host(port)` 直接方法

**E2B**：`sandbox.get_host(port)` 是 Sandbox 实例的直接方法。

**Agent Sandbox**：移到 `sandbox.network.get_host(port)` 子模块下。

**原因**：将网络相关功能聚合到 `network` 子模块，与 `commands`、`files` 等子模块保持一致的组织结构。同时，`network` 方法需要 `ports` 能力门禁检查。

### 3. `upload_url()` / `download_url()`

**E2B**：`sandbox.upload_url(path)` / `sandbox.download_url(path)`（JavaScript 是 `uploadUrl` / `downloadUrl`）返回带 `signature` 的 URL。浏览器只凭这个 URL 就能上传或下载一个文件，不必带 `X-Access-Token`。

**Agent Sandbox**：同名方法抛出 `FileOperationError`。当前数据面不认这套签名。不带 `X-Access-Token` 的 `/files` 请求是 403，正文为 `access denied: X-Access-Token header is required`，文件不会写入。带上该 header 才能传文件，`signature` 查询参数不起作用。`get_upload_url()` / `get_download_url()` 是别名。`files.upload_url()` 返回的地址仍然要求这个 header。

### 4. 能力门禁

**E2B**：没有能力检查机制，所有功能始终可用。

**Agent Sandbox**：引入能力模型，API 调用前检查模板是否声明了所需能力。

**原因**：
- **安全性**：限制沙箱功能范围，遵循最小权限原则
- **明确性**：在调用时立即报错（E3004），而不是在后端返回晦涩的错误
- **可扩展性**：为未来的细粒度权限控制奠定基础

### 5. 部分 RPC 路径

某些 API（`run_code`、`get_terminal` 等）的 RPC 路径基于 E2B SDK 逆向推断。这些路径在阿里云官方文档中未公开，可能存在差异。

---

## 扩展（非 E2B 功能）

Agent Sandbox 增加了 E2B 没有的功能：

| 功能 | 说明 |
|------|------|
| AK/SK 认证 | 阿里云 AccessKey 对认证 |
| 能力模型 | 模板级能力声明和运行时门禁 |
| 注册命令 | 在沙箱 server 里注册函数（`@sandbox.register`），用 `sandbox.run(name, **kwargs)` 调用 |
| @sandbox 装饰器 | 声明式远程函数执行 |
| MCP Server | AI IDE 集成（Cursor/Claude/VS Code） |
| 会话管理 | 命名会话持久化 |
| 密钥管理 | 环境变量和 `.env` 文件安全存储 |

---

## 下一步

- [从 E2B 迁移](../guide/migrate-from-e2b.md) — 实操迁移指南
- [架构概览](architecture-overview.md) — 系统架构
- [SDK 使用指南](../guide/sdk-usage.md) — 完整 SDK 用法
