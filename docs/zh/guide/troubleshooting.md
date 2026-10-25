# 常见问题（FAQ）

当前 SDK 安装使用[安装指南](install-python.md)。

> **说明：** 本页出现的 `abx` 命令由 `cli` 仓库中的 Node.js CLI 提供（[CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md)）。CLI 专属文档（CLI 设计、教程、参考）也在该仓库；本仓库记录 Python SDK（`agent-sandbox-client`）与容器侧运行时（`agent-sandbox-server`）。

---

## 连接超时

### 症状

```text
[E5001] Failed to connect to sandbox service
  Suggestion: Check network connectivity and firewall rules.
```

### 排查

1. **检查网络**：确认可以访问 `api.cn-hangzhou.e2b.fc.aliyuncs.com`
   ```bash
   curl -I https://api.cn-hangzhou.e2b.fc.aliyuncs.com
   ```

2. **检查超时配置**：增大 HTTP 超时
   ```bash
   abx config set http_timeout 60
   ```

3. **检查代理**：如果在代理环境中，确保 `https_proxy` 正确配置

4. **检查区域**：确认区域设置正确
   ```bash
   abx config get region
   ```

---

## 认证失败

### E1001 — API Key 无效或缺失

```text
[E1001] API key cannot be empty
  Suggestion: Check your ABX_SANDBOX_API_KEY environment variable or pass sandbox_api_key.
```

**解决**：
```bash
# 检查配置状态
abx config get sandbox_api_key

# 重新设置 API Key
abx config set sandbox_api_key your-api-key

# 或设置环境变量
export ABX_SANDBOX_API_KEY="your-api-key"
```

### E1003 — AK/SK 凭证无效

```text
[E1003] AccessKey ID and Secret cannot be empty
```

**解决**：确保同时设置了 AK ID 和 AK Secret：
```bash
export ALICLOUD_ACCESS_KEY_ID="your-ak-id"
export ALICLOUD_ACCESS_KEY_SECRET="your-ak-secret"
```

### E1002 — Token 过期

```text
[E1002] envdAccessToken not available. Sandbox may not be created or connected.
```

**解决**：检查系统时钟是否准确。重新连接获取有效 envd token，或检查显式配置的自定义交换；API Key 不会被自动创建或刷新。

---

## 模板不存在

### E2001 — TemplateNotFoundError

```text
[E2001] Template 'my-template' not found
  Suggestion: Run 'abx template list' to see available templates.
```

**解决**：

1. 检查模板名称拼写
2. 确认模板已安装：
   ```bash
   abx template install owner/repo
   ```
3. 使用默认模板测试：
   ```bash
   abx create base
   ```

### E2009 — SandboxNotFoundError

```text
[E2009] Sandbox 'sbx-xxxx' was not found.
```

对该 ID 调用 `Sandbox.connect()`、`get_info()`、`set_timeout()`、`pause()` 或 `resume()` 时，平台返回了 HTTP 404。

**解决**：检查 ID 拼写，运行 `abx list` 查看运行中的沙箱。已销毁或已过期的沙箱无法重新连接，请重新创建。对未知 ID 调用 `kill()` 仍保持幂等，不会抛出异常。

---

## 能力不支持（E3004）

### 症状

目录显示所选路径未满足，或 Provider 返回 E8004 并指出 `code.execute`、`code.context.execute` 等具体操作。服务端被策略关闭的 HTTP 端点则可能返回 `endpoint_disabled` / E9003（也属于 E3004）。

### 解释

模板提供的软件服务、项目 Provider 适配器、具体客户端入口与实例当前环境是不同层。缺少项目适配器操作不代表平台原生 API 没有该能力；缺少统一解释器调用也不代表模板的应用 HTTP 不能用。Beta 成熟度和当前路径测试证据分别记录。

### 解决

1. 确认具体工作流、消费入口和失败条件责任层；使用 [spec4 清单](../reference/template-yaml-spec.md)，不能补旧 `capabilities` 或 `tested_on`。
2. 适配器不支持时实现/安装对应操作，或显式选择已支持的工作流。无状态、默认持久上下文、指定上下文和实时流不能互相冒充。
3. 对应用服务，使用 `async with await sandbox.application_client(9000, token=application_token)` 独立解析端点，检查实际监听、协议版本、网关配置及应用令牌。
4. HTTP 401 不做匿名重试；解释器 404 不转 shell。需要 shell 时显式调用命令 API。
5. 服务端策略另外控制九个端点组；`core` 始终开启，`dev_tools`、`browser`、`agents` 默认关闭。检查 `server:`、实际加载的 policy 和环境配置，而不是模板的旧能力标签。

见[显式模板工作流](template-workflows.md)和[模板服务器 HTTP API](template-server-api.md)。

---

## 配额超限

### E2002 — QuotaExceededError

```text
[E2002] Sandbox quota has been exceeded
  Suggestion: Destroy idle sandboxes or request a quota increase.
```

**解决**：

```bash
# 查看运行中的沙箱
abx list --status running

# 销毁不需要的沙箱
abx kill sbx-xxxx

# 批量销毁
abx kill --all --yes
```

---

## 命令执行超时

### E3001 — CommandTimeoutError

```text
[E3001] Command execution timed out
  Suggestion: Increase the timeout parameter or check if the command is hanging.
```

**解决**：

```python
# SDK 中增加超时
result = await sandbox.commands.run("long-command", timeout=300)

# CLI 中增加超时
abx exec sbx-xxxx "long-command" --timeout 300
```

---

## 构建与部署相关

构建、推送、部署的错误（`E7xxx` 错误码，以及 `abx create` / `abx template scaffold` 缺少 LLM Key）由 `abx` CLI 抛出，不属于这个 SDK。见 CLI 的排障指南和[构建与部署](build-and-deploy.md)。

---

## 文件操作

### E4001 — 文件未找到

```python
# 先检查文件是否存在
exists = await sandbox.files.exists("/path/to/file")
if not exists:
    print("文件不存在")

# 列出目录内容
entries = await sandbox.files.list("/home/user")
```

### E4002 — 权限被拒绝

检查文件权限。沙箱默认用户为 `user`，可在命令中指定 `user` 参数。

---

## 安装问题

### pip install 失败

```bash
# 确保使用正确的包名
python -m pip install --index-url https://pypi.org/simple "agent-sandbox-client==0.4.0a3"

# 如果遇到依赖冲突
python -m pip check
```

### Python SDK 未找到

确认 Python 的 bin 目录在 PATH 中：

```bash
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'))"
# 或
python -m pip show agent-sandbox-client
```

---

## 下一步

- [认证详解](authentication.md) — 认证配置
- [配置参考](../reference/configuration.md) — 所有配置项
- [错误码参考](../reference/error-codes.md) — 完整错误码列表

---

## 相关：abx CLI

CLI 特有的问题（找不到 `abx`、`abx deploy` 没有 Dockerfile、部署步骤长时间无输出、无效的快捷方式目标、`abx template scaffold --adopt` 确认提示）见 CLI 仓库：[故障排查（CLI）](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/guide/troubleshooting.md)。
