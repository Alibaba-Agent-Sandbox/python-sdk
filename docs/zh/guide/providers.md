# 提供方（Providers）

工作流按具体消费入口的精确操作判断，见[模板工作流](template-workflows.md)。

本指南描述异步 `ProviderSandbox` 扩展；根级 `Sandbox` 和 `AsyncSandbox` 遵循固定版本的标准迁移契约，详见[从 E2B 迁移](migrate-from-e2b.md)。

> **说明：** 本页的 `abx provider ...` 命令由 `cli` 仓库中的 Node.js CLI 提供。只用 Python 的用户可以用 `python -m agent_sandbox.providers ...` 完成同样的操作。两者使用相同的安装目录、相同的回执和相同的目录树摘要。

**提供方**就是一个沙箱后端。SDK 和 CLI 只内置 `alicloud-express`。其余提供方用 `python -m agent_sandbox.providers install registry:<id> --yes` 安装，索引是 `https://registry.agent-sandbox.cn/providers/index.json`。启动时会在后台对照这份索引检查更新，结果写到 `~/.abx/providers/updates.json`。`ABX_PROVIDER_UPDATE_CHECK=0` 关掉检查。`ABX_PROVIDER_REGISTRY` 可以改索引地址。官网是 <https://www.agent-sandbox.cn>。提供方注册站是 <https://registry.agent-sandbox.cn>。

| Id | 名称 | 类型 | 默认 |
|---|---|---|---|
| `alicloud-express` | 阿里云极速版（Alibaba Cloud Express Edition） | 内置 | 是 |
| `alicloud-container` | 阿里云智能体沙箱容器版 | 目录插件，`node`；安装后 CLI 和所有 SDK 可用 | 否 |
| `cubesandbox` | CubeSandbox | 目录插件，`node`；安装后 CLI 和所有 SDK 可用 | 否 |
| `e2b` | E2B | 目录插件，`node`；安装后 CLI 和所有 SDK 可用 | 否 |
| `opensandbox` | OpenSandbox | 目录插件，`node`（ES 模块，EPP 方法在宿主进程内）；安装后 CLI 和所有 SDK 可用 | 否 |

除默认项以外的四个 id 在 `awesome-providers`，用 `abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes` 安装；公开索引发布后也可用 `python -m agent_sandbox.providers install registry:<id> --yes`（`abx` 没有 `registry:` 写法）。装好之后用 `Sandbox.create(provider="…")` 或 `abx --provider <id>` 选择。四个都是 `runtime.kind = "node"`（ES 模块 `provider.mjs`），只用 Node.js 写一次。CLI 在进程内加载它们。Python SDK 通过本机 Node 引擎（`abx provider engine serve`，按需启动，所以 `abx` 要在 `PATH` 里或用 `ABX_BIN` 指定）用 `EngineProvider` 访问（`engine://<provider>/<sandbox-id>`）。第三方的 `exec` 或 `rest` 清单仍在 Python 进程里运行。内置的 `alicloud-express` 是 Python 内置提供方。没有可安装的 `python` 类型。见 CLI 的[引擎 HTTP API](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/engine-api.md)。

| Id | 怎么用 |
|---|---|
| `opensandbox` | [OpenSandbox 提供方](../design/provider-opensandbox-mapping.md)。HTTP 由加载 `provider.mjs` 的 Node 宿主进程发出。`ABX_OPENSANDBOX_BASE_URL` 默认 `http://127.0.0.1:8080`。 |
| `alicloud-container` | [容器版](../design/provider-alicloud-container.md)。需要 `ABX_ALICLOUD_CONTAINER_DOMAIN`。不读取 `ABX_SANDBOX_API_KEY`。 |
| `cubesandbox` | [CubeSandbox 提供方](../design/provider-cubesandbox.md)。默认地址 `http://127.0.0.1:3000`。 |
| `e2b` | [E2B 提供方](../design/provider-e2b.md)。密钥是 `ABX_ABX_SANDBOX_API_KEY`。不读取 `ABX_SANDBOX_API_KEY`，也不读取 `ABX_SANDBOX_API_KEY`。 |

还没有后端的三个提供方，逻辑上能不能用，写在 [可用性审查](../design/provider-readiness.md)。让代理写一个新的提供方插件，用技能 `agent-sandbox-provider`（`agent-sandbox-provider/SKILL.md`）。

如果你从不接触提供方，一切照旧：每个命令、每种输出和每个环境变量的行为都和以前一样。id `alicloud-express` 是稳定的，只有显示名称可能改变。

---

## 引擎恢复与结果未知

对于 Node 提供方插件，Python SDK 只会在 `GET`、`HEAD` 发生传输故障时重新
发现本机引擎并重试一次。读取流也只能在产出第一个事件之前恢复。创建、执行、
上传等变更操作在连接故障后不会自动重放，即使还没有收到响应或 SSE 事件；
引擎可能已经完成了操作。

这类故障会抛出 `ProviderProtocolError`（E8020），说明操作结果未知。请先检查
所选提供方的沙箱列表或命令状态，再决定是否重试；直接重试可能重复创建资源
或重复执行命令。明确收到引擎 HTTP 401 拒绝时，仍可以重新发现引擎一次，
因为鉴权在操作分发之前拒绝了请求。这不代表幂等或自动回滚保证。

## 选择提供方

优先级从高到低：

| 位置 | 示例 |
|---|---|
| SDK 参数 | `await Sandbox.create(provider="my-cloud")` |
| CLI 选项 | `abx create --provider my-cloud` |
| 进程环境变量 | `export ABX_PROVIDER=my-cloud` |
| `./.env` | `ABX_PROVIDER=my-cloud` |
| `~/.abx/.env` | `ABX_PROVIDER=my-cloud` |
| `~/.abx/config.toml` | `[core]` `provider = "my-cloud"`（由 `abx provider default my-cloud` 写入） |
| 内置 | `alicloud-express` |

```python
from agent_sandbox.api.sandbox import Sandbox

sb = await Sandbox.create(template="base")                          # alicloud-express
sb = await Sandbox.create(template="base", provider="local-process")
sb = await Sandbox.create(provider="my-cloud", provider_options={"cluster": "prod"})
print(sb.provider)                                                  # "my-cloud"
await sb.kill()
await sb.close()                                                    # 释放提供方进程
```

`Sandbox.connect`、`Sandbox.list` 和 `Sandbox.kill_by_id` 接受同样的 `provider=` 参数。沙箱 id 属于创建它的提供方。给 `connect` 传限定引用（如 `my-cloud:sbx-1`），提供方就取自前缀。`provider=` 与前缀冲突会抛出 `ProviderMismatchError`（E8030）。

默认提供方管理：

```bash
abx provider list
abx provider default my-cloud       # 持久化到 ~/.abx/config.toml
abx provider default                # 显示当前默认提供方
abx provider default alicloud-express
```

---

## 安装提供方插件

```bash
abx provider install ./my-provider                          # 本地目录
abx provider install https://github.com/acme/abx-provider-acme.git --ref 3f2c...   # 完整提交
abx provider install git@github.com:acme/abx-provider-acme.git --ref v1.2.0 --allow-unpinned
abx provider list
abx provider info my-cloud
abx provider update my-cloud --check
abx provider uninstall my-cloud
```

不用 CLI 时：

```bash
python -m agent_sandbox.providers install ./my-provider
python -m agent_sandbox.providers list --json
python -m agent_sandbox.providers update my-cloud --check
python -m agent_sandbox.providers doctor my-cloud
python -m agent_sandbox.providers test my-cloud       # 契约测试套件（需要 pytest）
```

### 安装会做什么、不会做什么

- **安装时不会执行插件里的任何东西。** 没有 `setup.py`，没有 postinstall 钩子，也没有 `git checkout`。Git 来源以不检出的方式获取，每个条目都会被校验（只允许普通文件，不允许符号链接和子模块，并有大小和数量限制），文件由安装器自己写入。
- 安装会显示**同意界面**：id、版本、来源、解析出的提交、内容摘要、将要运行的命令、声明的安全块、特性和配置字段。非交互运行需要 `--yes`。
- 给出完整的 40 位十六进制提交（`--ref`）或 `--sha256 <目录树摘要>` 时，来源是**已固定（pinned）**的。标签或分支是**未固定（unpinned）**的：它可能在你审查之后、安装之前移动。只有在终端里有人读过同意界面（不加 `--yes`）之后才会接受未固定的来源，或者显式加 `--allow-unpinned`。单独的 `--yes` 永远不会接受会移动的 ref：安装以 `ProviderTrustError`（E8012）失败，并打印应当固定的提交。`provider update` 适用同一规则。
- 只接受 `https://` 和 `ssh` 的 git URL。带内嵌凭证的 URL 会被拒绝；请使用 SSH agent，或者安装你自己克隆的目录。`--allow-insecure-transport` 会启用 `file://`、`http://` 和 `git://`（用于测试和开发）。
- 已安装的文件记录在回执（`.abx-install.json`）里，带有 SHA-256 目录树摘要。**每次插件启动时都会校验该摘要**。如果有文件被改动，命令以 `ProviderIntegrityError`（E8011）失败；请重新安装或运行 `provider update`。
- `--link` 做开发用的符号链接安装，没有完整性检查。它需要确认，并且每次使用都会在 stderr 打印警告。

### 更新与卸载

`provider update` 从记录的来源重新获取。如果命令、安全块或特性列表变了，你必须重新同意。**已固定**（40 位十六进制提交或 `--sha256`）的安装不会移动：`update` 报告 `pinned` 且什么也不做，除非你传入新的 `--ref`。`update` 与 `install` 接受同样的传输和校验参数：`--ref`、`--check`、`--yes`、`--allow-unpinned`、`--allow-insecure-transport`（回执不会记住你用过它；`file://`、`http://` 或 `git://` 来源每次更新都需要它）和 `--no-verify`（跳过更新后的握手）。旧版本保留在回收目录里，直到新版本成功启动后才丢弃。如果新版本失败（例如握手失败），旧文件**及其 `data/` 目录**会被原样恢复。`provider uninstall` 删除目录；已保存的设置（`[providers.<id>]`、`ABX_<ID>_*`）会保留，除非加 `--purge`。卸载默认提供方会把默认值重置为 `alicloud-express`。

### 文件位置

```text
~/.abx/providers/
  <id>/
    abx-provider.toml     # 清单
    ...                   # 插件文件
    .abx-install.json     # 回执：来源、提交、摘要、同意记录
    data/                 # 插件的工作和状态目录（不参与摘要）
```

---

## 提供方类型

| 类型 | 是什么 | 可安装 | 适用于 |
|---|---|---|---|
| `builtin` | `alicloud-express` | 不适用 | SDK 和 CLI |
| `rest` | 只有清单：一个 E2B 协议端点，带自己的基础 URL 和密钥 | 是 | SDK 和 CLI |
| `exec` | 一个说 EPP/1 的程序（JSON-RPC 2.0，每行一个 JSON 对象，经 stdin/stdout） | 是 | SDK 和 CLI |
| `node` | 一个 ES 模块（`provider.mjs`，`export default create(kit)`），由 Node.js 宿主在进程内加载。`opensandbox`、`e2b`、`cubesandbox`、`alicloud-container` 都是这种 | 是 | SDK（经引擎）和 CLI |
| `python` | 代码里的 `Provider` 子类，用 `register_provider` 或 pip 入口点登记。`kind = "python"` 的清单不能安装 | 否 | 仅 SDK |

四个目录提供方都是 `node`。`exec` 是第三方插件的扩展点：一个进程可以同时服务 Python SDK 和 Node CLI，并可用任何语言编写。已经说 E2B envd 数据平面协议的后端只需实现控制面（创建、连接、列出、销毁）并返回 envd URL，之后命令、文件和终端都走快速的原生传输。没有 envd 的后端还需要实现数据平面方法（`exec.run`、`files.*`）。

### 能力矩阵

提供方声明自己实现的特性。调用它没有的特性会抛出 `ProviderFeatureNotSupportedError`（E8004，同时也是 `CapabilityNotSupportedError`），而不是 `AttributeError` 或 HTTP 404。

| 特性 | 覆盖范围 |
|---|---|
| `sandbox.lifecycle` | 创建、连接、列出、查看、销毁 |
| `sandbox.timeout`、`sandbox.pause` | 修改 TTL；暂停与恢复 |
| `exec.run`、`exec.stream`、`process.manage` | 缓冲式命令；流式输出；列出、终止和发信号给进程 |
| `pty` | 交互式终端 |
| `files.rw`、`files.watch`、`files.transfer` | 读、写、列出、移动、删除；监听；带签名的上传和下载 URL |
| `templates.read`、`templates.build` | 列出和查看模板；原有镜像构建、部署和删除 |
| `ports.url`、`ports.domain` | 端口的公网 URL；自定义域名 |
| `storage.mount`、`network.vpc` | 对象存储挂载；VPC 接入 |
| `sessions` | 沙箱在进程结束后仍存在，可按 id 重新连接 |

`abx provider list` 用一行显示每个提供方声明的特性（`sandbox(lifecycle,pause) exec(run,stream) files(rw) ...`；`python -m agent_sandbox.providers list` 输出相同），`abx provider info <id>` 显示完整清单。

清单里的特性标志在运行时对每一种提供方都会被强制执行：

| 类型 | 未声明的特性在哪里被拦下 | 结果 |
|---|---|---|
| `exec` | EPP 适配器，在请求写给插件之前 | E8004 |
| `rest` | 包在内置协议类外面的 `feature_gate`，在任何 HTTP 请求之前 | E8004 |
| `node` | Python 侧在发给引擎之前由 `EngineProvider` 拦住；CLI 在进程内做同样的拦截 | E8004 |
| `python` | 提供方自己代码里的 `Provider.require(feature)` | E8004 |

已声明的特性在后端内部失败不属于 E8004，而是映射后端的错误（见下文「错误」）。两种「未找到」被有意区分开：未知的**沙箱 id** 在所有提供方、所有 `sandbox.*` 调用（`connect`、`info`、`set_timeout`、`pause`、`resume`；`kill` 仍然幂等）上都是 `SandboxNotFoundError`（E2009）；缺失的模板、文件或进程是 E4001/E2001，没有 `sdk_code` 时是 `ProviderResourceNotFoundError`（E8005）。

### 安装之后能调用什么

安装一个提供商，并不会打开全部 SDK 方法或全部 `abx` 命令。SDK 和 CLI 调用的是**同一份已安装插件**。每个方法和命令都对应上表里的一项能力。插件没有声明时，调用会在发出请求之前抛出 `ProviderFeatureNotSupportedError`（E8004）。`node`、`exec` 和 `rest` 插件两边都能用。进程内注册的 `python` 提供商只给 SDK 用。`kind = "python"` 的清单不能安装。

| 能力 | Python SDK | CLI |
|---|---|---|
| `sandbox.lifecycle` | `Sandbox.create`、`connect`、`list`、`kill`、`info` | `create`、`list`、`info`、`kill`、`connect` |
| `sandbox.timeout` | `set_timeout` | `sandbox timeout` |
| `sandbox.pause` | `pause`、`resume` | `sandbox pause`、`sandbox resume` |
| `exec.run` | `commands.run`、`sandbox.run` | `exec`、`run` |
| `exec.stream` | `commands.stream` | `exec --stream` |
| `process.manage` | `commands.list`、`kill`、`send_stdin` | `sandbox process ...` |
| `pty` | `get_terminal` | PTY 会话 |
| `files.rw` | `files.*` | `upload`、`download`、`sandbox files ...` |
| `files.watch` | `files.watch` | — |
| `files.transfer` | 带签名的上传和下载 URL | — |
| `templates.read` | 模板读取 API | `template list`、`template info` |
| `templates.build` | 镜像构建和模板注册 | `template build/push/create/deploy/install/delete`、`deploy`、`install` |
| `ports.url` | `network.get_url` | `sandbox url` |
| `ports.domain` | 自定义域名 | — |
| `storage.mount` | OSS 挂载 | — |
| `network.vpc` | VPC 配置 | `--vpc-id` 及相关参数 |
| `sessions` | 对已有 id 调用 `Sandbox.connect` | `connect <provider:id>` |

### OpenSandbox

OpenSandbox 是目录插件，不在这个包里。先安装再创建：

```bash
python -m agent_sandbox.providers install registry:opensandbox --yes
```

```python
sb = await Sandbox.create(template="base", provider="opensandbox")
proc = await sb.commands.run("echo hello")
await sb.files.write("/tmp/note.txt", "hello")
print(await sb.files.read("/tmp/note.txt"))
await sb.kill()
```

能力对照在 [OpenSandbox 提供方](../design/provider-opensandbox-mapping.md)。同一份说明在 `awesome-providers/opensandbox/docs/README.md`。

### 扩展能力

上面的 feature id 是工具的公共面。提供方在这之外的操作登记到 `Provider.extensions`。它们不进 `features`，所以 `provider list` 的一行摘要里没有，别的提供方也不会带上。

`describe()["extensions"]` 列出当前 Provider 登记的扩展。扩展不代表标准操作已接入；以具体消费入口的精确操作为准。

---

## 编写提供方

插件是一个目录，里面有 `abx-provider.toml` 和它要运行的程序。

```toml
manifest_version = 1

[provider]
id      = "local-process"
name    = "Local Process"
name_zh = "本地进程"
version = "0.1.0"

[compat]
protocol = "epp/1"

[runtime]
kind    = "exec"
command = ["python3", "./provider.py"]   # argv 数组，不是 shell 字符串；"./" 相对于插件目录

[features]
supported = ["sandbox.lifecycle", "exec.run", "files.rw"]

[security]                               # 安装时显示并记录；仅作声明，不强制执行
filesystem       = ["data_dir"]
spawns_processes = true

[core]
inherit = []                             # 插件想要的通用键；需要用户同意

[config.fields.workdir_root]             # 插件自己的设置：ABX_LOCAL_PROCESS_WORKDIR_ROOT
type    = "path"
required = false
description = "Directory that holds sandbox working directories"
```

仓库里有两个可运行的示例：

- `examples/providers/local-process/` —— 约 200 行 Python 标准库写成的 `exec` 提供方（生命周期、命令、文件）。
- `examples/providers/e2b-compatible/` —— 只有清单的 `rest` 提供方。

OpenSandbox 是 [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox) 里的目录 `node` 提供方（一个无依赖的 ES 模块，宿主进程内运行它的 EPP/1 方法；直接 `node provider.mjs` 仍可在 stdio 上提供 EPP/1）。它在宿主进程里访问 [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) 服务：流式 exec、文件、进程控制、终端、暂停 / 恢复和端口 URL。安装命令是 `abx provider install alibaba-agent-sandbox/awesome-providers//opensandbox --allow-unpinned --yes`（或 Python 模块），然后 `Sandbox.create(provider="opensandbox")` 或 `abx --provider opensandbox`。后端是 E2B 形状时，写 `node` 插件更短：见 `awesome-providers/e2b/provider.mjs`。

### 编写检查清单

1. **清单**：`manifest_version = 1`、合法的 id。目录风格的提供方是 `[compat] protocol = "node/1"`、`[runtime] kind = "node"`，`entry` 是相对的 `.mjs` 或 `.js`。`exec` 插件是 `protocol = "epp/1"`、`kind = "exec"`，并带 `command`。`rest` 只有端点，没有程序。`kind = "python"` 的清单不能安装。每个选项都写进 `[config.fields.*]`，密钥加 `secret = true`，厂商自己的变量名写进 `env = [...]`。清单有错时返回 `E8014`，并指出出错的字段。第 2 到第 6 条是 `exec` 的检查清单。
2. **必须实现的方法**：`initialize`（返回你实现的特性）、`shutdown`，以及 `sandbox.lifecycle` 的 `sandbox.create|get|list|kill`。其余都按特性划分（见「插件要响应的方法」）。
3. **特性标志**：只声明确实可用的特性。其余的宿主直接返回 E8004，不会调用你。
4. **错误**：缺少特性返回 `-32003`；沙箱不存在返回 `-32002`（想写明的话加 `sdk_code` `E2009`）；凡是有对应 SDK 类的都带 `sdk_code`；信息里绝不出现凭证。
5. **一致性测试**：`python -m agent_sandbox.providers test <id>`（或 `abx provider test <id>`）必须通过；被跳过的用例就是你没有声明的特性。
6. **发布**：给出带 40 位十六进制提交的固定安装命令，如实填写 `[security]`，并在 README 里写明同意界面的内容。

开发循环：`python -m agent_sandbox.providers install ./my-provider --link --yes` 安装一个不校验摘要的符号链接，修改立即生效。先运行 `doctor`，再运行 `test`（见下文），最后安装固定版本的副本正式使用。

### 插件要响应的方法

线上方法、参数名和类型，以及哪些是必需的，列在 [EPP 方法表](../design/providers-and-credentials.md#epp-methods)里，机器可读的版本是 SDK 仓库的 `tests/fixtures/epp-methods.json`（CLI 保留一份逐字节相同的拷贝）。简述如下：

- `sandbox.lifecycle` 的**必需**方法：`sandbox.create`、`sandbox.get`、`sandbox.list`、`sandbox.kill`。`sandbox.connect` 是**可选**的（用于恢复或重新附着）；插件对它回答 `-32601` 时，宿主改调 `sandbox.get`。
- **按特性**：`exec.run`、`exec.start`（`exec.stream`）、`process.list|kill|signal|stdin`、`files.read|write|list|stat|mkdir|remove|move`、`ports.url`、`sandbox.set_timeout`、`sandbox.pause|resume`。只有实现了某个特性的全部方法才声明它；其余情况宿主抛出 E8004。
- **扩展**（宿主暂不调用，插件可以提供）：`files.search`、`files.chmod`、`exec.start{detached}`、`files.read{offset,length}`、`files.write{mode,append}`。
- `files.move` 的参数是 `{sandbox_id, source, destination, overwrite?}`（插件也可以接受 `src`/`dest`）。
- `exec.start` 返回后端原生的非空不透明字符串或正的安全整数 `process_id`。启动时先发送数据为空、携带原始 `pid` 的确认块；标识缺失或非法会失败，stdout 不作为启动确认。`process.kill|signal|stdin` 的 `pid` 是不透明 id：既可以是 `process.list` 条目的整数 `pid`，也可以是该原生启动标识；`ProcessInfo.pid` 和 `commands.kill(pid)` 两者都接受。
- 未知的错误 `sdk_code` 会回退为该 EPP 码的默认类。可接受的值就是宿主映射的 SDK 错误码，例如 `E1001`（凭证错误）、`E2000`/`E2001`（沙箱 / 模板未找到）、`E3001`（命令超时）、`E4001`（文件未找到），见[错误码参考](../reference/error-codes.md)。缺失**文件**时单独的 `-32002` 会变成 E8005，所以请带上 `sdk_code: "E4001"`；在 `sandbox.get`/`connect`/`set_timeout`/`pause`/`resume` 上，未知沙箱的单独 `-32002` 会变成 E2009（插件也可以直接写 `sdk_code: "E2009"`）。
- 清单里的默认值会**随** `initialize.config` 一起送达。不要给带有替代项的字段（`base_url` 与 `domain`）设置默认值：默认值总会胜出。
- 对一个正在运行的请求发 `$/cancel {id}` 的含义是：停止工作（杀掉派生的进程），并以错误或最终结果应答。

### `sandbox.create` 会收到什么

`Sandbox.create(..., provider="my-cloud", provider_options={...}, secure=...)` 发送：

| 参数 | 何时 |
|---|---|
| `template`、`timeout`、`metadata`、`envs`、`cpu`、`memory`、`disk`、`gpu`、`request_timeout` | 总是 |
| `secure` | 仅当调用者传了 `secure=True/False`；否则缺失，由插件自己的默认值决定（内置提供方按 `secure=True` 处理） |
| `options` | 调用者传入的 `provider_options`（仅已声明的配置字段），**不含密钥字段**；用于每次创建的设置，例如网络策略、平台或镜像拉取设置 |

`sandbox.network.get_url(port)` 仍是本地的同步计算。`await sandbox.network.resolve(port)` 返回 `(url, headers)`，`await sandbox.network.resolve_url(port)` 返回 URL；当提供方声明了 `ports.url` 时两者会询问插件的 `ports.url`，否则回退到本地计算。

对**所有**提供方，`sandbox.commands.start()`（以及 `run(..., background=True)`）返回的都是惰性流：在迭代该流之前什么都不会发送。要启动任务且不等待，请通过 `commands.run(..., shell=True)` 运行 `nohup ... &`，或使用 `sessions` 特性。

### 配置与凭证

每个提供方有自己作用域的键：环境变量或 `.env` 里是 `ABX_<PROVIDER>_<KEY>`，`config.toml` 里是 `[providers.<id>]`，SDK 里是 `provider_options={...}`。提供方只会在 `initialize` 请求里收到其清单声明的键。密钥绝不会放进插件的 argv 或环境变量。

通用键 `sandbox_api_key`、`sandbox_base_url` 和 `sandbox_domain`（`ABX_SANDBOX_API_KEY` 和 `ABX_SANDBOX_BASE_URL`）属于内置提供方。只有当插件清单在 `[core] inherit` 里列出它们，**并且**你在安装或更新时同意了，插件才能拿到。同意界面会列出这些键的名字。你的 LLM、GitHub 和 MCP 键永远不会交给提供方。

### 宿主如何处理插件进程

下面说的是 `exec` 子进程。`node` 提供方由 Node 宿主加载（CLI 在进程内，Python SDK 则是 `abx provider engine serve`），不会按下面这种方式拉起。

- 以清理过的环境启动：`PATH`、`HOME`、临时目录和语言环境变量、`env_passthrough` 中列出的名字，以及 `ABX_PROVIDER_DATA_DIR`。不会泄入 `ABX_*`、`E2B_*`、`ALICLOUD_*`、`GITHUB_TOKEN` 或 `OPENAI_*`。工作目录是插件的 `data/` 目录。
- 单行协议消息限制为 8 MiB，并为崩溃信息保留 stderr 的最后 64 KiB。在 `initialize` 里发送过的值会从捕获的 stderr 和错误信息中被遮蔽。
- 应用超时（默认启动 10 秒、每次调用 60 秒），并在超时、崩溃或关闭时终止整个进程组。
- 只重试幂等方法，并且只在插件标记为 `retryable` 的错误上重试。

> **没有隔离。** 插件是第三方代码，以你的用户权限运行，并拿着你为该提供方配置的凭证。只安装你信任的代码。固定、摘要校验和同意可以缩小风险，但并不会沙箱化进程。`[security]` 块是展示给你看的声明，而不是限制。

### 错误

宿主把插件的错误映射到现有的异常层级，所以无论哪个提供方，脚本看到的异常类型和 CLI 退出码都相同。

| EPP 错误码 | 抛出为 | CLI 退出码 |
|---|---|---|
| `-32001` 未认证 | `AuthenticationError` 系列（E1xxx） | 3 |
| `-32002` 未找到 | 对已有 id 的 `sandbox.*` 调用是 `SandboxNotFoundError`（E2009）；其他情况是 `ProviderResourceNotFoundError`（E8005），或 `data.sdk_code` 指定的类 | 4 |
| `-32003` 特性不支持 | `ProviderFeatureNotSupportedError`（E8004） | 1 |
| `-32004` 超出配额 | `QuotaExceededError` | 6 |
| `-32005` 超时 | `ProviderTimeoutError`（E8022）或 `CommandTimeoutError` | 5 |
| `-32006` 参数或配置无效 | `ProviderConfigError`（E8002） | 2 |
| `-32000` 其他失败 | 按 `data.sdk_code` 选类，否则 `ProviderError`（E8000） | 1 |
| JSON-RPC 标准错误码 | `ProviderProtocolError`（E8020） | 1 |

完整的 E8xxx 列表见[错误码参考](../reference/error-codes.md#e8xxx--提供方错误providererror)。

### 测试插件

运行契约测试套件有三种方式，由省事到费事。套件只检验插件声明过的特性，其余跳过（跳过不算失败）。

```bash
# 1. 一条命令，无需测试文件。什么都没收集到时会失败。
python -m agent_sandbox.providers test my-cloud --option base_url=http://127.0.0.1:8080
python -m agent_sandbox.providers test my-cloud -- -k exec -x      # `--` 之后是额外的 pytest 参数

# 2. 直接用 pytest，无需测试文件
pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract \
       --provider-under-test my-cloud --provider-option base_url=http://127.0.0.1:8080
```

```python
# 3. 在你插件自己的测试里写子类
from agent_sandbox.providers.testing import ProviderContractTests

class TestMyProvider(ProviderContractTests):
    provider_id = "my-cloud"          # 已安装的提供方
    provider_options = {}
```

（`--provider-under-test` 和 `--provider-option KEY=VALUE`（可重复）在用 `-p` 把 `agent_sandbox.providers.testing` 作为 pytest 插件加载时注册。`ABX_PROVIDER_UNDER_TEST` 设置默认值。没有选择提供方时套件会**失败**而不是跳过。）

它检查什么：已声明特性是否已知；密钥字段没有默认值；生命周期（创建、连接、列出、销毁，未知 id 是 `E2009`）；`kill` 幂等；`set_timeout`；暂停与恢复；`exec.run` 的退出码、stderr 和环境变量；流式输出顺序及恰好一个最终 `exit`；命令超时是否被强制执行；进程列表；文件（文本、二进制、Unicode、目录、移动、删除、缺失文件是类型化的未找到）；`ports.url`；你**没有**声明的特性是否以 E8004 失败（一个 `CapabilityNotSupportedError`）；以及密钥选项的值绝不出现在错误文本中。

离线测试：套件需要一个可用的后端。对于访问 HTTP 的插件，请写一个小型 mock 服务器，并用一个很小的 JSON-RPC 客户端通过 stdio 驱动插件。[opensandbox 插件](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox)里两者都有（`tests/mock/`、`tests/epp-client.mjs`）。

不运行沙箱也能检查已安装提供方的接线：

```bash
python -m agent_sandbox.providers doctor my-cloud          # 清单、摘要、握手、凭证
python -m agent_sandbox.providers doctor my-cloud --no-handshake
```

在含有无关 `conftest.py` 的目录里运行 `pytest`？加上 `--noconftest`（或 `--confcutdir`）。`python -m agent_sandbox.providers test` 已经让自己与当前目录的 pytest 配置隔离。

---

## 代码里的 Python 提供方（仅 SDK）

```python
from agent_sandbox.providers import Provider, register_provider

class MyProvider(Provider):
    id = "my-cloud"
    ...

register_provider(MyProvider())
```

软件包也可以在 `agent_sandbox.providers` 组里发布入口点，指向一个 `Provider` 实例或无参工厂；它会在第一次列出提供方时加载。这类提供方在你的进程内以完全信任运行，所以不能用 `abx provider install` 安装。

---

## 另请参阅

- [配置参考](../reference/configuration.md) —— 名称、别名、优先级
- [认证详解](authentication.md)
- [设计：提供方与凭证](../design/providers-and-credentials.md)

原生终端在读取会话上下文或启动协议适配器前检查 Provider 的 `pty` 声明。
不支持时返回明确的能力错误；客户端存在方法并不代表账号或函数已开通该能力。
