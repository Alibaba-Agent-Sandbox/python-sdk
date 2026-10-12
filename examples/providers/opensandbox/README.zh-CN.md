# opensandbox 提供方插件

[English](README.md)

一个 [EPP/1](../../../docs/zh/design/providers-and-credentials.md) **exec 提供方**插件，让 Easy Sandbox 在
[OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) 服务（Docker 或 Kubernetes 运行时）上创建沙箱。
Python SDK（`Sandbox.create(provider="opensandbox")`）与 `ebx` CLI（`ebx --provider opensandbox ...`）均可直接使用。

* 运行时：**Node.js >= 20，无 npm 依赖**（使用内置 `fetch`）。选择 Node 是因为 `ebx` CLI 本身基于 Node，
  使用 CLI 的用户已具备 Node；仅使用 Python SDK 时需要 `node` 在 `PATH` 中。
* 设计与 API 映射：[`provider-opensandbox-mapping.md`](../../../docs/en/design/provider-opensandbox-mapping.md)（仅英文）。
* 产出本插件的编写体验评估：[`provider-authoring-evaluation.md`](../../../docs/zh/design/provider-authoring-evaluation.md)。

## 安装

```bash
python -m easy_sandbox.providers install examples/providers/opensandbox --yes   # 或：ebx provider install <path|git-url>
python -m easy_sandbox.providers doctor opensandbox
```

从 git 安装时需固定提交（`file://` 等明文传输另需 `--allow-insecure-transport`）：

```bash
ebx provider install https://example.com/you/ebx-provider-opensandbox.git --ref <40 位提交哈希>
```

安装不会执行任何代码；只有命令实际用到插件时才会启动，且每次启动前都会按安装回执重新校验文件摘要。

## 配置

每个字段都可通过规范名称 `EBX_OPENSANDBOX_<FIELD>`、`~/.ebx/config.toml` 的 `[providers.opensandbox]` 段，
或（有列出时）OpenSandbox 原生环境变量设置。规范名称优先。

| 字段 | 原生别名 | 默认值 | 含义 |
|---|---|---|---|
| `base_url` | | `http://127.0.0.1:8080` | 服务根地址（可带 `/v1` 后缀） |
| `api_key`（机密） | `OPEN_SANDBOX_API_KEY` | 无 | 以 `OPEN-SANDBOX-API-KEY` 头发送；本地服务可不需要 |
| `domain`、`protocol` | `OPEN_SANDBOX_DOMAIN`、`OPEN_SANDBOX_PROTOCOL` | `http` | `host[:port]`，`base_url` 的替代写法 |
| `use_server_proxy` | `OPEN_SANDBOX_USE_SERVER_PROXY` | `false` | 通过服务代理访问沙箱 |
| `default_image` | | `python:3.12-slim` | 通用模板 `base` 使用的镜像 |
| `image_aliases` | | `code=opensandbox/code-interpreter:v1.1.0` | `name=image,...` 形式的模板短名 |
| `entrypoint` | | `tail -f /dev/null` | 通用镜像的常驻入口命令 |
| `ready_timeout` | | `60` | 等待 Running 与 execd 就绪的秒数 |
| `registry_username`、`registry_password`（机密） | | 无 | 私有镜像仓库认证 |
| `network_policy` | | 无 | 应用于每个新沙箱的 JSON 网络策略 |
| `platform` | | 无 | `linux/amd64`、`linux/arm64` 等 |
| `secure_access` | | `false` | Kubernetes 网关安全访问 |

`Sandbox.create(template=...)` 的解析顺序：先查别名，其次 `base` 映射到 `default_image`，否则按镜像引用原样使用。

## 能力

| 特性 | 状态 | 说明 |
|---|---|---|
| `sandbox.lifecycle` | 支持 | 创建（等待 Running 与 execd，失败时回收）、connect、get、list（分页）、kill（幂等） |
| `sandbox.timeout` | 支持 | `set_timeout`；OpenSandbox 最小 60 秒会被截断；新的到期时间按服务端时钟计算 |
| `sandbox.pause` | 支持 | pause / resume（Docker 运行时） |
| `exec.run`、`exec.stream` | 支持 | env、cwd、user、stdin、timeout；有序的 `exec.output` 与唯一的 `exec.exit`；`$/cancel` 可中止命令 |
| `process.manage` | 部分 | `process.list`；`process.kill` / `process.signal`（数字 pid：任意信号；execd 命令 id：仅 SIGKILL）；`process.stdin` 返回 `E8004` |
| `files.rw` | 支持 | read（offset/length）、write（mode）、list、stat、mkdir、remove、move，另有 `files.search`、`files.chmod` 扩展（目前无宿主调用） |
| `ports.url` | 支持 | `ports.url` 方法（直连端点，或配合 `use_server_proxy` 走服务代理） |
| `sessions` | 支持 | 通过 `exec.start` 的 `detached` 扩展实现后台命令（目前尚无宿主适配器发送该参数） |
| `pty`、`code.interpret`、`templates.*`、`files.watch`、传输 URL | 不支持 | `E8004`（`-32003`） |

## 测试

```bash
node tests/run.mjs                      # 24 个单元测试 + 21 个模拟服务测试，无需真实服务
```

联机测试需要可访问的 OpenSandbox 服务（一键本地启动见 `../../e2e/opensandbox/README.md`）：

```bash
export EBX_OPENSANDBOX_BASE_URL=http://127.0.0.1:8080
export OPEN_SANDBOX_API_KEY=...         # 按你的服务要求设置
OPENSANDBOX_LIVE=1 node tests/run.mjs live                         # 直接以 EPP/1 驱动插件
OPENSANDBOX_LIVE=1 python -m pytest tests/contract                 # 契约测试套件 + SDK 场景
python ../../e2e/opensandbox/provider_e2e.py                       # 全部阶段，使用临时 HOME
python ../../e2e/opensandbox/provider_install_e2e.py               # 安装 / 更新 / 卸载流程
```

`tests/contract` 需要可导入的 `easy_sandbox` 和 `pytest`；它把插件安装到临时的 `~/.ebx`，不会改动你真实的存储。

## 目录结构

```
ebx-provider.toml   清单（运行时、特性、安全声明、配置模式）
provider.mjs        入口：EPP 分发与能力装配
src/                http.mjs（生命周期 + execd 客户端）、sandbox.mjs、exec.mjs、files.mjs、
                    sse.mjs、multipart.mjs、convert.mjs、config.mjs、errors.mjs、epp.mjs
tests/              unit/、mock/（进程内模拟服务）、live/、contract/（pytest）
```

## 已知限制

* 文件读写受 EPP 8 MiB 行长度限制（单次读取上限 4 MiB，可用 `offset`/`length` 分段）。
* 传给 `Sandbox.create` 的 `secure=True` 会请求网关“安全访问”（仅 Kubernetes 网关部署；Docker 服务会拒绝）。`secure=False` 或不传 `secure` 则保持关闭；也可用 `secure_access` 配置字段设置全局默认值。
* 按次创建的设置：传给 `Sandbox.create` 的 `provider_options={"network_policy": ..., "platform": ..., "default_image": ...}` 只对该沙箱覆盖已配置的值（白名单：`default_image`、`image_aliases`、`entrypoint`、`ready_timeout`、`registry_username`、`registry_password`、`network_policy`、`platform`、`secure_access`；绝不包括服务地址或 API key）。
* 对所有提供方，`commands.start()` 都是惰性的（迭代流之前什么都不会发送）；要启动后台进程，请通过 `commands.run(..., shell=True)` 运行 `nohup ... &`。
* 旧版 execd v1.1.0 不支持 `argv` 且会吞掉换行符；插件会自动检测并降级（要获得精确输出请使用较新的 execd 镜像）。

许可证：Apache-2.0。
