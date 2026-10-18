# Provider 引擎：方案与对抗验证

> **状态：已退役的 Python gRPC 历史设计。** 内置提供方现使用[直接 HTTP](builtin-data-plane.md)，目录 Node 插件使用独立的 [Node 引擎](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/zh/reference/engine-api.md)。下文示例是历史记录，不再是受支持的命令。

状态：方案。2026-10-14 由三方对抗得出。试验切片见 [provider-engine.md](provider-engine.md)。英文对照：[provider-engine-plan.md](../../en/design/provider-engine-plan.md)。

那次评审当时已经落地的行为和下面的方案不一样：gRPC 引擎只创建 `alicloud-express`。OpenSandbox 当时是目录插件 `awesome-providers/opensandbox`，HTTP 留在插件进程里。目录提供方现在作为 `node` 模块跑在 Node 引擎上。

三方：

| 角色 | 结论 |
|---|---|
| 方案 | 一个本机引擎。SDK 只拨 Unix socket 上的 gRPC。引擎握着 HTTP、SSE、WebSocket。内置阿里云极速版和 OpenSandbox 都是引擎内适配器。 |
| 攻击 | 现有切片有 4 个 blocker：空凭证会借用引擎进程的密钥、守护线程加无条件 unlink、任意 URL 的 SSRF、创建之后命令和文件仍绕过引擎。 |
| 实测 | `pytest` 13 通过。`Exec`/`Terminal` 会连调用方给的地址。umask 0 时套接字是 `0777`，`nobody` 能调用 `Exec`。第二个进程会把正在监听的套接字 inode 换掉。 |

**判定：现在的切片不能当作阿里云极速版的生产路径。** 下面是收掉这些失败之后的方案。

## 1. 决定

SDK（Python、CLI，以及以后的其他语言）只认识三种调用：一次请求、一条服务端流、一条双向流。后端的 HTTP、SSE、WebSocket 只出现在引擎里。

`exec` 插件的标准输入输出不再承载文件、SSE 或终端。`rest` 只作为引擎内部的 HTTP 适配器，给协议已经对得上的后端。OpenSandbox 写成引擎内适配器，不再启动 `node ./provider.mjs`。

沙箱内的 server SDK 不选择 provider，不启动引擎。

## 2. 进程

- 一个套接字一个进程。默认 `~/.abx/engine.sock`。`ABX_ENGINE_SOCKET` 必须是绝对路径。拒绝 `host:port`。路径超过 108 字节就失败，不改去听 TCP。
- `~/.abx` 为 `0700`。bind 前 `umask 077`，bind 后套接字 `chmod 0600`。客户端看到 group/other 可访问就拒绝连接。
- 先 `Health`。通了就附着，不删除套接字。不通才在文件锁里拉起 `python -m agent_sandbox.engine`。禁止先 unlink 再 bind。
- 生产路径是脱离的子进程，不是随父进程死亡的守护线程。pytest 或 `ABX_ENGINE_INPROCESS=1` 才在进程内启动，以便现有单测继续 patch `SandboxProtocol`。
- 空闲 `ABX_ENGINE_IDLE_SECONDS`（默认 900）后退出。崩溃后只对幂等 RPC 重试一次（`Health`、`Get`、`List`、`Kill`）。`Create` 和所有流不自动重试。
- `Health.protocol` 必须是 `abx.engine.v1`。对不上就拒绝，并提示重启引擎。

## 3. 协议

SDK 把已经解析好的配置放进 `Creds`。引擎不读 `config.toml`，也不读自己的环境变量来补密钥。缺 `api_key` 或后端地址就失败。

凭证只在 RPC 内存和这条套接字上。`envd_access_token` 与 execd 的 header 由引擎保存，不放进返回给 SDK 的状态里。之后的数据面 RPC 只带 `sandbox_id`。

一元：`Health`、`Create`、`Connect`、`Get`、`List`、`Kill`、`SetTimeout`、`Pause`、`Resume`、`PortUrl`、`ExecRun`、文件元数据、`ProcessSignal`、`CodeExecute`。

服务端流：`ExecStart`（原始字节，不是 base64）、`FileRead`（64 KiB 一块）、`WatchDir`。

双向流：`FileWrite`（第一帧带路径，之后是数据，写完一块再读下一块）、`Terminal`（`OPEN` / `DATA` / `RESIZE` / `SIGNAL` / `CLOSE` / `EXIT`）。

取消 RPC 时引擎关掉对应的 HTTP 流或 WebSocket。队列有上限（4），写满就停住上游读取。

错误带 trailer `abx-error-code`，Python 映射回原来的异常（401 → `E1001`，沙箱 404 → `E2009`，超时 → `E3001`）。不用 `or` 把 `0` 当成「没填」。零和缺省用 `optional` 分开。

现有的 `Exec(sse_url)` 和「第一帧自带 `websocket_url` 的 Terminal」只保留到迁移最后一步，并且只接受回环地址。生产调用不准传 URL。

## 4. 阿里云极速版

适配器调用现有的 `SandboxProtocol`、`ProcessProtocol`、`FilesystemProtocol`，不新写一套 JSON。

- 创建仍是 `POST /sandboxes`，body 仍由 `SandboxConfig.to_create_payload()` 生成。
- 命令流走 envd 的 Connect（`application/connect+json`）。引擎解码一次，SDK 收到原始字节。
- 文件字节走 envd 的 `/files`，64 KiB 一块，不进 JSON。
- 终端把 `envd_url` 换成 `wss`，路径 `/terminal`。引擎握着这条 WebSocket。

`Sandbox.create` / `connect` 在内置 provider 上只向引擎发 RPC。返回的对象不再自己建一条绕过引擎的 `HttpClient` 去跑命令和文件。直接注入 mock protocol 的单测不经过引擎。

## 5. OpenSandbox

模块在引擎内。不启动已安装的 Node 插件，文件内容不以 `content_b64` 离开引擎。

生命周期走 OpenSandbox 的 HTTP。命令走 execd 的 SSE。文件走 execd 的上传下载。终端走 execd 的 WebSocket，数据帧带 `0x00` 前缀，由引擎剥掉后再交给 SDK。

第一刀明确返回 `E8004` 的：文件 watch、签名 URL、stdin、code、模板构建、按名字列进程。

## 6. 安装库

`~/.abx/providers` 保留。`rest` 仍可安装，引擎读 manifest 后发 HTTP，不执行插件目录里的文件。

新的 `exec` 安装直接失败，错误码 `E8010`，消息固定为：`exec providers cannot carry files, SSE or WebSocket; install refused`。已经装上的标 `disabled`，选中时失败，不启动其进程。`opensandbox` 是内置 id，同名安装目录被忽略。

## 7. 迁移顺序

每一步之后，现有三个引擎测试保持通过，云上创建请求的 body 仍由 `to_create_payload()` 生成。

1. `Health`、文件锁、`0700`/`0600`、禁止 unlink 活着的套接字。旧 RPC 行为不变。
2. 旧的 `Exec` / `Terminal` 只允许回环 URL。
3. 加上新 RPC，旧字段保持默认值。
4. 内置生命周期全部进引擎。
5. 内置命令、文件、终端进引擎。`tests/test_protocol` 仍直接测协议类。
6. CLI 改拨同一个套接字。
7. OpenSandbox 适配器。单测断言没有 `content_b64`。
8. 拒绝新的 exec 安装。
9. 删掉按 URL 出站的旧 RPC，把三个测试改到新 RPC 上，断言保持原意。

## 8. 第一刀不做

不实现 Go/Java SDK，不交付非 Python 的引擎二进制，不做 Windows 命名管道。不把沙箱内 9000 端口的 server SDK 代理进引擎。不自动恢复断开的终端流。不让引擎读配置文件。不在这一刀删除 EPP 源文件，只停止调用并拒绝安装。
