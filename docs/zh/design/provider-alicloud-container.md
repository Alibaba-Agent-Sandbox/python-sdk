# 阿里云智能体沙箱容器版

容器版是 ACS 或 ACK 上的 OpenKruise Agents sandbox-manager，与 Express 分属不同 Provider，使用各自的域名、凭证和运行时条件。CLI 与 Python `ProviderSandbox` 经本机引擎使用[目录适配器](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/alicloud-container)。Node.js 服务 HTTP 客户端不管理此 Provider。[English](../../en/design/provider-alicloud-container.md)。

使用 `abx provider install alibaba-agent-sandbox/awesome-providers//alicloud-container --allow-unpinned --yes` 或 `python -m agent_sandbox.providers install registry:alicloud-container --yes` 安装。可复现使用应固定经审查的完整提交。

## 精确解释器边界

适配器仅实现持久的 `code.default-context.execute`：向 49999 端口的 Jupyter `POST /execute` 发送 `code`、`language` 与可选 `env_vars`，读取缓冲的 NDJSON。它是明确的独立适配路径，不是已删除的猜测 envd Connect 解释器 RPC。调用时显式选择 `mode="default-context"`。

未声明无状态执行、公共上下文管理、实时回调或结构化结果支持。传入 context ID 或回调时，代码发送前即拒绝。缺少运行时或路由时不会降级为 shell。模板提供 Python 服务，不代表所选工作流必须使用这项解释器操作。

## 配置与创建

| 设置 | 环境变量 |
| --- | --- |
| 域名 | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| 可选 API 源站 | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| Provider 密钥，请求头 `X-API-Key` | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| `native` 或 `private` | `ABX_ALICLOUD_CONTAINER_PROTOCOL`，默认 `native` |

Native API 为 `https://api.{domain}`，端口地址为 `https://{port}-{id}.{domain}`。Private API 为 `https://{domain}/kruise/api`；envd 绑定使用 `https://{domain}/kruise/{id}/49983`，Jupyter handler 选择 49999 端口。不继承 Express 密钥。

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(
    provider="alicloud-container",
    template="YOUR_NATIVE_SANDBOXSET",
    provider_options={
        "domain": "sbx.example.com",
        "api_key": "REPLACE_ME",
        "protocol": "native",
    },
)
try:
    result = await sandbox.run_code("print(42)", mode="default-context")
finally:
    await sandbox.kill()
```

Manifest 分别声明生命周期、超时、暂停/恢复、exec、进程管理、文件与端口。具体 operation 列表决定工作流支持情况，不能推导 PTY、文件监听/传输、模板查询、存储挂载、VPC 或命名命令服务可用。命名命令应用工作流需要真实匹配的 HTTP 服务与绑定。

## 源码准备与证据

CLI 准备流程构建、推送显式兼容的源码/构建方案，再将配置的基础 SandboxSet 中运行时注入、卷、探针复制到本轮自有的零预热池资源。它不修改基础对象，也不改写 Dockerfile 指令。该流程需要 Docker/镜像仓库访问及 Kubernetes 权限，普通 sandbox-manager 密钥本身不能登记 SandboxSet。Python 只消费已准备的引用，不声明 `template.prepare`。

容器版保持 Beta。本地假 API 测试验证映射与拒绝行为；真实创建需要 ACS/ACK 部署、有效的原生 SandboxSet、域名/密钥与运行时服务。本环境尚未完成原生验收。源码注册、应用 HTTP 与解释器证据范围不同，成功的 mock 或历史回执不能证明当前工作流。
