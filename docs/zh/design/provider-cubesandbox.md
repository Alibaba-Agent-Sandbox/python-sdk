# CubeSandbox 提供方

CubeSandbox 是目录 Provider，由 CLI 和 Python `ProviderSandbox` 经本机引擎消费。Node.js 服务 HTTP 客户端属于独立入口，不管理云端沙箱。[English](../../en/design/provider-cubesandbox.md)。

插件与操作声明的权威来源是 [awesome-providers/cubesandbox](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/tree/main/cubesandbox)。使用 `abx provider install alibaba-agent-sandbox/awesome-providers//cubesandbox --allow-unpinned --yes` 安装 Git 目录，或通过 Python 的 `python -m agent_sandbox.providers install registry:cubesandbox --yes` 安装。可复现使用应固定经审查的完整提交。

## 精确解释器边界

适配器仅实现 `code.default-context.execute`：同一沙箱默认 Jupyter 上下文中的变量会持久保留。它向 49999 端口的 `/execute` 发送 JSON 字段 `code`、`language` 和可选 `env_vars`，读取缓冲的 NDJSON 结果。调用时显式使用 `await sandbox.run_code("x = 42", mode="default-context")`。

未声明无状态的 `code.execute`、显式上下文创建/执行/列表/重启/删除、实时 `code.stream` 或 `code.results.structured`。传入 context ID 或回调时，在代码发送前拒绝。缓冲结果不等于实时回调；解释器服务缺失时不会降级为 shell。

这一路径与已删除的猜测 Connect 解释器 RPC 不同。Cube 的[官方 Python SDK README](https://github.com/TencentCloud/CubeSandbox/blob/master/sdk/python/README.md) 明确说明 `/execute` 与持久变量。源码映射及回环测试不代表真实 Cube 部署通过。

## 配置与创建

| 字段 | 环境变量 | 默认 |
| --- | --- | --- |
| API 源站 | `ABX_CUBESANDBOX_BASE_URL` | `http://127.0.0.1:3000` |
| 可选 Provider 密钥 | `ABX_CUBESANDBOX_API_KEY` | 未设置 |
| 端口域名后缀 | `ABX_CUBESANDBOX_DOMAIN` | `cube.app` |
| 远程节点代理 | `ABX_CUBESANDBOX_PROXY` | 未设置 |

Provider 密钥与 Express 凭证隔离。进程和文件走 49983 端口的 envd；Jupyter 使用 49999。端口主机名为 `{port}-{sandboxID}.{domain}`。可选代理改变 TCP 连接目标，同时保留虚拟 Host。

```python
from agent_sandbox import ProviderSandbox

sandbox = await ProviderSandbox.create(
    provider="cubesandbox",
    template="YOUR_NATIVE_TEMPLATE_ID",
    provider_options={"base_url": "http://127.0.0.1:3000", "domain": "cube.app"},
    timeout=60,
)
try:
    result = await sandbox.run_code("print(42)", mode="default-context")
finally:
    await sandbox.kill()
```

控制面映射依据 [Cube OpenAPI](https://github.com/TencentCloud/CubeSandbox/blob/master/openapi.yml) 与[官方 SDK](https://github.com/TencentCloud/CubeSandbox/tree/master/sdk/python)。插件分别适配生命周期、超时、暂停/恢复、exec、文件与端口。当前 manifest 是具体操作的权威来源，粗粒度 feature 不能授权另一个工作流。不能从已支持操作推导进程管理、PTY、文件传输、原生模板查询、存储或 VPC。

## 源码准备与证据

CLI 源码准备要求显式兼容的 Dockerfile/构建方案、Docker、可写镜像仓库及 Cube 原生注册条件。保留 FROM、USER、COPY 与 ENTRYPOINT，返回同一 Provider 的原生托管引用；不会把 OCI 镜像当 Cube 模板 ID。Python 不声明 `template.prepare`，只消费已经准备好的引用。

Cube 保持 Beta。单元/回环测试验证映射和失败行为；真实创建需要运行中的 CubeAPI、有效原生模板及节点/运行时环境。本环境尚未完成该原生验收。源码或绑定身份变化需要新的范围证据，历史记录不能证明当前工作流。
