# OpenSandbox 提供方

> 状态：现行记录，2026-10-14。机器可读的同一张表是 `awesome-providers/opensandbox/provider.mjs` 里的 `FEATURES` 和方法表。
>
> 第 1 节到第 8 节的调研，以及 2026-10-13 的 exec 插件实测，在 [provider-opensandbox-research.md](../../en/archive/provider-opensandbox-research.md)。那些页描述的 Node `provider.mjs` 就是现在的实现。

OpenSandbox 是目录提供方，源码在 `awesome-providers/opensandbox`，id 是 `opensandbox`。用 `abx provider install registry:opensandbox --yes`（或 `python -m agent_sandbox.providers install registry:opensandbox --yes`）安装。`Sandbox.create(provider="opensandbox")` 和 `abx --provider opensandbox` 在插件进程里打 OpenSandbox 的 HTTP、execd 的 SSE 和 WebSocket。

清单是 `kind = "exec"`：一个无依赖的 Node 程序（`provider.mjs`），宿主启动它并用 EPP/1 通信。终端需要 Node 22+ 的全局 `WebSocket`。没安装时 `abx --provider opensandbox` 是 `E8001`。自己的说明在 `awesome-providers/opensandbox/docs/README.md`。

配置：

| 项 | 环境变量 |
|---|---|
| 生命周期地址，不带 `/v1` | `ABX_OPENSANDBOX_BASE_URL`，别名 `OPENSANDBOX_BASE_URL`。默认 `http://127.0.0.1:8080` |
| 请求头 `OPEN-SANDBOX-API-KEY` | `ABX_OPENSANDBOX_API_KEY`，别名 `OPEN_SANDBOX_API_KEY`、`OPENSANDBOX_API_KEY` |

`template="base"` 使用镜像 `python:3.12-slim`，入口是 `tail -f /dev/null`。带 `:` 或 `/` 的模板名按镜像 URI 使用。

下面三张表来自 2026-10-14 的真实调用：本机 OpenSandbox 1.1.1（`127.0.0.1:8080`，Docker，`opensandbox/execd:latest`），以及杭州地域的阿里云极速版。没有全部通过。

## 两边都有，适配器会调用

| 能力 | 工具 id | OpenSandbox | 这次的真实结果 |
|---|---|---|---|
| 创建、连接、查询、列表、删除 | `sandbox.lifecycle` | `POST` / `GET` / `DELETE /v1/sandboxes` | OpenSandbox 创建成功，列表里能找到，删除两次都返回。阿里云 SDK 和 CLI 也创建并删除成功 |
| 修改超时 | `sandbox.timeout` | `POST /v1/sandboxes/{id}/renew-expiration` | OpenSandbox 接受 240 秒。阿里云 SDK 接受 420 秒 |
| 暂停 / 恢复 | `sandbox.pause` | `POST …/pause` 和 `…/resume` | OpenSandbox 从 `PAUSED` 回到 `RUNNING`。阿里云 `POST /pause` 返回 HTTP 400 |
| 执行命令 | `exec.run` | execd `POST /command`（SSE） | OpenSandbox stdout 是 `osb-exec ok`。阿里云 SDK 是 `sdk-exec ok`，CLI 是 `cli-exec ok` |
| 流式执行 | `exec.stream` | 同上 | 两边都打出了流式标记 |
| 进程列表和信号 | `process.manage` | 没有进程接口。列表用 `ps`，信号用 `kill` | OpenSandbox 列出 4 个 pid。阿里云 CLI 看到 `sleep` 的 pid 4 并发了信号 15。阿里云 SDK 的 `commands.list()` 返回 0 |
| 终端 | `pty` | `POST /pty`，WebSocket `/pty/{id}/ws`，数据帧带 `0x00` 前缀，引擎剥掉 | OpenSandbox 里 `echo $((40+2))` 得到 `42`。阿里云 envd `/terminal` 返回 WebSocket 404 |
| 文件读写、列目录、移动、删除 | `files.rw` | execd `/files` 和 `/directories` | 两边都读回了写入的内容。CLI 上传再下载得到 `cli-upload` |
| 端口 URL | `ports.url` | `GET /v1/sandboxes/{id}/endpoints/{port}` | OpenSandbox 返回 `http://127.0.0.1:<端口>`。阿里云 SDK 算出 `8080-sbx-….aliyuncs.com` |

进程 stdin 不是独立能力。OpenSandbox 的 `/command` 没有 stdin，调用 `commands.send_input` 返回 `E8004`。

## 当前工具有，OpenSandbox 没有

适配器拒绝这些调用，错误码 `E8004`。

| 能力 | 工具 id | 这次的真实结果 |
|---|---|---|
| 监听目录 | `files.watch` | OpenSandbox 拒绝。阿里云 SDK 收到 `MODIFIED` |
| 文件 URL | `files.transfer` | OpenSandbox 没有 envd 的 `/files` 地址 |
| 读取模板 | `templates.read` | Docker 上的 `GET /templates` 是 501（只给 fsb 微虚拟机）。阿里云 `template list` 返回 26 个账号模板，`template info base` 有真实记录 |
| 构建并发布模板 | `templates.build` | 这次没有调用。OpenSandbox 的 Docker 运行时不能构建模板 |
| 域名形式的端口 | `ports.domain` | 只有阿里云计算 `{port}-{id}.{domain}` |
| 存储挂载 | `storage.mount` | 没有挂载接口被调用 |
| VPC | `network.vpc` | 阿里云平台选项，不会发给 OpenSandbox |
| 沙箱内命名命令 | `sessions` | 阿里云 `base` 镜像上 `GET /commands` 是 502，镜像里没有 SandboxServer |

## OpenSandbox 有，当前工具没接

这些接口不在 `features` 里，适配器不会调用。

| OpenSandbox 接口 | 说明 |
|---|---|
| `POST /code` | 只有带 Jupyter 的 code-interpreter 镜像才有。`python:3.12-slim` 没有。调用代码解释器返回 `E8004` |
| `POST /session` 和 `/session/{id}/run` | 有状态 shell，`cd` 和 `export` 可以留下来 |
| `GET /command/{id}/logs` | 后台命令的日志续读。流式执行走的是前台 SSE |
| `POST /v1/sandboxes/{id}/snapshots` | 沙箱快照 |
| `/v1/sandboxes/{id}/networkpolicy` | 出网策略，需要 egress sidecar |
| `PATCH /v1/sandboxes/{id}/metadata` | 创建之后修改 metadata。创建时仍会发送 metadata |
| diagnostics、execd `GET /metrics` | 诊断和指标 |

## 阿里云极速版这次没有通过的项

对照不是全绿。上面表格里，阿里云失败或和 OpenSandbox 不一致的是：

- 暂停：平台返回 HTTP 400。
- 终端：envd `/terminal` WebSocket 404。
- SDK 进程列表：返回 0。同一类操作在 CLI 上能看到后台 `sleep`。
- 创建后立刻 `abx sandbox list`：返回 “No sandboxes found.” 同一时刻 `abx sandbox info` 能读到该沙箱。
- `abx sandbox system ports`：退出码 1，基础镜像里没有 `ss` 和 `netstat`。
- 命名命令：`GET /commands` 返回 502。

代码解释器在阿里云上 HTTP 404 后改走 shell，`print(6*7)` 的 stdout 是 `42`。这不是 OpenSandbox 的路径。

## 提供方登记更多能力

上面「OpenSandbox 有，当前工具没接」的接口不放进固定的 18 个 feature id。放进去会让 `alicloud-express` 的能力表和契约测试都出现它们。它们登记在 `Provider.extensions`。

登记只表示「这个提供方知道这件事」。`implemented=False` 时调用仍然是 `E8004`。看见和能调用是两回事。

### 什么时候能看到

| 位置 | 能看到什么 |
|---|---|
| `provider.describe()["extensions"]`，以及以后的 `provider info` | 该提供方登记的全部扩展。不看镜像，也不看沙箱是否存在 |
| `extensions_for(sandbox_id=...)` | 只看这个沙箱满足条件的扩展 |
| 另一个提供方，例如 `alicloud-express` | 看不到这些 id。它的 `extensions` 是空的 |
| CLI `abx --provider opensandbox` | 现在看不到。CLI 还没加载这个提供方，创建直接是 `E8001` |

### 什么时候在沙箱上看不到

`extensions_for` 在没有 `sandbox_id` 时返回空元组。有沙箱 id 之后：

| 扩展 | 沙箱上出现的条件 | 现在能调用吗 |
|---|---|---|
| `session`、`snapshot`、`metadata.patch`、`diagnostics`、`metrics` | 只要沙箱 id 存在 | 不能，`require_extension` 返回 `E8004` |
| `code` | 镜像名包含 `code-interpreter`。`python:3.12-slim` 上看不到 | 不能 |
| `networkpolicy` | 这次创建带了 egress sidecar | 不能 |
| `command.logs` | 调用方已经有一条后台命令的 id | 不能 |

`features` 的一行摘要（`abx provider list`）不列扩展。扩展只出现在提供方详情里。

### 怎么登记

Python 提供方在类上写 `extensions`：

```python
from agent_sandbox.providers.base import Extension, Provider

class Example(Provider):
    extensions = (
        Extension(
            id="session",
            summary="Stateful shell.",
            summary_zh="有状态 shell。",
            implemented=False,
            when="sandbox",
        ),
    )
```

`when` 只有四个值：`sandbox`、`code_interpreter_image`、`egress`、`command`。OpenSandbox 的八项登记在 `opensandbox_provider.EXTENSIONS`。

exec / rest 插件以后用清单登记，解析器还没接受这段，写进去现在不会生效：

```toml
[features.extensions.session]
summary = "Stateful shell."
summary_zh = "有状态 shell。"
implemented = false
when = "sandbox"
```

不要把这些 id 写进 `[features] supported`。那一列只接受固定的 18 个 id，多出来的会被清单校验拒绝。

### 怎么使用

```python
from agent_sandbox.providers.registry import get_provider

provider = get_provider("opensandbox")  # 先安装 registry:opensandbox
catalog = provider.describe()["extensions"]          # 八项都在
hidden = provider.extensions_for()                   # ()，还没有沙箱
slim = provider.extensions_for(
    image="python:3.12-slim", sandbox_id="sb-1",
)                                                    # 没有 code，没有 networkpolicy
coded = provider.extensions_for(
    image="opensandbox/code-interpreter:v1.1.0",
    sandbox_id="sb-1",
    egress=True,
    command_id="c1",
)                                                    # code、networkpolicy、command.logs 都在
provider.require_extension("code")                   # E8004，已登记但未实现
```

实现某一项时，把对应 `Extension` 的 `implemented` 改成 `True`，并在引擎适配器里加上那个 HTTP 调用。在此之前，`require_extension` 保持 `E8004`。
