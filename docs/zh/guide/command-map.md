# 命令与 SDK 对照

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

同一行是同一件事在三家产品里的最近入口。它不是参数级兼容，也不是把 Agent Sandbox 收成其中一家的子集。

`abx` 是 Agent Sandbox 的命令行。Python SDK 是 `agent-sandbox-client`。默认提供方是阿里云极速版。装上 `opensandbox` 提供方之后，`abx` 的命令名不变，请求改发到 OpenSandbox 服务。那和直接运行 `osb` 不是同一条命令。

对照用的公开表面：

| 产品 | 命令行 | SDK |
|---|---|---|
| Agent Sandbox | `abx`（`@agent-sandbox/cli`） | `agent-sandbox`，`from agent_sandbox.api.sandbox import Sandbox` |
| E2B | `e2b`（`@e2b/cli`，文档版本 2.16.1） | `e2b`，`from e2b import Sandbox` |
| OpenSandbox | `osb`（`opensandbox-cli`，[CLI 文档](https://open-sandbox.ai/cli/)） | `opensandbox`，`from opensandbox import Sandbox`（[Python SDK](https://open-sandbox.ai/sdks/python)） |

E2B 形状的少量方法也可以从 `agent_sandbox.compat` 导入。差异和迁移步骤在[从 E2B 迁移](migrate-from-e2b.md)。OpenSandbox 的 HTTP 字段对照在设计稿 [provider-opensandbox-mapping](../../en/design/provider-opensandbox-mapping.md)。

单元格里的「—」表示这一侧没有对应的公开命令或方法。

## 安装与凭证

| 做什么 | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| 安装 | [CLI binary installation](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/binary-installation.md) | [配套源码安装指南](install-python.md) | `npm install -g @e2b/cli` | `pip install e2b` | `pip install opensandbox-cli` | `pip install opensandbox` |
| 写入凭证 | `abx config set sandbox_api_key` | 环境变量 `ABX_SANDBOX_API_KEY` | `e2b auth login` | 环境变量 `E2B_API_KEY` | `osb config set connection.api_key` | `ConnectionConfig(api_key=…)` 或 `OPEN_SANDBOX_API_KEY` |
| 查看生效配置 | `abx config list` | — | `e2b auth info` | — | `osb config show` | — |

阿里云 AccessKey 保持官方名字 `ALICLOUD_ACCESS_KEY_ID` 和 `ALICLOUD_ACCESS_KEY_SECRET`。OpenSandbox 的连接地址是 `osb config set connection.domain`，对应环境变量 `OPEN_SANDBOX_DOMAIN`。

## 沙箱生命周期

| 做什么 | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| 创建 | `abx create --template <名称>` | `Sandbox.create(template=…)` | `e2b sandbox create [template]` | `Sandbox.create(template)` | `osb sandbox create --image <镜像>` | `Sandbox.create("<镜像>")` |
| 接上已有沙箱 | `abx connect <id>` | `Sandbox.connect(id)` | `e2b sandbox connect <id>` | `Sandbox.connect(id)` | — | `Sandbox.connect(sandbox_id)` |
| 列出 | `abx list` | `Sandbox.list()` | `e2b sandbox list` | `Sandbox.list()` | `osb sandbox list` | 管理器列出沙箱 |
| 查看一个 | `abx info <id>` | `sandbox.refresh_info()` | `e2b sandbox info <id>` | 创建或连接后读对象 | `osb sandbox get <id>` | 连接后读对象 |
| 销毁 | `abx kill <id>` | `sandbox.kill()`，按 id 用 `Sandbox.kill_by_id(id)` | `e2b sandbox kill <id>` | `sandbox.kill()`，按 id 用 `Sandbox.kill(id)` | `osb sandbox kill <id>` | `sandbox.kill()`；`destroy()` 会先终止再关掉本地资源 |
| 延长寿命 | `abx create --timeout <秒>`（创建时设定） | `sandbox.set_timeout(秒)` | `e2b sandbox create --timeout` | `sandbox.set_timeout(秒)` | `osb sandbox renew <id> --timeout 30m` | `sandbox.renew(timedelta)` |
| 暂停 | — | `sandbox.pause()` | `e2b sandbox pause <id>` | `sandbox.pause()` | `osb sandbox pause <id>` | `sandbox.pause()` |
| 恢复 | — | `sandbox.resume()` | `e2b sandbox resume <id>` | `Sandbox.connect` 接上暂停的沙箱 | `osb sandbox resume <id>` | `Sandbox.resume(sandbox_id=…)` |
| 是否在跑 | — | `sandbox.is_running()` | `e2b sandbox list --state running` | `sandbox.is_running()` | `osb sandbox health <id>` | `is_healthy()` |
| 端口地址 | — | `sandbox.network.get_host(port)`、`get_url(port)` | — | `sandbox.get_host(port)` | `osb sandbox endpoint <id> --port 8080` | `sandbox.get_endpoint(port)` |

创建时三家选的不是同一种东西。`abx create --template` 和 `Sandbox.create(template=…)` 用模板名。`e2b sandbox create` 用 E2B 模板（构建结果是快照）。`osb sandbox create --image` 和 `Sandbox.create("python:3.12")` 用镜像地址；OpenSandbox 也可以 `--template` 或 `--snapshot-id`，这三项互斥。

`abx connect` 是一行一个命令的 REPL，不是 PTY。E2B 的 `e2b sandbox connect` 把终端接到沙箱上。OpenSandbox 的持久 shell 在 `osb command session`。

暂停的含义随运行时变化。OpenSandbox 在 Docker 上是 cgroup 冻结，恢复用 `Sandbox.resume`。E2B 的暂停可以在超时后续跑。Agent Sandbox 把 `pause` / `resume` 交给当前提供方。

## 在沙箱里执行

| 做什么 | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| 跑一条命令 | `abx exec <id> <命令>` | `sandbox.commands.run(cmd)` | `e2b sandbox exec <id> <命令>` | `sandbox.commands.run(cmd)` | `osb command run <id> -- <命令>`，短写是 `osb exec` | `sandbox.commands.run(cmd)` |
| 后台命令 | `abx exec <id> --background -- <command>` | `sandbox.commands.start(…, background=True)` | `e2b sandbox exec -b` | `commands.run` 的后台参数 | `osb command run --background` | `commands.run` 后用 `get_command_status` |
| 看后台输出 | — | `commands.stream` | — | 命令流 | `osb command logs <id> <execution-id>` | `commands.get_background_command_logs` |
| 中断 | `abx sandbox process signal` | `commands.send_signal(pid, 15 或 9)` | — | 结束对应进程 | `osb command interrupt <id> <execution-id>` | `commands.interrupt(execution.id)` |
| 列进程 | `abx sandbox process list` | `commands.list()` | — | — | — | — |
| 持久 shell | `abx connect` 的每一行都是新进程 | — | `e2b sandbox connect` | PTY | `osb command session create`，然后 `session run` | `commands.create_session`，`run_in_session`，`delete_session` |
| 交互终端 | `abx connect <id>` 是按行 REPL。CLI 没有 PTY 命令 | `sandbox.get_terminal()` | `e2b sandbox connect` | `sandbox.pty` | — | execd 的 PTY WebSocket |
| 跑一段代码 | — | `sandbox.run_code(code)` | — | `sandbox.run_code(code)` | — | 代码解释器镜像上的 `/code`，SDK 包是 `opensandbox-code-interpreter` |
| 注册命令 | `abx run <id> <命令名> --arg k=v` | `sandbox.run(name, **kwargs)` | — | — | — | — |
| 列出注册命令 | `abx command list <id>` | `sandbox.list_commands()` | — | — | — | — |

Agent Sandbox 只发送信号 15（SIGTERM）和 9（SIGKILL）。OpenSandbox 的 `interrupt` 停的是一次 execd 执行，不是任意数字 pid。

## 文件

| 做什么 | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| 读 | `abx download` 落到本机 | `files.read`、`read_bytes` | — | `files.read` | `osb file cat`、`osb file download` | `files.read_file` |
| 写 | `abx upload` | `files.write` | — | `files.write` | `osb file write`、`osb file upload` | `files.write_files` |
| 列目录 | `abx sandbox files list` | `files.list` | — | `files.list` | — | `files.list_directory` |
| 元数据 | `abx sandbox files stat` | `files.get_info` | — | `files.get_info` 一类的信息对象 | `osb file info` | 列出或搜索结果里的条目 |
| 建目录 | `abx sandbox files mkdir` | `files.make_dir` | — | `files.make_dir` | — | 上传时父目录会建出来 |
| 删除 | `abx sandbox files rm` | `files.remove` | — | `files.remove` | — | `files.delete_files` |
| 移动 | `abx sandbox files mv` | `files.move`、`rename` | — | `files.rename` | — | — |
| 搜索 | `abx sandbox files search` | — | — | — | `osb file search` | `files.search` |
| 是否存在 | — | `files.exists` | — | `files.exists` | — | 读或 stat 失败即不存在 |
| 监听变化 | — | `files.watch` | — | `files.watch_dir` | — | — |
| 签名文件 URL | — | `upload_url` / `download_url` 抛出 `FileOperationError`。`files.upload_url` 仍要 `X-Access-Token` | — | `upload_url`、`download_url` | — | `get_endpoint` 解析的是端口，不是单个文件的签名 URL |

E2B 的文件操作在 SDK 里。命令行用 `e2b sandbox exec` 间接碰文件。OpenSandbox 的 `file download` 在整次下载成功之后才替换本机目标文件。

## 模板

| 做什么 | abx | Agent Sandbox SDK | e2b | E2B SDK | osb | OpenSandbox SDK |
|---|---|---|---|---|---|---|
| 生成本地工程 | `abx template init` | — | `e2b template init` | `Template()` 构建器 | — | — |
| 构建并发布 | `abx template deploy`，分步是 `build` 和 `push` | —（由 CLI 构建和部署） | `e2b template create <名称>`（`template build` 已弃用） | `Template.build` | `osb template create --image … --publish …` | SDK 的模板管理 |
| 列出 | `abx template list` | — | `e2b template list` | 模板 API | `osb template list` | 同上 |
| 查看 | `abx template info` | — | — | — | `osb template get <id>` | 同上 |
| 删除 | `abx template delete` | — | `e2b template delete` | — | `osb template delete` | 同上 |
| 搜索目录 | `abx template search`，安装是 `abx template install` | — | — | — | — | — |
| 快照 | — | 提供方能力 | 模板构建本身就是快照 | `Template.build` | `osb snapshot create <sandbox-id>` | 快照 API |
| 公开或撤回 | — | — | `e2b template publish`、`unpublish` | — | — | — |

三家的「模板」不是同一个对象。Agent Sandbox 的模板是 `template.yaml` 加镜像，默认提供方把它交给阿里云极速版。E2B 的模板构建结果是可直接启动的快照。OpenSandbox 的 `osb template` 是 Kubernetes 运行时上的黄金镜像；Docker 运行时不提供这组接口。OpenSandbox 从快照启动用 `osb sandbox create --snapshot-id`。

## 只有一侧提供的能力

| 能力 | 在哪里 | 另外两家 |
|---|---|---|
| 可切换的沙箱提供方 | `abx provider`，SDK 的 provider 插件 | E2B 和 OpenSandbox 各管自己的控制面 |
| Modal 风格的函数 | `@sandbox`，见[声明式用法](declarative-usage.md) | 没有同名装饰器 |
| 注册命令 | `abx run`、`sandbox.run()` | 没有这一层 |
| Agents API | 沙箱内 HTTP，目前支持 Codex 和 Qwen Code，见 [Agents API](agents-api.md) | 没有这组 `/v1/agents/sessions` |
| MCP | `abx mcp install/start/status/deploy` | E2B 无同名命令组。OpenSandbox 有 `osb skills`，那是它自己的技能包 |
| 出口策略 | 提供方策略 | E2B 用自己的网络限制。OpenSandbox 是 `osb egress get/patch` |
| 凭证保管 | 创建时注入环境变量 | OpenSandbox 另有 `osb credential-vault`，要在创建时打开 `--credential-proxy` |
| 诊断日志 | `abx sandbox system metrics` | `e2b sandbox logs`、`e2b sandbox metrics`。OpenSandbox 是 `osb diagnostics logs/events`，旧入口是 `osb devops` |
| 按端点开关路由 | 沙箱内 `agent-sandbox-server` 的策略，见[细粒度能力](fine-grained-capabilities.md) | 那是沙箱里的 HTTP 服务器，不是 E2B 或 OpenSandbox 的控制面 |

## 相关文档

- [从 E2B 迁移](migrate-from-e2b.md)
- [与其他沙箱工具的对比](comparison.md)
- [CLI 参考](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/reference/cli-reference.md)
- [提供方](providers.md)
