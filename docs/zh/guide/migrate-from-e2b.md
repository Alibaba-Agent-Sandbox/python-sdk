# 从 E2B 迁移

Easy Sandbox 设计上与 E2B Python SDK 保持高度 API 兼容。本文档提供迁移指南。

---

## API 映射对照表

| E2B SDK | Easy Sandbox | 说明 |
|---------|-------------|------|
| `from e2b import Sandbox` | `from easy_sandbox.api.sandbox import Sandbox` | 主类导入 |
| `Sandbox.create()` | `Sandbox.create()` | ✅ 完全兼容 |
| `Sandbox.connect(id)` | `Sandbox.connect(id)` | ✅ 完全兼容 |
| `Sandbox.list()` | `Sandbox.list()` | ✅ 完全兼容 |
| `sandbox.kill()` | `sandbox.kill()` | ✅ 完全兼容 |
| `Sandbox.kill(id)` | `Sandbox.kill_by_id(id)` | ⚠️ 方法名不同 |
| `sandbox.is_running()` | `sandbox.is_running()` | ✅ 完全兼容 |
| `sandbox.pause()` | `sandbox.pause()` | ✅ 完全兼容 |
| `sandbox.set_timeout(t)` | `sandbox.set_timeout(t)` | ✅ 完全兼容 |
| `sandbox.commands.run(cmd)` | `sandbox.commands.run(cmd)` | ✅ 完全兼容 |
| `sandbox.files.read(path)` | `sandbox.files.read(path)` | ✅ 完全兼容 |
| `sandbox.files.write(path, d)` | `sandbox.files.write(path, d)` | ✅ 完全兼容 |
| `sandbox.run_code(code)` | `sandbox.run_code(code)` | ✅ 完全兼容 |
| `sandbox.get_host(port)` | `sandbox.network.get_host(port)` | ⚠️ 需通过 network 子模块 |
| `sandbox.get_upload_url(path)` | `sandbox.get_upload_url(path)` | 调用会失败。当前数据面要求 `X-Access-Token`，不接受只靠签名的 URL |
| `sandbox.get_download_url(path)` | `sandbox.get_download_url(path)` | 同上 |

---

## 导入路径替换

### 直接替换

```python
# E2B
from e2b import Sandbox

# Easy Sandbox（推荐）
from easy_sandbox.api.sandbox import Sandbox
```

### 使用兼容层

```python
# 兼容层导入（最小改动）
from easy_sandbox.compat import Sandbox
```

兼容层 `easy_sandbox.compat` 重新导出 `Sandbox` 类，API 签名与 E2B SDK 一致。

---

## 兼容层详情

兼容模块 `easy_sandbox.compat.sandbox` 提供：

```python
from easy_sandbox.compat import Sandbox
from easy_sandbox.compat import E2BSandbox  # 别名
```

两者是同一个 `Sandbox` 类，仅命名不同。

---

## 环境变量

Easy Sandbox 的每项设置只有一个环境变量。从 E2B 迁过来时设置这些：

| 设置 | 环境变量 |
|---|---|
| 沙箱 API Key | `EBX_SANDBOX_API_KEY` |
| 平台 API URL | `EBX_SANDBOX_BASE_URL` |
| 数据平面域名 | `EBX_SANDBOX_DOMAIN` |

---

## 不兼容点与解决方案

### 1. `Sandbox.kill(id)` → `Sandbox.kill_by_id(id)`

E2B 中类方法 `Sandbox.kill(id)` 按 ID 销毁沙箱。Easy Sandbox 中此功能由 `Sandbox.kill_by_id(id)` 提供，`sandbox.kill()` 是实例方法。

```python
# E2B
await Sandbox.kill("sbx-xxxx")

# Easy Sandbox
await Sandbox.kill_by_id("sbx-xxxx")
```

### 2. `get_host(port)` 需通过 network 子模块

```python
# E2B
host = sandbox.get_host(8080)

# Easy Sandbox
host = sandbox.network.get_host(8080)
url = sandbox.network.get_url(8080)
```

> **注意**：`network.get_host()` 和 `network.get_url()` 是本地 URL 计算辅助函数。它们在逻辑上关联 `ports` 能力，但**不会**执行运行时能力检查——无论模板是否声明了该能力，调用均会成功。

### 3. `get_upload_url()` / `get_download_url()`

E2B 的这两个方法返回一个浏览器可以直接打开的签名 URL。当前极速版 envd 不接受这种请求：不带 `X-Access-Token` 时返回 403，正文是 `X-Access-Token header is required`。因此 Easy Sandbox 的同名方法会抛出 `FileOperationError`，不会返回一个打不开的链接。

传文件用 `files.write()`、`files.read()`、`files.upload()`、`files.download()`。这些调用由 SDK 带上访问令牌。

### 4. 能力模型

Easy Sandbox 引入了能力模型。模板在 `template.yaml` 中声明能力。仅 `code` 能力在**运行时强制校验（fail-closed）**——`CodeContextModule` 方法在 `code` 能力缺失时抛出 `CapabilityNotSupportedError`（E3004）。其他模块转发请求而无运行时门控：

- `run_code()` / `code.*` → 需要 `code` 能力——**运行时强制校验（E3004）**
- `commands.run()` → 逻辑关联 `shell`（无运行时门控）
- `files.*` → 逻辑关联 `files`（无运行时门控）
- `network.*` → 逻辑关联 `ports`（无运行时门控）
- `get_terminal()` → 逻辑关联 `terminal`（无运行时门控）

默认能力集 `{shell, files, code}` 覆盖大多数常用操作。

### 5. 阿里云扩展

Easy Sandbox 增加了阿里云 AK/SK 认证方式，这在 E2B 中不存在：

```python
sandbox = await Sandbox.create(
    access_key_id="your-ak",
    access_key_secret="your-sk",
)
```

### 6. 单次请求超时

`Sandbox.create(request_timeout=...)` 与 E2B 的 `request_timeout` 对齐：它约束客户端
等待创建 HTTP 响应的时长，独立于 `timeout`（沙箱生存时长 TTL）。省略时沿用全局
`http_timeout` / `EBX_HTTP_TIMEOUT`。

```python
sandbox = await Sandbox.create(
    template="python-hello",
    timeout=300,            # 沙箱生存时长（TTL）
    request_timeout=120,    # 仅本次创建请求的 HTTP 等待
)
```

---

## 迁移步骤

1. **替换依赖**：`pip install easy-sandbox`（卸载 `e2b`）
2. **替换导入**：
   - 最小改动：`from e2b import Sandbox` → `from easy_sandbox.compat import Sandbox`
   - 推荐：`from easy_sandbox.api.sandbox import Sandbox`
3. **替换 `Sandbox.kill(id)`**：改为 `Sandbox.kill_by_id(id)`
4. **替换 `get_host()`**：改为 `sandbox.network.get_host()`
5. **`get_upload_url` / `get_download_url`**：改用 `files.write()` / `files.read()`。当前数据面不接受只靠签名的 URL
6. **设置环境变量**：沙箱 API Key 用 `EBX_SANDBOX_API_KEY`。每项设置只有一个变量，见[配置参考](../reference/configuration.md)。

---

## 下一步

- [认证详解](authentication.md) — 了解完整的认证方式
- [SDK 使用指南](sdk-usage.md) — SDK 完整使用方法
- [E2B 兼容性说明](../explanation/e2b-compatibility.md) — 设计背景与原因
