# 未实测提供方的可用性审查

> 状态：2026-10-14。OpenSandbox 和阿里云极速版已经有真实调用。这里审查的是还没有后端的三个：CubeSandbox、E2B、容器版。它们的源码在 `awesome-providers/`，安装方式见该目录的 `docs/zh/install.md`。审查对照的是当前官方 SDK 和 OpenAPI，不是单元测试里的假服务器。同一份结论也写在 `awesome-providers/docs/zh/catalog.md`。

三个目录适配器都复用 E2B 形状的 `SandboxProtocol`。控制面路径（`POST /sandboxes`、`templateID`、`X-API-Key`、`DELETE`、`POST /timeout`、`POST /pause`）和官方文档一致，可以在拿到环境之后直接打。下面是不改就会在真实环境里走错的地方，以及已经改过的部分。

## 结论

| 提供方 | 逻辑上能否用 | 拿到资源后第一件事 |
|---|---|---|
| E2B | 可以。创建、执行、文件、端口、暂停所走的 HTTP 和当前 OpenAPI 一致 | 设置 `ABX_E2B_API_KEY`，模板用 `base` |
| CubeSandbox | 可以完成创建、命令、文件、暂停和目录监听。`run_code` 打到 Jupyter `:49999/execute` | API 在 `:3000`，`ABX_CUBESANDBOX_DOMAIN=cube.app`，模板 id 用集群里真实存在的那个，不要假设有 `base` |
| 容器版 | 原生协议可以。私有协议的数据面 URL 只在创建、连接、查询时补全 | `ABX_ALICLOUD_CONTAINER_DOMAIN` 和 `ABX_ALICLOUD_CONTAINER_API_KEY`。模板按集群镜像，文档示例是 `code-interpreter` |

三个都不会读取 `E2B_API_KEY`。没有自己的密钥时，E2B 和容器版在发请求之前拒绝。

## 已经对齐的差异

这些是对照官方实现后改过的，单元测试锁住了新行为。

| 问题 | 原来会怎样 | 现在 |
|---|---|---|
| E2B 默认域名 `e2b.dev` | 数据面主机名 `49983-{id}.e2b.dev` 不是当前 SDK 的默认域名。当前 SDK 的域名是 `e2b.app`，API 是 `https://api.e2b.app` | 默认改为 `api.e2b.app` / `e2b.app`。旧账号用环境变量指回 `e2b.dev` |
| Cube 默认域名 `localhost` | envd 会去连 `49983-{id}.localhost`，到不了 CubeProxy。官方默认是 `cube.app` | 默认 `cube.app` |
| `connect` 只发 GET | Cube 和当前 E2B 用 `POST /sandboxes/{id}/connect` 恢复暂停的沙箱。GET 只能看状态 | 三个适配器都先 POST，4xx 再 GET |
| Cube 进程和文件不带用户 | 官方 SDK 写明 envd 会拒绝空用户，并默认发 `root` | 进程 `user`、文件 `username`，以及 `Authorization: Basic` 都是 `root` |
| Cube 没有 `envdAccessToken` | 客户端在发请求前抛 `TokenExpiredError` | 没有 token 时不发 `X-Access-Token`，请求继续 |
| Cube 数据面用了 https | 会去连 443。CubeProxy 的 HTTP 在 80，主机名里的 `49983` 只是路由前缀 | 补成 `http://49983-{id}.{domain}`。响应里的 `domain` 优先于配置 |
| Cube `resume` 没有 JSON 正文 | Axum 对缺 body 返回 422 | `POST /resume` 发送 `{}` |
| Cube `run_code` 打到 envd 的 CodeInterpreter | 官方是 Jupyter `:49999` 的 `POST /execute` | 改打这个 URL，读 ndjson |
| 进程 Start 的 Connect 正文 | Cube envd 把原始 JSON 的前 5 个字节当成帧头 | Cube 的 envd 请求加上 5 字节帧和 `Connect-Protocol-Version: 1`。极速版仍用原来的裸 JSON |
| `state: pausing` | 解析失败 | `SandboxStatus` 接受 `pausing` |
| Cube 目录监听被 E8004 | 官方 SDK 有 `files.watch_dir`，走的是同一套 envd | `files.watch` 改为已声明 |

## 拿到资源后仍然要眼见为实

这些不是猜出来的拒绝，而是官方接口和本适配器还没接上的部分。有环境之后按这个顺序看。

| 提供方 | 调用 | 预期 |
|---|---|---|
| Cube | `run_code` 两次，第二次读第一次的变量 | 要看 Jupyter 是否把同一次 `/execute` 之外的状态留在内核里。请求已经发到 `:49999/execute` |
| Cube | 不在节点上 | 设置 `ABX_CUBESANDBOX_PROXY=主机:80`。TCP 打到代理，Host 仍是 `49983-{id}.cube.app` |
| Cube | `Sandbox.list(status=...)` | `GET /sandboxes` 忽略 `status` 和 `offset`。过滤要等改打 `GET /v2/sandboxes` |
| E2B | `get_terminal` | OpenAPI 没有单独的 PTY 路径。envd WebSocket `/terminal` 需要实测。失败时不要改成静默 E8004，先看状态码 |
| E2B | `Sandbox.connect` 到一个暂停的沙箱 | 应先打到 `POST /connect` 并恢复。`POST /resume` 在 OpenAPI 里标了 deprecated，`pause()` 之后的 `resume()` 仍走那条旧路径 |
| 容器版 native | 创建响应里没有 `envdUrl` | SDK 补 `https://49983-{id}.{domain}`。如果集群的 envd 端口不是 49983，命令会连错主机 |
| 容器版 private | 创建 | 数据面是 `https://{domain}/kruise/{id}/49983`。端口 URL 是 `https://{domain}/kruise/{id}/{port}` |
| 容器版 | `get_terminal` | 未声明，E8004。sandbox-manager 没有 `/terminal`，PTY 要走带 `pty` 字段的进程启动 |
| E2B | `get_terminal` | 同样未声明。公开 envd 用 `process.Process/Start` 的 `pty` 字段，不是 WebSocket `/terminal` |
| E2B | 会读标准输入的命令 | `Start` 现在带 `stdin: false`。不带这个字段时，`cat` 会一直等到 HTTP 超时 |

## 资源到了之后怎么跑

```bash
cd python-sdk/e2e
python -m pytest test_08_providers.py -s -ra
```

Cube 需要 `127.0.0.1:3000` 或 `ABX_CUBESANDBOX_BASE_URL`。E2B 需要 `ABX_E2B_API_KEY`。容器版需要 `ABX_ALICLOUD_CONTAINER_DOMAIN` 和 `ABX_ALICLOUD_CONTAINER_API_KEY`。缺哪一项，对应测试跳过，不会把另一家的密钥发出去。
