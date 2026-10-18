# CubeSandbox 提供方

CubeSandbox 是目录提供方，源码在 `awesome-providers/cubesandbox`，id 是 `cubesandbox`。用 `abx provider install alibaba-agent-sandbox/awesome-providers//cubesandbox --allow-unpinned --yes`（或 `python -m agent_sandbox.providers install registry:cubesandbox --yes`）安装。`Sandbox.create(provider="cubesandbox")` 和 `abx --provider cubesandbox` 用宿主里的 E2B 协议类，加上 `provider.mjs` 里的几处覆盖，访问 CubeAPI。

清单是 `kind = "node"`：Node.js 宿主加载 `provider.mjs`，Python SDK 通过本机引擎（`abx provider engine serve`）使用它。自己的说明在 `awesome-providers/cubesandbox/docs/README.md`。

控制面路径来自 [openapi.yml](https://github.com/TencentCloud/CubeSandbox/blob/master/openapi.yml) 和[官方 Python SDK](https://github.com/TencentCloud/CubeSandbox/tree/master/sdk/python)。单元测试不需要一台正在运行的 CubeSandbox。它在 `127.0.0.1` 上用本地 TCP 服务回答 `POST /sandboxes`。

真实创建需要 `127.0.0.1:3000` 上有 CubeAPI。一键安装在这台机器上停在预检：根文件系统是 overlay，不是 `/data/cubelet` 要求的 XFS，而且 init 是 tini，不是 systemd。端口 3000 没有进程，所以真实创建没有执行。

## 配置

| 字段 | 类型 | 环境变量 | 默认 |
|---|---|---|---|
| `base_url` | url | `ABX_CUBESANDBOX_BASE_URL` | `http://127.0.0.1:3000` |
| `api_key` | 密钥，可选 | `ABX_CUBESANDBOX_API_KEY` | 不设置 |
| `domain` | 字符串 | `ABX_CUBESANDBOX_DOMAIN` | `cube.app` |

默认源站用 3000 端口，因为 Cube Python SDK 的 README 把 `CUBE_API_URL` 写成 `http://127.0.0.1:3000`。用 `provider_options={"base_url": "..."}` 覆盖。这个值是 CubeAPI 的源站，不带路径前缀。请求打到 `/sandboxes`，不是 `/cubeapi/v1/sandboxes`。

设置了 `api_key` 时，客户端发送 `X-API-Key`。没设置时不发送认证头。本地 CubeAPI 允许这样。这个提供方不读 `ABX_SANDBOX_API_KEY`。那个变量是阿里云极速版的密钥。

`domain` 是端口主机名 `{port}-{sandboxID}.{domain}` 的后缀。

```python
from agent_sandbox import ProviderSandbox as Sandbox

sb = await Sandbox.create(
    provider="cubesandbox",
    provider_options={
        "base_url": "http://127.0.0.1:3000",
        "api_key": "...",
        "domain": "cube.app",
    },
    template="base",
    timeout=60,
)
```

## 这个适配器会调用的能力

| 能力 | 共享协议发出的 HTTP | Cube 上是否有 |
|---|---|---|
| `sandbox.lifecycle` | `POST /sandboxes`、`GET /sandboxes`、`GET /sandboxes/{id}`、`DELETE /sandboxes/{id}`、`GET /v2/sandboxes` | OpenAPI 和 SDK 都有 |
| `sandbox.timeout` | `POST /sandboxes/{id}/timeout` | OpenAPI 和 SDK 都有 |
| `sandbox.pause` | `POST /sandboxes/{id}/pause` 和 `POST /sandboxes/{id}/resume` | OpenAPI 和 SDK 都有 |
| `exec.run`、`exec.stream` | envd 端口 49983 上的 `POST /process.Process/Start` | Cube Python SDK |
| `files.rw` | envd 的 `GET /files`、`POST /files`，以及 `POST /filesystem.Filesystem/{Stat,ListDir,MakeDir,Remove,Move}`。用户名默认 `root` | Cube Python SDK |
| `files.watch` | envd `POST /filesystem.Filesystem/WatchDir` | Cube Python SDK 的 `files.watch_dir` |
| `code.interpret` | envd Connect `POST /code.CodeInterpreter/Execute` | 不是 Cube SDK 的路径，见下 |
| `ports.url` | 本地计算 `{port}-{sandboxID}.{domain}` | Cube SDK 的 `get_host` |

`connect` 先发 `POST /sandboxes/{id}/connect`（Cube 用它恢复暂停的沙箱）。这个路径返回 4xx 时再退回 `GET /sandboxes/{id}`。进程和文件请求在调用方没写用户时带 `root`，因为 Cube envd 会拒绝空用户。

`run_code` 发到 `http://49999-{id}.{domain}/execute`，正文是 `code`、`language`、`env_vars`，响应按 ndjson 读。不在节点上时设置 `ABX_CUBESANDBOX_PROXY=主机:80`，TCP 打到代理，Host 仍是虚拟主机名。

## 会抛出 E8004 的调用

这些不在 `features` 里。`feature_gate` 在发出 HTTP 之前拒绝对应的协议方法。`Provider.require` 以同样的方式拒绝能力 id。

| 能力 | 被拒绝的内容 |
|---|---|
| `files.transfer` | 仅靠签名或 token 的文件 URL |
| `pty` | 交互终端 |
| `templates.read`、`templates.build` | 模板列表和构建 |
| `sessions` | SandboxServer 上的具名命令 |
| `process.manage` | 进程列表、标准输入和信号。`exec.run` 仍然可以启动命令 |
| `ports.domain` | 单独的域名式能力 id。端口主机名仍然使用 `domain` |
| `storage.mount` | 通用挂载能力 |
| `network.vpc` | VPC |

## 扩展

OpenAPI 里有三项不属于 18 个固定能力、又是 Cube 自己的能力。它们登记为 `implemented=False`、`when="sandbox"`。这个适配器不会调用它们。

| Id | OpenAPI |
|---|---|
| `volume.mounts` | `NewSandbox.volumeMounts`、`/volumes` |
| `network.policy` | 创建体里的 `network`，以及 `PUT /sandboxes/{id}/network` |
| `distribution.scope` | `NewSandbox.distributionScope` |

`extensions_for` 在没有沙箱 id 时返回空。传入沙箱 id 后，这三项都会出现，因为 `when` 是 `sandbox`。它们的 `implemented` 是 false，所以 `require_extension` 抛出 `E8004`。没有沙箱时，`describe()["extensions"]` 仍然列出它们。

下面这些 OpenAPI 操作也存在，但没有登记。它们不是上面那三项 Cube 专有能力，这个适配器也不调用：`GET /health`、`POST /sandboxes/{id}/refreshes`、`GET /sandboxes/{id}/logs`、`POST /sandboxes/{id}/snapshots`、`POST /sandboxes/{id}/rollback`、`GET /snapshots`，以及 `/templates` 构建接口。
