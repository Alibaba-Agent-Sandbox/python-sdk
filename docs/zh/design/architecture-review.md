# 整体架构评审：过度设计、重复与体验矛盾

> 评审日期：2026-10-13。范围：`cli`（`@agent-sandbox/cli`，命令 `abx`）和 `python-sdk`（`agent-sandbox`、`agent-sandbox-server`）。
> 方法：读代码、跑 `abx --help`、数规模。每一条都标了证据位置。标「判断」的是我的取舍意见，不是事实。

## 2026-10-13 清理之后的状态

下面的正文是评审当时的快照，路径、名称和数字保持原样，没有改写。这一节记录每条发现现在的落地情况。3.5 已完成：评审记录和 server-sdk-v2 目标设计现在位于 [archive/](../archive/)。

| 条目 | 状态 | 现状 |
|---|---|---|
| 1.1 密钥变量名 | 已完成 | 文档与代码统一为 `ABX_SANDBOX_API_KEY` |
| 1.2 「兼容 E2B 协议 / drop-in」标语 | 已完成 | 标语已删，文档只说「E2B 形状的 API」及其差异 |
| 1.3 全局 `--profile` | 已完成 | 已删除 |
| 1.4 `config init` 引导范围 | 已完成 | 默认只问凭证和区域 |
| 2.1 跑 Agent 的五个入口 | 已完成 | 只保留 Agents API（`/v1/agents/**`）。`BUILTIN_AGENTS`、`agent/builtin.py`、`abx agent`、自带 Agent 设计文档已删除 |
| 2.2 具名命令的三个名字 | 已完成 | 只保留服务端注册（`@command`，模板里的 `commands.py`），调用是 `sandbox.run(name, **kwargs)`。`Sandbox.custom()` 和 `custom_commands` 已删除，客户端会拒绝该键。`sandbox.register.upload()/download()` 也已删除 |
| 2.3 两套分发面、两套策略引擎 | 已完成 | 一张 `ENDPOINTS` 表（118 个端点）、一个 `PolicyEngine`、一条管线。`/ops` 与 `server/core/*` 已删除；路径违规统一为 403 `path_not_allowed` |
| 2.4 能力开关两层互相遮蔽 | 已完成 | 只有端点规则一层。组是端点 id 的别名，`template.yaml` 的 `server.groups` 接受列表或映射。唯一的组环境变量是 `ABX_SERVER_ENABLED_GROUPS`（只能打开）。`ABX_SERVER_DISABLED_GROUPS`、`enable_builtin`、`disable_builtin`、客户端 legacy 发现模式都已删除。404 和 `/capabilities` 带 `rule`，说明是哪条规则拒绝的 |
| 2.5 只在 README 里的 OSS / VPC / 自定义域名 | 已完成 | 已删除（平台没有按沙箱暴露这些 API）。`compat` 保留为部分迁移辅助；`declarative`（`@sandbox`）保留，是否长期保留仍待你定 |
| 2.6 CLI 命令面三层别名 | 已完成 | 顶层快捷方式写死；`exec` 吸收流式执行；没有 `sandbox process start` |
| 3.1 TS 版 CLI 带着 Python 的外衣 | 已完成 | 命令层在 commander 上（`cli/src/cli/kit.ts`）。模型用 zod，终端颜色用 picocolors，YAML 用 `yaml`。Click、Rich、Pydantic 复刻已删除 |
| 3.2 双语言各写一份业务逻辑 | 已完成 | 边界已定：Python SDK 是运行时客户端，CLI 负责模板构建和部署。客户端的构建与部署代码已删除 |
| 3.3 提供方插件系统 | 已完成 | 抽象保留，OpenSandbox 已从 CLI 和 Python SDK 跑通 |
| 3.4 Agents API 的宽度 | 已完成 | 路由保留（70 条）。`GET /v1/agents/runtimes` 报告 `implemented`；只有 Codex 和 Qwen Code 有本地后端，其余适配器返回带类型的 404 |
| 3.5 文档量与结构 | 已完成 | 评审记录和 server-sdk-v2 目标设计现在位于 [archive/](../archive/) |

## 0. 先给结论

架构的主干是合理的：客户端、容器内服务端、模板与提供方这四块各有一个明确职责，这一点不用动。

问题集中在「同一件事有多个入口」。上一轮删掉的自带 Agent 只是其中一例，同类问题还有六处。另外，第一次上手的路径上有三处文档与代码对不上，这类问题比重复更伤体验，应该最先修。

| 优先级 | 数量 | 含义 |
|---|---|---|
| P0 | 4 | 新用户第一步就会撞上的矛盾，修起来便宜 |
| P1 | 6 | 重复或半成品，建议合并或删除，需要你拍板 |
| P2 | 5 | 成本高但不紧急，先记下，不建议现在动 |

规模参照（行数）：

| 部分 | 源码 | 测试 |
|---|---|---|
| `cli/src` | 61,516 | 44,307 |
| `python-sdk/client-sdk/src` | 23,952 | 27,033 |
| `python-sdk/server-sdk/src` | 21,880 | 12,523 |
| 文档 | 192 个 md，52,067 行 | |

## 1. P0：第一次使用就会撞上的矛盾

### 1.1 文档里的密钥变量名不是代码读的那个

`docs/zh/DESIGN.md` 和 `docs/en/DESIGN.md` 的「快速上手」写 `export SANDBOX_API_KEY=your-api-key`。代码里这个变量的规范名是 `ABX_SANDBOX_API_KEY`（`utils/config_keys.py`，`abx config` 与 `command-map.md` 也都用这个名字）。照着首页文档做的人会得到鉴权失败，却没有任何提示指向变量名。

建议：把 DESIGN 里的变量改成 `ABX_SANDBOX_API_KEY`，并在 `abx config init` 的末尾打印「已写入的变量名」。这是纯文档修改。

### 1.2 首页标语说「兼容 E2B 协议」，其余文档说「不是」

- 两个 README 和 DESIGN 的第一段都写「**E2B-protocol compatible**」，并且列出「drop-in replacement」。
- `command-map.md` 明说「不是参数级兼容，也不是把 Agent Sandbox 收成其中一家的子集」。
- `compat/sandbox.py` 只有 55 行，是一个重导出，文档表里有两个方法直接 `raise FileOperationError`。
- 我们刚决定不读 `E2B_*` 变量，也不做任何兼容。

三处互相矛盾。标语会让用户期待「改一行 import 就能迁移」，实际做不到。

建议（判断）：标语改成「方法形状接近 E2B，迁移见指南」，把 `compat` 的定位降到迁移辅助。是否保留 `compat` 模块本身见 2.5。

### 1.3 `abx --help` 里有一个不能用的全局选项

`--profile / -p` 的帮助文字是 `[Reserved] Configuration profile`（`cli/src/cli/main.ts:550`），值被存进 `ctx.obj` 之后没有任何命令读它。同时 `-t/--timeout` 是全局选项，却只对 `create` 有意义。

建议：删掉 `--profile`；把 `--timeout` 移到 `create`。未上线，没有兼容负担。

### 1.4 `abx config init` 把三种不相干的配置塞进同一次引导

引导覆盖「凭证、区域、ACR 命名空间、LLM」。只想 `abx create --template base` 的人只需要第一项。ACR 是构建推送镜像用的，LLM 只服务 `abx create "描述"` 的 AI 建模板。结果是第一次运行要回答一串与当前目的无关的问题。

建议：`config init` 默认只问凭证和区域；`--with-build`、`--with-llm` 才追加其余两段，或者在第一次用到时再问。

## 2. P1：重复与半成品

### 2.1 「在沙箱里跑 Agent」现在有五个入口，只有一个是真的

| 入口 | 状态 | 证据 |
|---|---|---|
| Agents API（`/v1/agents/**`） | 真实现，两个适配器 | `server/agents/*` 加 `routes_agents.py` 共约 9,300 行，70 条路由 |
| `sb.agent.code()` / `sb.agent.shell()` | 只有设计稿，没有实现 | `design/built-in-agents.md` 自己写着「设计稿，本质是 `commands.run()` 的语法糖」；`api/sandbox.py` 没有 `agent` 属性 |
| `BUILTIN_AGENTS` 关键字表 | 导出了，没有调用方 | `agent/builtin.py`（207 行）除 `__init__` 外无引用 |
| `abx agent …` 一组命令 | 只有规格，CLI 没有这个命令 | `design/agents-api-cli-followups.md`；`abx agent --help` 报用法错误 |
| 自然语言建模板的内置 Agent（`abx create "描述"`、`coding_agent`、`qwen_code`） | 真实现，但它是「生成模板」的工具，不是「运行 Agent」 | `cli/src/agent/*`，约 8,200 行 |

用户看到「Agent」这个词有五种含义。其中前三条合在一起是「已经被 Agents API 取代的另一套想法」，和刚删掉的自带 Agent 是同一类。

建议：
1. 删 `built-in-agents.md`（中英）、`BUILTIN_AGENTS`，`agent/infer.py` 如果只服务 `BUILTIN_AGENTS` 一并删（我没有追到它的全部调用方，删之前要查）。
2. 把 `agents-api-cli-followups.md` 要么实现，要么删。现在它是一份没人认领的规格。
3. 文档里把「AI 建模板」改名叫「模板生成」，不再叫 Agent。

### 2.2 同一件事「跑一个具名命令」有三个名字

- `Sandbox.custom()`，以及模板 `custom_commands`（机制 A，客户端把占位符替换后用 shell 执行）。
- 服务端 `CommandRegistry` 加 `POST /commands/{name}`（机制 B）。
- `@sandbox.register` 装饰器，再用 `sandbox.run("name")` 调用（`declarative/decorator.py`，656 行）。
- CLI 的 `abx run` 同时处理 A 和 B，并且有一个保留关键字 `server_port` 专门用来选机制 B（`cli/src/cli/commands/sandbox.ts:1799`）。

同一个动作，三种写法、两条执行路径，用户要先弄懂「我现在在用 A 还是 B」。

建议（判断）：只保留 B（服务端注册，有策略、审计、限流）。A 的价值只是不需要服务端，但所有现行模板都带服务端。需要你确认：有没有不带 server-sdk 的模板还在依赖 A。

### 2.3 服务端有两套分发面和两套策略引擎，迁移只做了一半

- v1 路由表加 `_dispatch`（`server/app.py`、`router.py`）。
- `/ops/{id}` 的 v2 管线（`server/core/*`，约 2,000 行）。`core/legacy.py` 的文件头写着「stage S1 of the strangler migration」，`core/policy.py` 的文件头写着「allow/deny 规则模型是后续工作包（WP-2），这个类目前没有 allow/deny 构造器」。
- 策略也有三层：`ServerPolicy`（`policy.py`，904 行，细粒度规则）、运行时 `PolicyEngine`、`core/policy.Policy`（包装前者）。
- 用户文档里搜不到 `/ops`：没有任何用户可见的文档描述它。

也就是说有一套用户看不见、没有完成的新入口，它的存在只增加维护面（`legacy.py` 要把 117 条 v1 路由逐条映射一遍）。

建议（判断）：未上线，不需要「绞杀」过渡。二选一：(a) 把 `/ops` 冻结并从发布物里去掉，等有明确需求再回来；(b) 现在直接完成迁移，删 v1。我倾向 (a)，因为客户端、CLI、全部模板、测试都是按 v1 写的。

### 2.4 能力开关有两层，并且互相遮蔽

- 层 1：能力组开关，`ABX_SERVER_ENABLED_GROUPS` 与 `ABX_SERVER_DISABLED_GROUPS` 两个方向相反的变量（`router.py:74`、`runtime.py:60`、`routes_agents.py:4`）。
- 层 2：端点策略（`ServerPolicy.only(...)`、`template.yaml` 的 `server:`）。
- 组在 `agents` 这类默认关闭时，只启用某个端点而不启用组，会得到 404，而不是「这个端点被开启了但组关着」的明确提示。

我们为 Agents API 补了「逐个端点开启」，但它建立在这个两层模型之上，用户要同时理解两层。

建议：对外只暴露一层。组只作为「一键开一批端点」的别名，在策略里展开成端点；删掉 `DISABLED_GROUPS`，只留一个方向。404 的错误体里写明是哪一层拒绝的。

### 2.5 Python 客户端里有几块「只在 README 里有」

- `extensions/oss.py`、`vpc.py`、`domain.py` 各约 20 行，只是 pydantic 数据类。`OSSMount` 在整个 `client-sdk/src` 里没有任何使用方（我 grep 过）。但两个 README 把「OSS、VPC、自定义域名」写成一等能力。
- `compat/` 见 1.2。
- `declarative/` 的 `@sandbox` 装饰器是第三种编程范式（除了 `Sandbox.create` 和具名命令），见 2.2。

建议：README 里不再宣称 OSS/VPC/域名，除非它们被接到 `create`；`compat` 与 `declarative` 各自决定留或删（需要你定，见第 5 节）。

### 2.6 CLI 命令面有三层别名

`abx --help` 有 15 个顶层命令，`create`、`list`、`info`、`kill`、`exec`、`connect`、`upload`、`download`、`run` 都是 `abx sandbox …` 的快捷方式。快捷方式表存进 `~/.abx/config.toml`，运行时「配置文件是唯一来源」（`_shortcut_table.ts`）：用户改配置会让 `abx create` 消失。

「执行一条命令」有四种说法：`abx exec`、`abx sandbox exec`、`abx sandbox process start`（帮助里写「同步执行并等待」）、`abx sandbox shell-stream`，加上 `abx run` 与 `abx connect`。

建议：快捷方式固定，不放进用户配置；只保留 `exec`（同步）和 `process start --background`（后台）两种；`shell-stream` 并入 `exec --stream`。`provider` 是核心命令但不出现在顶层帮助里，要么列出来要么说明原因。

## 3. P2：成本高，先记下

### 3.1 TS 版 CLI 带着 Python 的外衣

`cli/src/framework/*`（约 5,000 行，等于一份 click）、`cli/src/cli/_rich.ts`（2,350 行）、`models/_pydantic.ts`（1,051）、`_orjson`、`_shlex`、`difflib`、`_pycompat` 合计约 10,500 行，用来在 Node 里复刻 Python 库的行为。原因是 CLI 是从 Python CLI 逐行移植过来的，并用「parity 台账」保证每个 Python 测试都有对应测试。

Python CLI 已经被删，这套保真再没有对照物。后果：每加一个命令要在 click 复刻层里写，换成 `commander` 一类的库可以省掉一半以上，但需要重写 11,000 行命令代码和大量以 Python 输出为准的测试。

判断：不要现在动。在发布 0.3 之后，如果还会继续长期演进 CLI，再单独立项。

### 3.2 同一套业务逻辑在两种语言里各写一份

`cli/src/api/*` 与 `client-sdk/src/agent_sandbox/api/*` 一一对应（Docker 构建 Python 1,194 行对 TS 1,254 行，`fc_template` 878 对 860，`session_manager` 161 对 136，另有 `providers/`）。`ci.yml` 里需要把 python-sdk 的源码 vendoring 到 CLI 仓库才能跑模板指南的交叉检查，说明两个仓库在测试上已经耦合，在发布上却是分离的。

判断：边界应该是「Python SDK 负责运行时客户端，CLI 负责模板构建与部署」，各自只写一份，通过一个稳定的数据文件（`template.yaml`、`abx-provider.toml`）连接，而不是互相镜像。这是一个大改动，先定边界，再逐步收缩。

### 3.3 提供方插件系统比现实需求重

EPP/1 协议、`installer`（从 git URL 装插件）、`exec_provider`、`rest_provider`、`doctor`、`template_profile`，TS 约 4,800 行，Python 侧再镜像一份。真正在用的只有 `alicloud-express`，OpenSandbox 是验证用的第二个。从 git URL 安装并执行第三方代码，还带来供应链面。

判断：协议留着无害；建议先不对外承诺「安装第三方提供方」，把 `provider install` 标成实验性，等第二个提供方真实落地再开放。

### 3.4 Agents API 的宽度远超两个适配器

70 条路由占整个服务端 117 条的 60%，覆盖 vaults、environments、subagents、webhooks 等，而适配器只有 `codex` 与 `qwen-code`；`claude-code`、`cursor`、`command` 返回 404 `agents.not_implemented_locally`。路由表面是对着一个更大的目标形状写的，实际只有一小部分有真实后端。

判断：保持（你已经决定后续会扩充）。但需要在 `GET /v1/agents/runtimes` 或文档里清楚标出「哪些路由是真实现、哪些是形状」，避免用户把 404 当成故障。

### 3.5 文档量与结构

192 篇 md、5.2 万行，中英各一份。`design/` 里混着：已实现的设计、没有实现的设计（`built-in-agents`、`cli-followups`）、评审记录（`*-review.md`、`server-sdk-v2/reviews`、`opensandbox-e2e-adversarial.md`）。用户找不到「现在到底是什么样」。

判断：把评审记录移到 `docs/archive/` 并在 README 标明不是现行规范；没有实现的设计文件头统一加「状态：未实现」。

## 4. 做得对、不要动的部分

- 客户端 / 服务端 / 模板 / 提供方的四块划分。
- 配置键唯一来源（`config_keys.py`）加生成到 CLI，避免了两边漂移。
- 细粒度策略的数据模型本身（`ServerPolicy`），问题只在上面叠了两层。
- 默认一个 Agent、其余显式指定；Agents API 是运行 Agent CLI 的唯一方式。
- 对阿里云官方变量名保持原样。

## 5. 需要你决定的事

| # | 问题 | 我的倾向 |
|---|---|---|
| 1 | 删 `BUILTIN_AGENTS`、`built-in-agents.md`，并实现或删除 `agents-api-cli-followups.md` | 删前两者；CLI 的 `abx agent` 先不做 |
| 2 | 具名命令只保留服务端注册（机制 B），去掉 `custom_commands`（机制 A） | 是，前提是没有无服务端模板在用 A |
| 3 | `/ops` v2 管线：冻结移出发布物，还是现在完成迁移并删 v1 | 冻结移出 |
| 4 | 能力开关对外只保留一层（端点策略），组只是别名 | 是 |
| 5 | `declarative`（`@sandbox`）和 `compat` 是否保留 | 保留 `compat` 为 55 行迁移辅助；`declarative` 你来定 |
| 6 | CLI 命令面收敛（快捷方式固定、`exec` 合并、删 `--profile`） | 是 |
| 7 | 首页标语去掉「E2B 兼容」 | 是 |

P0 的四条我可以直接修，不需要决策。

## 6. 建议的执行顺序

1. P0 四条（纯文档与小范围 CLI 参数改动）。
2. 决策 1、7：删除与标语，改动小、冲突面最小。
3. 决策 6、4：影响 CLI 与服务端对外的名字，要在发布 0.3 之前做，否则之后就是破坏性变更。
4. 决策 2、3、5：涉及模板、服务端的结构，在上一步之后做。
5. P2 全部延后。
