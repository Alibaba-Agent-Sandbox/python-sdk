# 提供方编写体验评估 —— 接入一个新提供方有多难？

> **历史记录。** 本页评估的是第一个 `exec` 插件。现行的 OpenSandbox 适配器是 [provider-opensandbox-mapping.md](provider-opensandbox-mapping.md) 里的 `node` 提供方。Node 提供方架构：[node-provider-architecture.md](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/zh/design/node-provider-architecture.md)。

> **状态**：评估（基于证据），已应用一轮修复（见第 10 节） · **对象**：`opensandbox` exec 提供方插件（[awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox)）。插件源码在该目录，不在本仓库。评估依据 SDK 文档，并在真实的本地 OpenSandbox 服务上驱动 · **配套文档**：[providers-and-credentials.md](providers-and-credentials.md)（规范性设计）、[provider-opensandbox-mapping.md](../../en/design/provider-opensandbox-mapping.md)（调研，仅英文）、`../guide/providers.md`（使用/编写指南） · **English**：[../../en/design/provider-authoring-evaluation.md](../../en/design/provider-authoring-evaluation.md)
>
> **关于本译文**：这是英文评估文档的中文版，章节编号一致；两者有差异时以[英文版](../../en/design/provider-authoring-evaluation.md)为准。
>
> **方法**：由一位作者（AI 编码代理）从仓库文档和参考插件出发编写插件，并记录文档、宿主适配器或工具链迫使其绕路的每一处。结论标注为 **[ran]**（实际运行复现，命令见第 9 节）、**[read]**（读源码或文档得出）或 **[est]**（估算）。“时间”为会话的挂钟估算，并非精确计时。

---

## 0. 结论

接入一个提供方**可行，整体体验不错**：协议很小，清单（manifest）承担了大量琐碎工作（配置模式、环境变量别名、机密标记、授权确认、完整性校验），安装器/回执机制在所有流程中表现正确，仅有两个缺陷（第 5 节）。一个完整插件（生命周期、暂停/恢复、流式执行、9 种文件操作、进程控制、端口 URL；约 1.7 千行无依赖 Node 代码加约 1.3 千行测试）约一小时即可达到契约测试全绿，再花数小时完成全部联机覆盖。

摩擦集中在三个地方，且都不在协议本身：

1. **宿主侧抽象比规范更薄。** `Sandbox.create` 写死 `secure=True`，没有按次创建的提供方选项，从不调用 `ports.url`，`commands.start()` 惰性启动，`run_code` 没有降级路径（第 4 节）。
2. **编写者工具链文档不足且部分失效。** 文档中的契约测试命令收集不到任何测试；测试套件仅 5 项；没有脚手架、没有模拟宿主、没有给插件作者的 EPP 客户端，每位作者都要重写 JSON-RPC 测试客户端（第 3、6 节）。
3. **跨组件漂移。** 规范、Python 适配器、参考插件和（即将有的）CLI 之间的参数名与可选方法没有被同一份机器可读的模式固定（第 3.3 节）。

---

## 1. 产出

| 项目 | 结果 |
|---|---|
| 运行时选择 | 无依赖 Node ESM（Node >= 20，内置 `fetch`）。调研文档*建议*使用标准库 Python，但并未强制。选择 Node 是因为 `abx` CLI 本身是 Node 程序（CLI 用户无需额外运行时），`fetch` 加 `ReadableStream` 让 SSE 流式处理很简单，而安装器本来就禁止依赖。代价：仅用 Python SDK 的用户需要 `node` 在 `PATH` 中；改写成 Python 版本是机械翻译。 |
| 能力 | `sandbox.lifecycle`（create/connect/get/list/kill）、`sandbox.timeout`、`sandbox.pause`（pause/resume）、`exec.run`、`exec.stream`、`process.manage`（list/kill/signal；无 stdin）、`files.rw`（含范围读取、带 mode 写入、list、stat、mkdir、remove、move；扩展 search/chmod）、`ports.url`、`sessions`（后台命令）。声明为不支持（E8004）：`pty`、`code.interpret`、`templates.*`、`files.watch`、`files.transfer`、`process.stdin`。 |
| 配置 | 13 个清单字段；规范名称 `ABX_OPENSANDBOX_*` 加原生别名（`OPEN_SANDBOX_API_KEY`、`OPEN_SANDBOX_DOMAIN` 等）。机密（`api_key`、`registry_password`）标记为 `secret`。 |
| 规模 | `provider.mjs` + `src/` 共 1 670 行；测试 1 262 行（24 单元、21 模拟服务、2 联机 EPP、5 套件、10 个 pytest SDK 场景）。 |
| 吸收的平台特性 | execd 上传要求元数据部分为*文件*部分；`mode` 是以十进制整数书写的八进制数字；DELETE `/files` 与 `/directories` 按类型区分；第二次 kill 返回 404（吞掉以保持 `kill` 幂等）；TTL 最小 60 秒（截断）；metadata 必须符合 Kubernetes 标签规则（提前校验，`-32006`）；`renew-expiration` 接受绝对时间（取自服务端 `Date` 头，因此不受客户端时钟偏差影响）；旧版 execd v1.1.0 无 `argv` 且会吞掉换行（已检测并处理）。 |

---

## 2. 测试结果（本地 OpenSandbox 服务 1.1.1，Docker 运行时）

| 层级 | 命令 | 结果 [ran] |
|---|---|---|
| Node 单元 + 模拟服务 | `node tests/run.mjs` | 45/45 通过 |
| Node 联机（直接 EPP/1） | `OPENSANDBOX_LIVE=1 node tests/run.mjs live` | 2/2 通过（完整生命周期/执行/文件/端口/暂停/错误映射，错误密钥） |
| 共享契约测试套件 | `pytest ... --provider-under-test opensandbox`（使用 6.1 节的收集变通） | 5/5 通过（**现用 `python -m agent_sandbox.providers test opensandbox` 为 18/18**，第 10 节） |
| SDK 场景（`Sandbox.create(provider="opensandbox")`） | `pytest tests/contract` | 10/10 通过（5 套件 + 5 场景：流式顺序与增量到达、退出码、env/cwd、Unicode 文件、缺失文件 `E4001`、`set_timeout`、暂停/恢复、进程列表、`E8004`、未知 id） |
| 配置优先级 | `provider_e2e.py --stages env` | 6/6：规范名称优先于原生名称（base URL 与 API key）；仅原生名称也足够；错误密钥为 `E1001` |
| 安装流程 | `provider_install_e2e.py` | 36/36 检查通过，另有 2 项非致命发现（第 5 节）（**现为 39/39，无发现**，第 10 节） |
| 全部 | `provider_e2e.py` | 12/12 |

安装流程覆盖：本地路径安装；固定到 40 位提交的 `file://` 裸仓库安装（无 `--allow-insecure-transport` 被拒；非交互式未固定被拒）；回执 `tree_sha256` 与已安装目录、源目录的独立摘要一致（git 与本地安装摘要相同）；篡改检测（`doctor` 完整性检查失败，恢复后通过；`data/` 不参与摘要）；更新（`pinned` 空操作、`--check`、无授权被拒、`--yes` 生效、重复更新幂等、新版本握手失败时回滚）；卸载保留 `data/`，`--purge` 清除；`--link` 需要 `--yes`。

---

## 3. 评分卡（1 = 受阻，3 = 可用但需绕路，5 = 毫无摩擦）

| 维度 | 分数（原始 → 第 10 节之后） | 原因（原始评估） |
|---|---|---|
| 协议清晰度（EPP/1 规范） | 4 → **4.5** | 一张表列出所有方法、参数、结果与特性；约定（线上单位为秒、`exec.output`/`exec.exit` 顺序、幂等重试集合、8 MiB 行限制）都有说明。不足：可选/扩展方法、`files.move` 参数名、分块（见第 6 节）。 |
| 清单与配置模式 | 4.5 | 声明式字段、`secret`、`env` 别名、`choices`、`default`、`core.inherit`、`security` 块；宿主负责解析优先级。唯一的坑：默认值会被*下发*给插件，因此 `base_url` 上的清单默认值会悄悄压过 `domain` 替代写法，文档未提及。 |
| 错误模型 | 4 | JSON-RPC 码映射到稳定的 SDK 码，带 `retryable` 标志和 `sdk_code` 提示。不足：“连接被拒绝”没有对应码（表现为通用 `E8000`）；插件可指定的 `sdk_code` 取值只有示例（`E2001`、`E4001`），完整列表是 `providers/epp.py` 中的 `_SDK_CODE_CLASSES`。 |
| 安装器、存储、信任 | 4 → **4.5** | 所有流程均正确且严格；授权与回执设计出色。有两个缺陷（第 5 节）和若干缺失的 CLI 参数。 |
| 契约测试 / 编写者工具 | 2 → **4** | 套件存在但按文档执行收集不到测试，仅 5 项，不覆盖流式/暂停/超时/进程/文件边界，没有模拟宿主，没有脚手架或 `abx provider init`。 |
| 宿主适配器（抽象完整度） | 3 → **4** | exec 适配器覆盖核心；但见第 4 节：写死 `secure`、无按次创建选项、惰性启动、`ports.url` 未接线、无 `code` 降级。 |
| 参考插件 | 3.5 | `local-process` 精简易读；但它是 Python，不涉及 HTTP/流式/认证，也未体现真实世界的问题（时钟偏差、重试、取消）。 |
| 文档可发现性 | 3 → **3.5** | 设计文档详尽但长达 700 多行；编写路径分散在设计、指南与代码中；指南的 *Writing a provider* 一节只展示了清单，没有首次 EPP 交互或必须响应哪些方法的完整演示。 |
| 可调试性 | 3.5 | stderr 被捕获并在崩溃时展示；`doctor` 很好用。没有请求回放或 `--trace-epp`。 |
| 离线可测性 | 3 → **3.5** | 作者必须自己编写模拟服务和 EPP 客户端（本插件均已提供，可复用）。 |
| **总体** | **3.5 → 4.0 / 5** | 各项变化见第 10 节。 |

### 3.1 首个可用插件所需时间 [est]

| 里程碑 | 时间 | 说明 |
|---|---|---|
| 阅读设计 + 调研 + 参考插件 | 约 15 分钟 | 调研文档完成了大部分思考；没有它，目标平台 API 的摸底才是最耗时的部分，而不是 EPP。 |
| 骨架：清单 + `initialize` + `doctor` 通过 | 约 10 分钟 | 以 `local-process` 为模板即可。 |
| 生命周期 + 执行 + 文件，首次套件全绿 | 约 35 分钟 | 套件曾因缺少 `sandbox.connect` 失败（规范写 `connect` *或* `get`，宿主实际调用 `connect`）。 |
| 完整能力集、错误映射、模拟 + 联机测试 | 数小时 | 几乎全部来自目标平台的特性（第 1 节），与 EPP 无关。 |

对于 REST API 干净、没有 execd 那类特性的平台，有脚手架的话 150 行的插件约 30 分钟可完成；目前缺少脚手架和模拟宿主，大约多出 20 分钟。

### 3.2 做得好的地方

* `initialize` 握手直接下发解析后的配置，插件里完全不需要配置加载代码。
* 机密不会出现在 argv/环境变量中；配置模式已标记机密，因此错误信息脱敏很容易。
* `doctor` 在创建任何沙箱前就发现了真实错误（清单字段错误、入口路径错误）。
* `epp://<provider>/<id>` 标记 URL 干净地为 exec 提供方禁用了 envd。
* 每次启动校验回执与摘要，免费获得篡改检测。

### 3.3 跨组件漂移（主要的长期风险）

同一套协议表面在四处被描述：设计表、Python 适配器、参考插件和（即将有的）Node CLI。已见例子：`files.move` 的参数（表中为 `path…`，适配器为 `source`/`destination`，插件两者都接受）；`sandbox.connect` 与 `sandbox.get`；`exec.start` 的字符串 `process_id` 与 `ProcessInfo`/`kill` 的整数 `pid`；插件实现但表和宿主适配器都未提及、因此目前无人调用的可选扩展（`files.search`、`files.chmod`、`exec.start{detached}`）。用一份 JSON Schema（或把现有一致性夹具扩展为每个方法的请求/响应模式）即可消除这一类缺陷。

---

## 4. 抽象泄漏（作者无法影响的宿主侧行为）

| # | 泄漏 | 影响 | 建议修复 |
|---|---|---|---|
| L1 | `Sandbox.create` 总是发送 `secure: true` | 插件无法遵从用户的 `secure=False`；本插件只能忽略该标志并增加 `secure_access` 配置字段（仅 Kubernetes 网关） | 仅在用户设置时才发送 `secure`，并说明其对非 envd 提供方的含义 |
| L2 | 没有按次创建的提供方选项 | 镜像拉取策略、网络策略、仓库认证、平台、GPU 只能是全局配置字段 | 把 `Sandbox.create` 已接受的 `provider_options` 以 `options` 传入 `sandbox.create` |
| L3 | 从不调用 `ports.url` | `network.get_url` 由客户端依据沙箱域名计算，插件的 `ports.url` 在 SDK 中成了死代码；只有 CLI 接线时才有用 | 声明该特性时，让 `network.get_url` 走 `ports.url` |
| L4 | exec 提供方的 `commands.start()` 是惰性的 | 只有迭代返回的 `StreamReader` 时才发送 `exec.start`；“后台启动再轮询”会静默无效 | 适配器中立即发送 `exec.start` 并缓冲到队列 |
| L5 | `ProcessInfo` 只有 `pid`、`command`、`status` | 插件侧数据（用户、启动时间、CPU）被丢弃 | 透传可选字段 |
| L6 | exec 提供方未声明 `code.interpret` 时 `Sandbox.run_code` 抛 `E8004` | 虽然 `exec.run` 能做到，却没有可移植的“在沙箱里运行 Python”降级 | 适配器中提供基于 shell 的可选降级（`python3 -c`），由特性开关控制 |
| L7 | 每次创建都警告 `Could not resolve capabilities for template 'base'` | 所有非内置提供方每次创建都产生日志噪声 | 对非内置提供方跳过解析，或解析为提供方声明的特性 |
| L8 | exec 流的 `process_id` 是字符串，而 `commands.kill(pid)` 是 `pid: int` | 无法暴露数字 pid 的插件（execd 命令 id）无法通过 SDK 被终止 | `kill` 接受 `str | int` 并透传 |
| L9 | `files.read/write` 无分块 | 8 MiB 行限制使单个文件约 6 MiB 封顶；插件把读取限制在 4 MiB | 规范中为 `files.read` 增加 `offset/length`（插件已支持）并增加分块写（`append`） |
| L10 | 服务不可达表现为通用 `E8000` | `base_url` 写错时用户只看到“提供方失败” | 增加连接失败码（或 `sdk_code`）供插件使用 |

---

## 5. 在安装器中发现的缺陷（不在插件中）

| # | 缺陷 | 证据 | 修复 |
|---|---|---|---|
| B1 | **更新回滚时 `data/` 丢失。** `_swap_in` 在 `verify` 之前就把旧 `data/` 移入暂存目录；验证失败时删除 `final`（此时含 `data/`）并恢复回收站中的副本，而后者已不含 `data/`。 | `provider_install_e2e.py` 输出 `[BUG ] data/ survives an update that was rolled back...` | 在 `remove_tree(final)` 之前把 `data/` 移回回收站副本（或在 `verify` 通过前改为复制）。 |
| B2 | **`python -m agent_sandbox.providers update` 没有 `--allow-insecure-transport`。** 以该参数安装的 git 源无法在命令行更新（E8012）；回执也没有记录使用过该参数。 | `[GAP ] CLI 'update' cannot reach a file:// source` | 为 `update` 增加该参数；可考虑在回执中记录 `insecure_transport: true`，以便授权后 `update` 复用。 |
| B3 | 文档中的契约测试命令收集到 0 项测试（6.1 节）。 | `--pyargs agent_sandbox.providers.testing` 什么都找不到，因为模块名（`testing.py`）和类名（`ProviderContractTests`）都不匹配 pytest 默认模式 | 见 6.1 节。 |

---

## 6. 文档缺口

### 6.1 契约测试说明有误

`guide/providers.md` 写的是 `pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.testing --provider-under-test my-cloud`。它会**收集到 0 项**（pytest 退出码为 5，宽松的 CI 步骤可能忽略）。紧邻其上的子类写法可用。命令行形式需要：

```bash
pytest -p agent_sandbox.providers.testing -o python_classes=ProviderContractTests \
       -o python_files=testing.py --pyargs agent_sandbox.providers.testing \
       --provider-under-test my-cloud
```

子类写法（`class TestMine(ProviderContractTests): provider_id = "my-cloud"`）即 [`opensandbox/tests/contract/test_contract.py`](https://github.com/alibaba-agent-sandbox/awesome-providers/blob/main/opensandbox/tests/contract/test_contract.py) 所用。建议：让套件默认可被收集（`__test__ = True`，把类改名为 `TestProviderContract`，或提供带 `pytest_collect_file` 的 `pytest11` 入口点），并在文档示例中把“收集到 0 项”视为错误。

### 6.2 缺失或难以找到的信息

| # | 缺口 | 应放在哪里 |
|---|---|---|
| D1 | 清单中声明的默认值会随 `initialize.config` 下发；在有替代写法的字段（`base_url` 与 `domain`）上设默认值会使替代写法失效 | 清单参考，配置字段 |
| D2 | `data.sdk_code` 可接受值的完整列表（文件用 `E4001`，模板用 `E2001` 等）；目前只有代码里列出，且文件缺失时裸的 `-32002` 会变成“沙箱不存在”（E8005） | EPP 错误表 |
| D3 | 宿主调用 `sandbox.connect`；只提供 `get` 不够 | EPP 方法表（标明必需与可选） |
| D4 | 每个特性需要哪些方法，以及宿主可能调用哪些可选扩展（`exec.start{detached}`、`files.search`、`files.chmod`） | 特性表增加“方法”列 |
| D5 | 对正在运行的流的*请求* id 发送 `$/cancel` 时 `exec.start` 应做什么（插件必须终止进程）；规范只说明存在取消 | EPP 章节 |
| D6 | 更新的重新授权规则，以及已固定的安装在不带 `--ref` 时更新为空操作 | `guide/providers.md` 的更新一节（规则有，空操作未提） |
| D7 | `data/` 不参与摘要，而 `tests/` *参与*（插件测试会使每次安装变大并改变摘要） | 编写检查清单 |
| D8 | 以 `install --link --yes` 作为开发循环，已在*安装*一节记录，但 *Writing a provider* 没有链接过去 | 编写指南交叉链接 |
| D9 | 指南的 *Testing a plugin* 只覆盖契约套件：没有模拟宿主辅助、没有示例 EPP 客户端、没有离线测试建议 | 新增“测试你的插件”一节；本插件的 `tests/epp-client.mjs` 与 `tests/mock/` 可作为起点 |
| D10 | 提供方 id 含连字符/下划线时的规范环境变量名，以及 `ABX_<ID>_*`、原生别名、`.env`、TOML 之间的优先级 | 环境变量指南（表有，别名规则是隐含的） |
| D11 | 在含有无关 `conftest.py` 的目录运行仓库 `pytest` 会在收集阶段失败；作者需要 `--noconftest`/`--confcutdir` | 贡献文档 |
| D12 | 当工作区对 `server-sdk` 使用 `uv` source 时，`pip install -e client-sdk` 失败 | 贡献文档 / 打包 |

### 6.3 已应用与待处理的文档修复

已应用（我负责的文档）：opensandbox 插件 README 现位于 [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox)（`README.md` / `README.zh-CN.md`：安装、配置、能力矩阵、测试层级、已知限制）、`e2e/opensandbox/README.md`（如何运行提供方 E2E；测试工具会安装插件，不内置一份副本）、`examples/providers/README.md`（指向该目录）。**待处理**（文件归其他工作流所有）：6.1 节全部内容、D1–D12，以及第 7 节的修正。

---

## 7. 具体修复建议（按优先级）

| 优先级 | 修复 | 涉及 | 规模 |
|---|---|---|---|
| P0 | B1 更新失败时的数据丢失 | `installer._swap_in` | 约 5 行 + 测试 |
| P0 | 修正契约测试命令并使套件可被收集（6.1 节） | `providers/testing.py`、`guide/providers.md`（中英） | 小 |
| P1 | `provider update --allow-insecure-transport`（B2）及 `abx provider update` 对齐 | `providers/__main__.py`、CLI | 小 |
| P1 | L1/L2：遵从 `secure`，把 `provider_options` 传入 `sandbox.create` | `exec_provider.ExecSandboxProtocol.create`、规范表 | 小 |
| P1 | L4：`ExecProcessProtocol.start` 立即发送 `exec.start` | `exec_provider.py` | 小 |
| P1 | L3：让 `network.get_url` 走 `ports.url` | `Sandbox`/network API | 中 |
| P2 | 机器可读的方法模式（每个方法一份 JSON Schema，SDK、CLI、套件共用），并据此生成套件测试 | `fixtures/`、`testing.py` | 中 |
| P2 | 扩展套件：流式顺序与唯一退出、取消、`set_timeout`、暂停/恢复、进程 list/kill、文件边界（二进制、缺失 -> `E4001`、覆盖）、幂等 kill、错误参数 `-32006` | `providers/testing.py` | 中 |
| P2 | 作者脚手架：`python -m agent_sandbox.providers init <id> --runtime node|python`，生成清单、入口和 EPP 测试客户端 | 新模块 | 中 |
| P2 | 在 EPP 表中标明必需/可选方法与扩展方法（D3、D4） | `providers-and-credentials.md` | 小 |
| P3 | L5–L10 | `exec_provider.py`、models | 各自较小 |
| P3 | `--trace-epp` / `ABX_EPP_TRACE=1` 记录请求/响应（已脱敏） | `providers/epp.py` | 小 |
| P3 | 摘要中排除 `tests/` 或写入文档（D7） | `store._walk_regular`、文档 | 小 |

---

## 8. 对 EPP/1 设计本身的观察

* **优点**：基于 stdio 的 JSON-RPC 在任何语言中都易于实现（Node 版 EPP 循环仅 108 行）；用通知做流式，无需第二条通道；宿主仅对幂等方法重试，规则干净。
* **优点**：混合（envd URL）模型意味着已经支持 envd 的平台完全不需要数据面代码。
* **不足**：除清单 `features` 列表外没有能力协商，沙箱级能力（例如“该镜像带有代码解释器”）无法表达（调研文档把它列为缺口 4）。
* **不足**：没有版本化的方式新增可选方法；插件新增的扩展（`files.search`）只有匹配的宿主才会调用。
* **缺失**：慢速创建（拉镜像需数分钟）的进度通知；规范列出了 `progress` 通知，但适配器没有向用户呈现。

---

## 9. 复现本评估

```bash
cd e2e/opensandbox && ./local-up.sh up && eval "$(./local-up.sh env)"
python3 provider_e2e.py                 # 未设置 ABX_OPENSANDBOX_PLUGIN 时会克隆 awesome-providers
python3 provider_install_e2e.py
git clone --depth 1 https://github.com/alibaba-agent-sandbox/awesome-providers.git
cd awesome-providers/opensandbox && node tests/run.mjs
```

各脚本读取的环境变量见 `e2e/opensandbox/README.md`（不会在任何地方写入机密；本地 API key 是一次性的开发用值）。

---

## 10. 处理状态

下列修复均已在 SDK 中完成，并对本地 OpenSandbox 服务重新验证（`provider_install_e2e.py`：39/39 项检查，没有任何 `[GAP]`/`[BUG]` 行；`provider_e2e.py`：12/12，其中包含 18 个契约测试和 23 个 SDK 场景；Node 插件测试：46/46）。

| 项目 | 状态 | 变更 |
|---|---|---|
| B1 回滚时丢失 `data/` | **已修复** | `installer._swap_in` 在恢复旧目录树之前先把 `data/` 移回，两条失败路径（`verify` 失败、交换失败）都覆盖。回归测试分别注入这两种失败，并比对文件内容与权限。 |
| B2 `update` 缺少 `--allow-insecure-transport` | **已修复** | `python -m agent_sandbox.providers update` 接受 `--allow-insecure-transport` 和 `--no-verify`。回执刻意不记住该参数（见指南）。 |
| B3 / 6.1 契约命令收集到 0 项 | **已修复** | `python -m agent_sandbox.providers test <id>`（收集到 0 项时失败，并与当前目录的 pytest 配置隔离）以及 `pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract --provider-under-test <id>`。指南、设计文档及中文版已更正。 |
| 套件仅 5 项测试（第 3 节） | **已修复** | 18 项测试：exec 流顺序与唯一 exit、退出码 / stderr / 环境变量、超时强制执行、二进制与 Unicode 文件、目录与移动、类型化未找到、kill 幂等、`set_timeout`、暂停 / 恢复、进程列表、`ports.url`、未声明特性的 E8004、密钥脱敏；支持 `--provider-option KEY=VALUE`。 |
| L1 写死 `secure=True` | **已修复** | `Sandbox.create(secure=None)`：仅当调用者设置时才发给插件；内置提供方仍按 `True` 处理。 |
| L2 没有按次创建的选项 | **已修复** | `provider_options` 以 `options` 的形式（去掉密钥字段）送达 `sandbox.create`。OpenSandbox 插件对每次创建接受一个白名单（`network_policy`、`platform`、`default_image` 等），并且绝不让 `options` 改变服务地址或密钥。 |
| L3 从不调用 `ports.url` | **已修复** | 当声明了 `ports.url` 时，`await sandbox.network.resolve(port)` / `resolve_url(port)` 会询问插件。`get_url()` 保持同步且在本地计算（不破坏 API）。 |
| L4 惰性的 `commands.start()` | **已记录，未更改** | 这不是提供方层的缺陷：内置的 envd 流也以完全相同的方式惰性，所以“急切的 exec 适配器”会让各提供方行为不一致。指南对此做了说明，并给出 `nohup ... &` / `sessions` 的替代做法。 |
| L8 `process_id` 字符串 vs `pid` 整数 | **已修复** | `pid` 端到端都是 `int \| str`（`ProcessInfo.pid`、`commands.kill/send_signal/send_input`、exec 适配器）；方法表写作 `string \| integer`。 |
| 3.3 漂移：`files.move` 参数名、`connect` vs `get` | **已修复** | 一张机器可读的表 `epp-methods.json`（逐字节镜像到 CLI 仓库，并有同一性测试）。适配器与它做双向测试。`files.move` 是 `source`/`destination`；`sandbox.get` 必需，`sandbox.connect` 可选，收到 `-32601` 时自动回退到 `get`。 |
| 插件永不结束命令时静默卡住 | **已修复**（扩展套件时发现） | 流式适配器抛出的是裸 `asyncio.TimeoutError`；现在抛出 `CommandTimeoutError`（E3001）。 |
| D1、D2、D3、D4、D5、D6、D7、D8、D9、D11 | **已修复（文档）** | 指南的“编写提供方”/“测试插件”，以及设计文档的方法表与约定（中英文）。D7 是记录而非更改（插件的 `tests/` 仍计入摘要）。D11 在测试一节中加了说明。 |
| D10、D12 | 未完成 | 带连字符 id 的环境变量规则已在配置参考中；`uv` 来源的打包问题属于贡献文档，超出提供方文档范围。 |
| L5 额外的 `ProcessInfo` 字段、L6 `run_code` 回退、L7 能力解析日志噪音、L9 分块文件、L10 连接被拒绝的错误码 | 未完成 | 记录待后续处理；可选的扩展参数（`files.read{offset,length}`、`files.write{mode,append}`）已写入方法表，插件可以先于宿主实现。 |
| 脚手架（`provider init`）、`--trace-epp`、每个方法的结果模式 | 未完成 | 参数有模式检查；结果仅作描述。 |

**评分变化。** 契约测试 2 → 4（可收集、18 项测试、一条命令）；宿主适配器 3 → 4（L1-L4、L8）；安装器 4 → 4.5（B1、B2）；协议清晰度 4 → 4.5（一张带必需 / 可选 / 扩展标记及精确名称的表）；文档可发现性与离线可测性各 +0.5。总体 3.5 → 4.0。

## 11. 补充（2026-10-13）：对照真实服务器复核这一抽象

**结论：保留这一抽象，加固边缘。** EPP/1 exec 插件、`abx-provider.toml`、安装器和契约套件足以让 OpenSandbox 真正跑起来（Docker，服务器 1.1.1），Node CLI 和 Python SDK 两端都验证过：按提交固定从 git 安装、doctor、契约 18/18、create、exec、二进制文件、超时、pause/resume、connect、kill、篡改检测。证据：[2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md)。没有新增任何协议方法。

复核发现并改动的内容（TS 与 Python 同步）：

| 发现 | 改动 |
|---|---|
| 沙箱不存在时，插件是 `E8005`，内置提供方是 `E2009` | `sandbox.get/connect/set_timeout/pause/resume` 把插件的「未找到」映射为 `SandboxNotFoundError`（E2009）；插件也可以写 `sdk_code: "E2009"`。契约套件现在要求未知 id 返回 E2009 |
| `rest` 预设不执行 `[features] supported`（只有 `exec` 插件执行） | `feature_gate` 包住四个协议类；未声明的特性在任何 HTTP 请求之前返回 E8004 |
| `exec` 记录继承了内置平台的 `region = "cn-hangzhou"` 和 `timeout = 300` | `record_to_info` 让区域为空；插件同时给出 `created_at`/`expires_at` 时由它们推出 timeout |
| 某些路径下 `--yes` 会接受会移动的 git ref | `--yes` 永远不接受未固定的 ref；交互式审阅或 `--allow-unpinned` 才可以。`update` 同一规则。拒绝信息会打印应当固定的提交 |
| 插件根目录缺少 `abx-provider.toml` 时只提示「file not found」 | 错误信息说明清单文件不在插件根目录，以及如何指向子目录 |
| `provider list` 看不出提供方能做什么 | 新增 Features 列（`sandbox(lifecycle,pause) exec(run,stream) ...`），`--json` 和 `python -m agent_sandbox.providers list` 里也有 |
| exec 与 rest 提供方里重复的同意逻辑；TS exec 适配器里没用的 `listV2` | 抽出 `consented_inherit`；删除该方法 |

冗余检查：`exec_provider`（EPP 适配器）与 `rest_provider`（E2B 预设）除上面的辅助函数外没有共用代码，也不冗余：它们是到达后端的两种方式（自有线协议 vs E2B 线协议）。`epp.ts` / `epp.py` 只是 JSON-RPC 客户端和错误映射。`Provider.capabilities()` 与 `FEATURE_TO_CAPABILITY` 没有调用方；能力解析仍来自模板（未解决）。

信任模型检查：安装器本来就不检出工作树、只允许普通文件、记录树摘要、每次启动校验、更新失败时回滚。确认与固定本来就有，但存在漏洞（`--yes` 加分支名），现已堵上。因此从 git URL 安装提供方**不是**实验性功能。

未解决：模板命令忽略 `--provider`；能力集合不是由提供方特性推导的；没有 pause/resume 的 CLI 命令；`SandboxInfo` 的区域和超时仍带有内置默认值。
