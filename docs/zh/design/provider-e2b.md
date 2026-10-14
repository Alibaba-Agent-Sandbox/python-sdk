# E2B 提供方

E2B 是目录提供方，源码在 `awesome-providers/e2b`，id 是 `e2b`。用 `abx provider install alibaba-agent-sandbox/awesome-providers//e2b --allow-unpinned --yes`（或 `python -m agent_sandbox.providers install registry:e2b --yes`）安装。`Sandbox.create(provider="e2b")` 和 `abx --provider e2b` 用宿主里的 E2B 协议类访问 E2B 公开 API。

它不是随 SDK 编译进去的。清单是 `kind = "node"`：`provider.mjs` 由 Node.js 宿主加载，Python SDK 通过本机引擎（`abx provider engine serve`）使用它。自己的说明在 `awesome-providers/e2b/docs/README.md`。

单元测试不访问 `https://api.e2b.dev`。它在 `127.0.0.1` 上用本地 TCP 服务回答 `POST /sandboxes`。

真实访问 E2B 需要设置 `ABX_E2B_API_KEY`。没有这个变量时，测试确认 `Sandbox.create(provider="e2b")` 在发出请求前抛出 `InvalidAPIKeyError`。极速版的 `ABX_SANDBOX_API_KEY` 不会被送到 `api.e2b.dev`。这台环境没有单独的 E2B 密钥，所以真实创建没有执行。

英文页：[provider-e2b.md](../../en/design/provider-e2b.md)。

## 配置

| 字段 | 类型 | 环境变量 | 默认 |
|---|---|---|---|
| `base_url` | url | `ABX_E2B_BASE_URL` | `https://api.e2b.app` |
| `domain` | 字符串 | `ABX_E2B_DOMAIN` | `e2b.app` |
| `api_key` | 密钥 | `ABX_E2B_API_KEY` | 不设置 |

这三个名字也可以放在 `provider_options` 里。`Sandbox.create(api_url=...)` 不会改这个源站。解析器读的是 `provider_options["base_url"]`。

设置了密钥时，客户端发送请求头 `X-API-Key`。没有 `ABX_E2B_API_KEY` 时抛出 `InvalidAPIKeyError`，错误信息里写明 `ABX_E2B_API_KEY`。这个提供方不读 `ABX_SANDBOX_API_KEY`（阿里云极速版的密钥），也不读 `E2B_API_KEY`（本产品拒绝的旧名字）。

`domain` 是 `https://{port}-{sandboxID}.{domain}` 的后缀。envd 端口是 49983。创建响应里没有 `region` 时保持未知（空字符串），不会落成 `cn-hangzhou`。

当前 E2B SDK 用 `https://api.e2b.app`，域名是 `e2b.app`。数据面主机名是 `https://{port}-{sandboxID}.e2b.app`。`https://api.e2b.dev` 是旧源站；账号还在那边时同时设置 `ABX_E2B_BASE_URL` 和 `ABX_E2B_DOMAIN`。

```python
from agent_sandbox import Sandbox

sb = await Sandbox.create(
    provider="e2b",
    provider_options={
        "base_url": "https://api.e2b.app",
        "domain": "e2b.app",
        "api_key": "...",
    },
    template="base",
)
```

## 这个适配器会调用的能力

创建是 `POST /sandboxes`，正文包含 `templateID`、`timeout`、`metadata`、`envVars`。其余由共享协议客户端发送。

| 能力 | 共享协议做的事 |
|---|---|
| `sandbox.lifecycle` | `POST /sandboxes`、`GET /sandboxes`、`GET /sandboxes/{id}`、`DELETE /sandboxes/{id}`、`GET /v2/sandboxes` |
| `sandbox.timeout` | `POST /sandboxes/{id}/timeout` |
| `sandbox.pause` | `POST /sandboxes/{id}/pause` 和 `POST /sandboxes/{id}/resume` |
| `exec.run`、`exec.stream` | envd `POST /process.Process/Start` |
| `process.manage` | envd 的进程列表、标准输入和信号 |
| `files.rw` | envd 的读、写、列目录、移动和删除 |
| `files.watch` | envd `WatchDir`。已声明，不会因为未声明而返回 `E8004` |
| `code.interpret` | envd `POST /code.CodeInterpreter/Execute` |
| `ports.url` | 本地计算 `https://{port}-{sandboxID}.{domain}` |

## 会抛出 E8004 的调用

这些 id 不在 `features` 里。`feature_gate` 在发出 HTTP 之前拒绝未声明能力对应的协议方法。`Provider.require` 以同样的方式拒绝能力 id。

| 能力 | 被拒绝的内容 |
|---|---|
| `pty` | 交互终端。公开 envd 没有 `/terminal` |
| `files.transfer` | 仅靠签名或 token 的文件 URL |
| `templates.read` | 模板列表和查询 |
| `templates.build` | 模板构建和发布 |
| `ports.domain` | 单独的域名式能力 id。端口主机名仍然使用 `domain` |
| `storage.mount` | 存储挂载 |
| `network.vpc` | VPC |
| `sessions` | SandboxServer 上的具名命令 |

`files.watch` 已声明。`files.watch` / `watch_dir` 不会因为未声明而抛出 `E8004`。

## 扩展

`extensions` 是空的。18 个固定能力之外没有登记扩展。

E2B 公开 API 还有这些接口，这个适配器不调用，也不登记成扩展：沙箱日志（`GET /v2/sandboxes/{sandboxID}/logs`）、指标（`GET /sandboxes/{sandboxID}/metrics`）、快照、fork、更新网络、卷、模板标签、团队密钥、事件和 webhook。卷和未声明的 `storage.mount` 重叠。模板列表和构建与 `templates.read`、`templates.build` 重叠。
