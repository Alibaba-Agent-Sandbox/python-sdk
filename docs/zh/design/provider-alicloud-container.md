# 阿里云智能体沙箱容器版

> 状态：现行记录。这不是极速版 `alicloud-express`。源码在 `awesome-providers/alicloud-container`，用 `abx provider install registry:alicloud-container --yes`（或 `python -m agent_sandbox.providers install registry:alicloud-container --yes`）安装。清单是 `kind = "node"`：Node.js 宿主加载 `provider.mjs`，所以 CLI 和（经本机引擎的）所有 SDK 都能用。自己的说明在 `awesome-providers/alicloud-container/docs/README.md`。

容器版是 ACS 或 ACK 上的 OpenKruise Agents sandbox-manager。它兼容 E2B HTTP，不是极速版的全托管 Endpoint。

```python
sb = await Sandbox.create(
    provider="alicloud-container",
    template="code-interpreter",
    provider_options={
        "domain": "sbx.example.com",
        "api_key": "...",
        "protocol": "native",
    },
)
```

| 项 | 环境变量 |
|---|---|
| 域名 | `ABX_ALICLOUD_CONTAINER_DOMAIN` |
| API 源站，可省略 | `ABX_ALICLOUD_CONTAINER_BASE_URL` |
| API Key，请求头 `X-API-Key` | `ABX_ALICLOUD_CONTAINER_API_KEY` |
| `native` 或 `private` | `ABX_ALICLOUD_CONTAINER_PROTOCOL`，默认 `native` |

`native` 的 API 是 `https://api.{domain}`，数据面是 `https://{port}-{id}.{domain}`。`private` 的 API 是 `https://{domain}/kruise/api`，数据面是 `https://{domain}/kruise/{id}/49983`。不读取极速版的 `ABX_SANDBOX_API_KEY`。

已接入：`sandbox.lifecycle`、`sandbox.timeout`、`sandbox.pause`、`exec.run`、`exec.stream`、`process.manage`、`files.rw`、`code.interpret`、`ports.url`。`pty` 不声明：sandbox-manager 没有 `/terminal`。

`E8004`：暂停、文件监听、文件 URL、模板、存储挂载、VPC、命名命令。官方说明里，预签名上传下载、日志、指标和卷也不在容器版的 E2B 兼容范围内。

单元测试打的是本机假 API。`e2e/test_08_providers.py` 在设置了 `ABX_ALICLOUD_CONTAINER_DOMAIN` 和 `ABX_ALICLOUD_CONTAINER_API_KEY` 时走真实 sandbox-manager；没有这两项时只确认适配器拒绝启动，不会把极速版密钥发出去。这台环境没有 ACS/ACK 集群，所以真实创建没有执行。英文：[provider-alicloud-container.md](../../en/design/provider-alicloud-container.md)。
