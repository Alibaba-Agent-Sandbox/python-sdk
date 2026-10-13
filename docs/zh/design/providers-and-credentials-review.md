# 提供方与凭证 —— 对抗式评审记录

被评审的文档：[`providers-and-credentials.md`](./providers-and-credentials.md)（规范性设计）及其 CLI 对应文档 `cli/docs/design/providers-and-credentials-cli.md`。

> **关于本译文**：这是[英文评审记录](../../en/design/providers-and-credentials-review.md)的中文版，编号一致；表格逐条对应，以英文版为准。
>
> **流程说明（如实披露）。** 任务要求由全新的评审者进行两轮*独立*评审。编写环境无法启动独立的评审者，所以两轮都由作者以刻意分离的"攻击者"模式完成：每一轮使用不同的视角，只从文档文本出发（不依据作者的意图），并且每个论断都用具体探测对照真实代码（`transport/config.py`、`api/sandbox.py`、`models/*`、原 CLI）检查，而不是重读文字。下面的发现都是初稿中真实存在的缺陷，在写任何代码之前就已在设计中修复。请把本记录当作自我评审；在 CLI 工作者开始之前，仍建议由人或独立方做第三遍评审（见"剩余风险"）。

严重程度：**B** 阻断（设计行不通 / 安全漏洞），**H** 高，**M** 中，**L** 低。

## 第 1 轮 —— 视角：功能完整性、遗漏的键 / 别名、提供方契约缺口、迁移 / 向后兼容

| # | 级别 | 发现 | 处理（位置） |
|---|---|---|---|
| 1.1 | H | 清单遗漏了读取配置的位置：`SANDBOX_LOG_LEVEL`、`SANDBOX_TEMPLATE`/`EBX_TEMPLATE`、server SDK 的 `SANDBOX_*` 变量、MCP 的 `EBX_MCP_*`、`TEAM_ID`/`E2B_TEAM_ID`、`ACREE_INSTANCE_ID`（注意是两个 E）、`--acree-instance-id`。 | 已加入 §1.1–1.7 和别名表；`acree_instance_id` 选项别名；server 端变量明确列为*不在范围内，保持不变*。 |
| 1.2 | H | `api_key` 既是 `config set` 的名字，*也是* TOML 键；`load_config` 的关键字有 `api_base_url`；`domain`/`api_url` 既在顶层又在 `[transport]` 下。第一版别名表只覆盖了环境变量名。 | §5 现在分别有环境变量 / 配置文件 / SDK 关键字 / CLI 选项的别名表；扁平 TOML legacy 键**只在没有 `[transport]` 时**生效（与今天一致）。 |
| 1.3 | H | 把 `api_url` 改名为 `sandbox_base_url` 同时又要求"stdout 不变"，对 `config list` 是矛盾的。 | §6 策略：`config list` 中的重命名就是所要求的变化，并明确指出；其他一切保持静默；`--legacy-names` / `EBX_CONFIG_LEGACY_NAMES=1` 让旧的列表再保留一个版本。 |
| 1.4 | H | 现有测试对 `easy_sandbox.transport.config._ENV_FILE_CANDIDATES/_CONFIG_FILE/_PROJECT_ENV_FILE` 和 `easy_sandbox.api.sandbox.{load_config,create_auth_provider,HttpClient,SandboxProtocol}` 打补丁；测试会构造 `TransportConfig(api_key=…)`。注册表 / 重写可能破坏它们。 | §11 实现映射：保留这些接缝；`TransportConfig` 保留 `api_key`、`api_url`、`domain` 作为构造函数别名和属性（可读写）；`Sandbox` 中的默认（内置）路径继续使用模块级名字。有对应测试。 |
| 1.5 | M | 每个键的存储名必须是它那一个环境变量。 | `ebx config set` 写入这一个名字。没有第二个存储名。 |
| 1.6 | M | 优先级怪癖：今天 dotenv 候选文件按*名字*逐个查询，所以低优先级文件可以通过排在前面的别名获胜。未文档化、无法测试。 | 规范化为**先按层，再按名字顺序**；在 CHANGELOG 和 CLI §0 中说明。没有现有测试固定旧行为。 |
| 1.7 | M | 由 `region` 推导的默认值（`sandbox_base_url`、`sandbox_domain`）有个怪癖：环境变量显式给出 URL 会禁止域名推导。 | 保留并写成规格（§4.5）；泛化为 `[endpoint.derive]`，让插件也能声明。 |
| 1.8 | H | 提供方契约缺少现有 SDK 接口需要的特性：`sandbox.pause`、`sandbox.timeout`、`exec.stream`、PTY、`templates.*`、指标、代码解释器、`files.watch`。没有它们，"不支持时给出类型化错误"无法被证伪。 | 能力注册表（§7.2）有 18 个命名特性，与 SDK 调用一一对应；不支持 → `E8004` `ProviderFeatureNotSupportedError`，在任何副作用*之前*抛出。 |
| 1.9 | H | 沙箱 id 是提供方本地的；会话（`models/session.py`）、`sandbox.yaml`、`@sandbox` 没有 provider 字段 → 会针对错误的提供方恢复会话。 | 会话记住 `provider`；`sandbox.yaml` 增加 `provider:`；限定引用 `provider:id`；冲突 → `E8030`。 |
| 1.10 | M | 插件错误语义未定义 → 无法推导 CLI 退出码 0–6。 | §9 错误表 E8000–E8030 + 两种语言共享的 `epp-error-mapping.json`（EPP 错误码 → SDK 异常 → CLI 退出码）。 |
| 1.11 | M | 没有针对 *Windows* 和无法启动的插件（缺少解释器）的说明。 | `E8021`（`ProviderProcessError`）附 stderr 末尾；拒绝 `.bat/.cmd/.ps1`；`--link` 仅限 POSIX。 |
| 1.12 | L | LLM 键（`qwen_code_*`）在原版中已被移除；表格必须说明它们*没有*复活。 | 列为已移除；`EBX_QWEN_CODE_API_KEY` 只保留为 legacy 环境变量别名。 |

## 第 2 轮 —— 视角：用户体验、git 插件的安全 / 供应链、可测试性、多提供方边界情况

| # | 级别 | 发现 | 处理 |
|---|---|---|---|
| 2.1 | **B** | **提供方之间的凭证泄露。** 如果通用的 `sandbox_api_key`（`EBX_SANDBOX_API_KEY`）被传给任意默认提供方，`ebx provider default evil`（或插件更新）会窃取阿里云密钥；反过来会把插件的密钥发到阿里云端点。 | §4.6 隔离规则：通用沙箱键属于内置提供方。非内置提供方只能通过清单的 `[core] inherit` ∩ 安装回执中保存的已同意列表获得它们；同意界面打印警告行；`provider doctor` 对重复使用发出警告。 |
| 2.2 | **B** | **安装不得执行代码，而 git 自己就可能执行。** `git clone` + checkout 可能运行钩子 / 过滤器 / LFS smudge，跟随符号链接，并写到目标之外。 | §8.2：`--no-checkout --filter=blob:limit`，隔离的 git 配置（无系统 / 全局配置，`protocol.allow` 白名单，禁止重定向，不从环境使用凭证助手），在用 `cat-file --batch` 写入 blob **之前**用 `ls-tree -z -l` 校验*每一个*条目（无符号链接 / 子模块 / 超大 / 大小写冲突 / 穿越）；完全不做工作树检出。 |
| 2.3 | H | 标签 / 分支安装是可变的；基于标签的"已固定"说法是假的。 | 只有 40 位十六进制提交或 `--sha256` 目录树摘要才算固定；标签 / 分支是 `unpinned`，非交互时没有 `--allow-unpinned` 就拒绝；已固定安装的 `update` 需要显式的新 `--ref`。 |
| 2.4 | H | 安装后篡改（编辑 `~/.ebx/providers/<id>` 里的文件）。 | 目录树摘要记录在回执 `.ebx-install.json` 中；**每次**启动前重新校验（`E8011`）；与语言无关的 `tree-digest-vectors.json`。 |
| 2.5 | H | argv / 环境 / 日志中的密钥：`--opt token=…` 在 `ps` 里可见；插件继承全部环境；插件 stderr 回显密钥；`initialize` 可能被记录。 | `--opt` 拒绝密钥字段；启动环境被清理（白名单 + 清单的 `env_passthrough`，后者不得包含 `EBX_*`/`E2B_*`/`ALICLOUD_*`）；密钥只通过 stdin 上的 `initialize` 请求传递；stderr 被遮蔽并去除 ANSI；`initialize` 从不记录。 |
| 2.6 | H | 清单里的 `[security]` 块看起来像沙箱，其实不是。用户会过度信任它。 | 到处都标注为**建议性 / 自我声明**（同意界面标签"由插件声明（不强制执行）"，§8.5 说明）；OS 级约束列为未来工作。 |
| 2.7 | H | 输出歧义：`ebx list` 打印裸 id；切换默认提供方后，用户会把 id 粘贴到错误的提供方。但禁止改变现有用户的输出。 | 只有当**环境和生效**提供方都是 `alicloud-express` 时才使用旧格式；否则使用限定的 `provider:id`，JSON 增加 `provider` 键。 |
| 2.8 | M | `--link` 是未固定代码的漏洞。 | 需要 `--yes`；信任级别 `link`；仅 POSIX；每次启动都重新读取清单和完整性。 |
| 2.9 | M | `[auth]` 模型无法表达"(a AND b) OR c"（如 AK+SK 或一个 token）→ 错误的"缺少凭证"报错。 | `[auth] any_of = [["a","b"],["c"]]`；驱动 `E1003` / doctor。 |
| 2.10 | M | 可测试性：没有可测试的插件；安装器测试会需要网络。 | 参考插件 `examples/providers/{e2b-compatible,local-process}`；临时裸 git 仓库 + `--allow-insecure-transport`（`file://`）用于安装器测试；**金丝雀测试**（插件被执行就会写文件——安装后绝不能存在）；任何插件都能运行的 `providers.testing` 契约套件。 |
| 2.11 | M | 两个实现（Python + Node）会漂移。 | 一致性夹具（`config-keys.json`、`config-resolution-vectors.json`、`tree-digest-vectors.json`、`epp-error-mapping.json`、`migration-vectors.json`）由 Python 生成，逐字节镜像到 CLI 仓库，并有同一性测试。 |
| 2.12 | M | 多提供方：有一个提供方出故障时的 `list --all-providers`；把提供方 A 的沙箱记录交给提供方 B；`--provider` 与 `Q:id` 不一致。 | 部分失败语义（警告并继续；按最佳结果退出）；冲突用 `E8030`；会话记住提供方。 |
| 2.13 | L | 体验缺口：`--provider` 没有拼写提示，`ebx --help` 没提到提供方，`ebx info` 没说是哪个提供方回答的。 | 已加入（CLI 规格 §0、§4.1）。 |
| 2.14 | L | Windows 的 `.bat` 启动器需要 shell → shell 注入面。 | 被清单校验拒绝；启动始终是 `shell:false` / argv 列表。 |
| 2.15 | L | 插件名 / id 可能与配置表名或 Windows 保留名冲突。 | 保留 id 列表（`core`、`transport`、`providers`、`shortcuts*`、`con`、`nul` 等）随 JSON 导出一起发布。 |

## 剩余风险（已接受并已文档化）

* 插件就是普通程序：固定 + 同意 + 环境清理可以降低但不能消除供应链风险。本版本没有 OS 沙箱。
* `exec` 提供方每次 CLI 调用要多一个进程（启动延迟）；长期运行的守护进程（EPP/2）是未来工作。
* 上面的自我评审局限：没有独立评审者看过本文档。

## 实现阶段补充

在实现 Python 一侧时发现的问题（第 3 轮）：

| # | 发现 | 处理 |
|---|---|---|
| I1 | EPP `-32002` 被映射到 `SandboxCreationError`（E2000，退出码 1），与"未找到"文档中的退出码 4 矛盾。 | 新增 **E8005 `ProviderResourceNotFoundError`**。`-32002` 映射到 `data.sdk_code` 指定的类，否则为 E8005；`exit_code_for` 和 `epp-error-mapping.json` 已更新（§7.4、§9）。 |
| I2 | 契约测试套件在一个 `sandbox.kill` 对未知 id 抛错（kill 不幂等）的插件上失败。 | 参考插件的 `kill` 是幂等的，宿主适配器在 kill 上吞掉 E8005，套件检查幂等性。 |
| I3 | 对没有 envd 的提供方的沙箱，`Sandbox.list_commands` 抛出 `TokenExpiredError`。 | 标记 URL `epp://<provider>/<id>`；对它跳过 envd 认证 / 列出。 |
| I4 | 正常退出的插件可能留下仍在运行的孙进程。 | `EppClient.close` 在退出之后也会回收进程组，而不仅仅是在超时 / 崩溃时。 |
| I5 | 运行 Python 插件会往受摘要校验的目录里写 `__pycache__`，导致第二次启动完整性失败。 | `PYTHONDONTWRITEBYTECODE=1` 加入清理后的环境（§8.3）；`data/` 保留给插件自己的状态并排除在摘要之外。 |
| I6 | 没有 API 可以释放 `Sandbox` 持有的插件进程。 | `Sandbox.close()` / `close_sync()`。 |
| I7 | `apply_migration` 在移走所有键后留下空的 `[transport]` 表。 | 变空时删除；由 `migration-vectors.json` 覆盖。 |
| I8 | 设计写的是"有效能力 = 模板 ∩ 提供方"。预先求交集会增加第二个事实来源，可能与提供方不一致。 | §7.2 现在说明模板能力不变，提供方缺少特性时在调用时抛 E8004。 |
| I9 | `sandbox.yaml provider:` 和 `@sandbox(provider=...)` 触及声明式层，而另一个工作流正在并行编辑它。 | 推迟并在 §7.8 标为"已规划"；列为后续事项。 |
| I10 | 清单示例使用了 `command = ["python3", "provider.py"]`；裸名字按 `PATH` / CWD 解析，只有 `./x` 锚定在插件目录内。 | 示例使用 `./provider.py`。 |
| I11 | 文档说 dotenv 分层"不变"；有一个边角（两个 `.env` 文件对同一个键使用不同名字）确实会变。 | 在 `reference/configuration.md` 和 CHANGELOG 里作为唯一的行为变化说明。 |

实现阶段结束时的验证：新增和受影响的模块全部通过（`tests/test_utils/test_config_keys.py` 144、`tests/test_transport/`（含 `test_config_names.py` 92）、`tests/test_providers/` 清单 51、安装器 87、EPP 33、sandbox-provider 15、注册表作用域 33、一致性 106；连同已有的 transport 测试共 738 个）；client-sdk 其余测试通过（1846 个），除了在另一个工作流的 `routes_agents` 模块修改中途导入 server 包的模块（循环导入，与提供方无关）；所有新增文件的 ruff 和 mypy 均无告警。
