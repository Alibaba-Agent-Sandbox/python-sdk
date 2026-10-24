# 会话持久化

本页的 SDK `LocalSessionStore` 和 `SessionManager` 仍存在；已移除的是 CLI 的 `abx session` 命令组。持久化内容是本地名称与沙箱 ID 等连接信息，不是远端内存或文件快照，不能恢复已删除或到期的实例。`SessionManager.stop()` 会尝试删除实例，但会记录并吞掉删除异常；需要确认资源清理时必须额外核对实际实例状态。

当前 SDK 安装使用[安装指南](install-python.md)。

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（[CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

会话（Session）将沙箱与一个人类可读名称关联，方便在不同终端或时间点反复连接同一个沙箱。

---

## 会话概念

会话是沙箱 ID 与名称的映射关系。通过会话，你可以：

- 用名称代替 sandbox ID 来操作沙箱
- 在不同终端窗口中连接同一个沙箱
- 暂时断开后重新连接

### 会话数据模型

每个会话包含以下信息（`SessionInfo`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `str` | 会话名称 |
| `sandbox_id` | `str` | 关联的沙箱 ID |
| `template` | `str` | 使用的模板 |
| `created_at` | `datetime` | 创建时间 |
| `metadata` | `dict` | 元数据 |

---

## 本地存储

会话默认使用本地文件系统存储，由 `LocalSessionStore` 实现。

### 存储位置

```text
~/.abx/sessions/
├── my-project.json       # 会话 "my-project"
├── my-project.json.lock  # 并发锁文件
├── dev-env.json          # 会话 "dev-env"
└── ...
```

每个会话保存为一个 JSON 文件，文件名由会话名称派生（非字母数字/短横/下划线的字符替换为 `_`）。

### 并发保护

文件读写通过文件锁保护：
- 优先使用 `filelock` 库（如已安装）
- 回退到 POSIX `fcntl` 锁（macOS/Linux）

---

## CLI 使用

> **注意**：`abx session` CLI 命令组已从 CLI 中移除，会话功能现已完全通过 SDK API 提供。以下示例仅供参考，实际使用请通过 Python SDK。

### SDK 替代方案

```python
from agent_sandbox.api.session_manager import SessionManager

manager = SessionManager()

# 启动会话
await manager.start("my-project", template="base", timeout=600)

# 连接会话
sb = await manager.connect("my-project")

# 列出会话
sessions = await manager.list_sessions()

# 停止会话
await manager.stop("my-project")
```

---

## SDK 使用

```python
from agent_sandbox.session.local import LocalSessionStore
from agent_sandbox.models.session import SessionInfo

# 创建存储实例
store = LocalSessionStore()  # 默认 ~/.abx/sessions/

# 保存会话
session = SessionInfo(
    name="my-project",
    sandbox_id="sbx-xxxx",
    template="base",
)
await store.save("my-project", session)

# 加载会话
session = await store.load("my-project")
if session:
    print(f"Sandbox: {session.sandbox_id}")

# 列出所有会话
sessions = await store.list_all()

# 删除会话
await store.delete("my-project")
```

---

## 自定义存储位置

```python
store = LocalSessionStore(base_dir="/path/to/custom/sessions")
```

---

## 下一步

- [CLI 教程](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/cli-tutorial.md) — 完整 CLI 使用教程
- [配置参考](../reference/configuration.md) — 配置文件位置
