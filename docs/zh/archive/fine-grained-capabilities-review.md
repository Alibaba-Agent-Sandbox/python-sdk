# 评审记录：细粒度能力、客户端/服务端对齐、基础镜像

> 状态：归档。不是现行规范。

> 被评审文档：[fine-grained-capabilities.md](../design/fine-grained-capabilities.md)、
> [client-server-alignment.md](../design/client-server-alignment.md)、
> [base-image-and-server-sdk.md](../design/base-image-and-server-sdk.md)。
> 被评审产物：**v1 草案**（第 1 轮评审前冻结的三份文档）。
> 结论：**v2（已评审）**。下列每一项发现要么已在设计文档中解决（每份文档末尾的"评审后的变更"一节），要么明确推迟并说明原因。
> 英文版为准（逐条的完整措辞与测试引用）：[../../en/archive/fine-grained-capabilities-review.md](../../en/archive/fine-grained-capabilities-review.md)。

## 0. 方法与如实说明

任务要求由不同视角的*全新子智能体*进行两轮独立的对抗式评审。撰写环境**没有子智能体创建能力**，因此两轮评审由作者本人以**相互独立的串行评审过程**完成，
每个视角都扮演刻意敌对的角色，并且从冻结的 v1 草案和显式检查清单出发，而不是从作者的意图出发。这弱于真正独立的评审者（可能存在共同盲区），因此采取了两项缓解措施：

* **第 2 轮的安全视角基于证据而非意见。** 评审之前，对*未修改的*服务端运行了经验性探测：启动真实的 `SandboxServer`，埋入指向基础目录之外的符号链接，
  并发出路径遍历、编码、方法覆盖和畸形请求头的请求。发现项 R2-S1..S6 是观察到的行为，而不是假设。同样的探测已变成回归测试（见第 4 节）。
* **每项解决方案都有测试支撑。** 每个"已解决"的条目都指明了锁定它的测试模块（纯文档性的则指向文档章节），便于人工评审者核对。

建议在 GA 发布之前增加由人工或独立智能体完成的第三轮评审（列入最终报告的未决问题）。

严重程度：**H** = 会带来漏洞或硬性不兼容；**M** = 会导致缺陷或用户痛点的设计缺口；**L** = 打磨项。

## 1. 第 1 轮：功能完整性与用户体验/API 人体工学

### 1a. 视角：功能完整性（"哪些场景无法表达或含糊不清？"）

| # | 级别 | 发现 | 解决 |
|---|------|------|------|
| R1-F1 | M | 主打场景（"只暴露上传 + 下载，且下载只能来自 `/home/user/out`"）需要 12 行 JSON；草案中没有一行式写法。 | `transfer-only` 预设**以及** `ServerPolicy.only(*endpoint_ids, **rule)` 成为规范（3.4a）：`only` = `"*": {enabled: false}` + 启用列出的 ID，核心端点始终保留。测试：`test_policy_config.py`（预设）、`test_policy_paths.py::TestTransferOnlyScenario`。 |
| R1-F2 | M | 多路径端点（`files_move`、archive、搜索根）未规定：只读是针对源还是目标检查？每个路径属于哪类操作？ | 增加规范性的*路径角色*表（3.5）：`files_move` 的源为 `delete`、目标为 `write`，两者都必须通过 allow/deny/只读；`files_archive` 的根为 `read`，每个成员重新检查。测试：`test_policy_paths.py::...::test_move_out_of_scope_denied_both_directions`、`test_policy_pipeline.py::TestScopes::test_move_requires_both_write_and_delete`。 |
| R1-F3 | H | 限制只通过 `Content-Length` 执行。伪造/缺失长度（分块）会让无限数据流入 `files_upload_stream`。 | 请求体由端点的 `max_request_bytes`（默认为传输上限）约束，作用于读取请求体前声明的 `Content-Length`；`max_bytes` 约束解码后的负载；策略模式下拒绝分块 `Transfer-Encoding`（400）；中止时删除不完整文件。测试：`test_http_hardening.py::TestBodyLimit::test_lying_content_length_cannot_exceed_cap`、`test_policy_paths.py::TestTransferOnlyScenario::test_upload_size_limit`。**实现说明：** 最终实现*没有*使用计数读取器；服务端只读取声明的长度，因此伪造的长度无法超出上限。 |
| R1-F4 | M | 自定义路由（`RouteTable.route(...)`）和自定义命令无法参与：无法声明 scope，处理器没有 `PathGuard`。 | `RouteInfo.scopes`；`register(..., scopes=[...], endpoint_id=...)`；处理器可获得 `request.context["policy"]`（带 `guard(path, op)` 的 `EndpointContext`）。测试：`test_policy_pipeline.py::TestScopes::test_custom_route_scopes`。 |
| R1-F5 | M | `capabilities_check` 出现在 scope 表里，却没有关于"不得成为探测口（不得触碰文件系统）"的契约。 | 契约：只做策略求值，不做 `stat`；响应永远不说明路径是否存在。测试：`test_policy_pipeline.py::TestDiscovery::test_check_does_not_reveal_existence`、`test_check_endpoint_matches_enforcement`。 |
| R1-F6 | M | 策略重载/可变性未规定。 | 策略在启动后不可变；`revision` 是内容哈希；运维通过重启生效（第 4 节"配置入口"）。运行时 `with_endpoint` 创建*新*策略对象。 |
| R1-F7 | M | 无法表达按身份的*路径* scope（令牌 A 可读 `/out`，令牌 B 可读 `/in`）；规则是全局的。 | **推迟（v1 的文档化非目标）。** 理由：身份 x 路径矩阵会使 schema 翻倍；受支持的做法是使用不同沙箱，或使用自定义 scope 加不同端点。记为未决问题 OQ-2。 |
| R1-F8 | L | 未设置限制的默认值是"今天的常量"，但没有列举。 | 增加旧常量表（3.6）：10 MiB JSON 请求体、100 MiB 旧版 `/download`、10 MiB `/upload`（`ABX_MAX_UPLOAD_SIZE`）等。 |
| R1-F9 | L | `files_watch` 需要类似 `process` 的长连接，没有最长时长/并发限制。 | `limits.max_duration_seconds`（默认 300）+ `max_concurrency`。 |

### 1b. 视角：用户体验 / API 人体工学（"新用户会在哪里踩坑？"）

| # | 级别 | 发现 | 解决 |
|---|------|------|------|
| R1-U1 | M | 策略中的笔误（`"alow"`、`"limit"`）会静默变成空操作，看起来像安全漏洞。 | 封闭词汇表；未知键触发 `PolicyConfigError`，附带*拼写建议*和 JSON 路径（`endpoints.files_list.paths.alow`）。测试：`test_policy_config.py`（未知键/拼写建议用例）。 |
| R1-U2 | M | `endpoints` 中未知的端点 ID（如 `file_download`）被静默忽略。 | 没有匹配任何已注册路由的精确选择器是错误（匹配不到任何路由的通配符在 `check-config` 中只是警告）。 |
| R1-U3 | M | 调用方应捕获哪个错误？草案只是一个扁平列表。 | 客户端异常树定稿（第 7 节）：全部派生自 `ServerAPIError`；它带有 `.status_code`、`.error_type`、`.error_code`、`.endpoint`，`PolicyDeniedError` 增加 `.scope`；旧的 `except PermissionDeniedError` 仍能捕获文件策略拒绝。 |
| R1-U4 | M | 缓存过期时（策略已变而客户端本地返回 403），"快速失败"的预检查可能令人意外。 | 预检查只在*显式* `discover()` 之后发生；服务端始终权威；**实现情况：** `client.forget_discovery()` 丢弃缓存，`discover()` 刷新（没有 `prechecks=False` 开关：不调用 `discover()` 就是选择退出）；调用方最终看到的始终是服务端自己的拒绝。 |
| R1-U5 | L | 需要调试辅助："为什么我的调用被拒绝？" | `ServerPolicy.explain(...)`（服务端），`client.check(...)` / `caps.check_path(...)` -> `POST /capabilities/check`；`agent-sandbox-server check-config --explain files_download_stream --path /etc/passwd`。 |
| R1-U6 | L | 大小字符串（`5MB`）在 MB 与 MiB 之间有歧义。 | 十进制与二进制明确区分：`MB`=10^6，`MiB`=2^20；纯整数为字节；已文档化并测试。 |
| R1-U7 | L | `Sandbox.server` 与装饰器代理同名。 | 已核实无冲突（`Sandbox` 今天没有 `server` 属性）；保留 `Sandbox.server`（9000 端口、惰性、缓存）+ `Sandbox.server_at(...)`。 |
| R1-U8 | L | 同步用户需要每个方法的 `_sync` 孪生。 | 对齐文档中强制要求；完整性测试遍历所有异步方法。 |
| R1-U9 | L | `ServerPolicy.only("download")`：旧路由 ID `upload`/`download` 与 stream ID 容易混淆。 | `only()` 接受别名组令牌 `"transfer"`，含义为 `{upload, download, files_upload_stream, files_download_stream}`。 |

**第 1 轮结论：** 设计已更新（3.4a、3.5 角色表、3.6、7、8 节）；除 R1-F7（推迟）外没有拒绝任何发现。

## 2. 第 2 轮：安全绕过与向后兼容

### 2a. 视角：安全绕过（"假设策略作者很称职，而我是敌人"）

针对未修改服务端的探测所得证据标记为 **[probe]**。

| # | 级别 | 发现 | 解决 |
|---|------|------|------|
| R2-S1 | **H** | **[probe]** `files_archive`（zip）会跟随*文件*符号链接：沙箱目录中指向 `/etc/passwd` 的符号链接会连同内容一起被打包。基于现有代码构建的任何路径白名单都可以通过归档端点绕过。属于既有漏洞。 | 归档拒绝（跳过）目标位于端点边界之外或被拒绝的符号链接；从不跟随目录符号链接。这是**所有模式下都应用的缺陷修复**（在 CHANGELOG 中记为安全修复）。测试：`test_policy_paths.py::TestArchiveSymlinkLeakFix`。 |
| R2-S2 | M | **[probe]** `files_search`/`files_list` 会显示指向外部的符号链接条目的名称，名称泄露目录拓扑。 | 策略模式下未通过守卫的条目被省略（且不会进入）。旧模式不变。测试：`test_policy_paths.py::TestDirectoryExpandingEndpoints::test_list_omits_denied_and_escaping_entries`。 |
| R2-S3 | **H** | **[probe]** 非数字的 `Content-Length` 会使 `_read_json_body` 抛出未处理的 `ValueError`（连接被丢弃，无响应）；负值被当作 JSON 错误解析。恶意客户端可借此做请求走私实验。 | 严格解析：`^\d+$`，否则 400；负数 -> 400；重复且不同的 `Content-Length` -> 400；带请求体端点上出现 `Transfer-Encoding` -> 400。所有模式生效（纯缺陷修复；此前行为是中止连接）。测试：`test_http_hardening.py::TestContentLength`。 |
| R2-S4 | M | **[probe]** 重复查询参数（`?path=/ok&path=/etc/passwd`）：服务端取第一个，而中间层（网关/WAF）可能取最后一个，上游做出的白名单判断就会不一致。 | 策略模式下拒绝重复的携带路径的参数（`400 duplicate_parameter`）。旧模式保持"第一个生效"。测试：`test_http_hardening.py::TestPolicyModeFraming`（仅策略模式拒绝）。 |
| R2-S5 | M | **[probe]** 存在性探测的顺序：边界内不存在的路径 -> 404 "File not found"，边界外 -> 400/403，调用方因此可以探测白名单之外的文件系统。 | 策略模式下边界/deny 检查总是在任何 `stat` **之前**执行，边界之外无论是否存在都返回同样的 403 `path_not_allowed`。测试：`test_policy_paths.py::TestNoExistenceOracle`。 |
| R2-S6 | L | **[probe]** 相对路径相对*服务进程 CWD* 而不是 `base_dir` 解析；配合 `paths.allow` 是个陷阱。 | 旧模式保留（兼容），策略模式下相对路径相对第一个 allow 根目录解析（已文档化）。测试：`test_policy_paths.py::...::test_relative_paths_resolve_against_allow_root`。 |
| R2-S7 | **H** | 把策略挂在 *URL 字符串* 而不是匹配到的路由上，会产生编码路由和尾部斜杠的差异。草案已按 `RouteInfo` 为键；评审者核验了路由器：`%73tat` -> 404，`//files` -> 404，尾部斜杠在匹配前归一化。 | 确认：策略键仅为 `route.name`；对编码/双斜杠/尾部斜杠路由做回归测试；方法覆盖头/参数被明确忽略。测试：`test_http_hardening.py::TestMethodOverride`、`TestRouteNormalisation`。 |
| R2-S8 | **H** | TOCTOU / 符号链接替换：先 `realpath` 检查再 `open`。拥有 `process:run` 的攻击者可以竞争替换。 | 最后一个分量使用 `O_NOFOLLOW`；打开后把 `fstat` 身份与 `/proc/self/fd/N` 的解析结果比较并重新做边界检查；`symlinks: never` 额外拒绝任何符号链接分量（lstat 逐级遍历）。**残余风险已文档化**：检查与打开之间中间分量的替换在纯标准库 Python 中无法完全消除；缓解办法是不要把 `process`/`terminal` 与路径范围同时暴露（lint L1）。 |
| R2-S9 | M | 允许目录树内指向外部 inode 的硬链接对路径检查不可见。 | 残余风险已文档化（只能通过进程端点创建；由 lint L1 覆盖）。`files_*` 端点不能创建硬链接。 |
| R2-S10 | M | Deny glob：大小写变体、`./`、尾部斜杠，以及匹配词法路径还是解析后路径。 | Deny 同时作用于**解析后**路径*和*归一化的词法路径；POSIX 下区分大小写（已文档化；macOS 开发机需注意）；基本名模式（`*.pem`）匹配任何路径分量；目录 deny 是带分隔符的前缀匹配（`/a/b` 不会拒绝 `/a/bc`）。每个变体都有测试。 |
| R2-S11 | **H** | 令牌混淆：草案允许同时使用 `Authorization: Bearer` 与 `X-Access-Token`；两个不同的 `X-Access-Token` 头的行为未定义。 | 身份模式：出现多个不同的凭据头值 -> 400 `ambiguous_credentials`；仅当 `X-Access-Token` 缺失或相同时 Bearer 才生效（草案写的是"使用 Authorization"，已修改：网关会注入自己的 `X-Access-Token`；顺序为先 `Authorization`，已文档化）。旧模式不动（第一个 `X-Access-Token`）。 |
| R2-S12 | M | 多个令牌时令牌查找的时序侧信道。 | 对所有令牌先取摘要再 `compare_digest`，不提前退出（保持）；这是实现层面的性质，没有时序测试覆盖。 |
| R2-S13 | **H** | 秘密暴露：`GET /env`（system 组）返回整个环境，包括 `ABX_SERVER_TOKEN` 和其他身份的 `token_env`；子进程会继承它们。 | 策略身份模式下 `env_get` 对服务端自己的秘密（`ABX_SERVER_*` 与所有已配置的 `token_env` 名称）脱敏；子进程环境只去掉相同的名称（任意用户变量从不触碰）。`env_set` 拒绝这些名称和 `ABX_` 前缀。旧模式不变（兼容），但 lint 建议使用策略。测试：`test_policy_pipeline.py::TestSecrets`、`test_policy_exec.py::TestSecretEnvironment`。 |
| R2-S14 | M | PTY WebSocket（9001 端口）有自己的认证（URL 中的 `?token=`：令牌会进入访问日志和网关日志），且会绕过端点策略。 | PTY 服务端使用同一份策略：身份来自 `Authorization: Bearer` / `X-Access-Token` 头（新增）或旧的查询令牌；需要 scope `terminal:use`；`pty_connect` 规则 `enabled:false` 会以 4003 关闭套接字。查询令牌仍被接受（兼容），但会在发现的 `warnings` 中标注。测试：`test_policy_pty.py::TestPtyWebSocketAuth`。 |
| R2-S15 | M | 策略文件完整性：可写的策略文件允许沙箱内用户放宽策略。 | `agent-sandbox-server check-config`（lint L5）会在策略文件或其目录对当前用户可写时发出警告（请以服务端用户身份运行）；文档建议将其放在 `/etc/agent-sandbox/`，属主 root、权限 0644。 |
| R2-S16 | M | allow 根目录很宽（`/`）时暴露 `/proc`、`/sys`、`/dev`；`/proc/self/environ` 会泄露令牌。 | allow 根为 `/` 时 lint L2；`hardened` 预设拒绝 `/proc`、`/sys`、`/dev`、`**/.ssh`、`**/.env*`、`**/*.pem`、`**/id_*`。 |
| R2-S17 | L | 超长路径 / glob 选择器的 CPU 消耗（ReDoS）。 | 路径长度上限 4096；选择器对短 ID 使用 `fnmatch`；deny 模式使用 `fnmatchcase`，不会由用户输入生成正则。 |
| R2-S18 | L | 通过路径字符串进行审计日志注入。 | 以 JSON 编码的行（构造上即已转义）；路径截断为 512 个字符。 |
| R2-S19 | L | 暴力破解令牌：没有失败认证的节流。 | **推迟**：部署在网关之后；标准库服务端在网关后面做按 IP 限流并不可靠。已文档化；采用恒定时间比较，并在文档中给出高熵令牌建议。 |
| R2-S20 | L | Unicode 形近字符 / 规范化。 | POSIX 路径是未经规范化的字节，形近字符指向*不同*的文件，不存在混淆绕过。已文档化（macOS HFS+ 规范化注意事项）。 |

### 2b. 视角：向后兼容（"现有用户哪里会坏？"）

| # | 级别 | 发现 | 解决 |
|---|------|------|------|
| R2-C1 | **H** | 现有测试（`test_env_subprocess_boundary.py`）直接用 `ThreadingHTTPServer(..., SandboxRequestHandler)` 接线，只设置 `auth_token` 和 `registry`。新属性（`policy`、`audit`）不能是必需的。 | 处理器通过 `getattr(self.server, ..., None)` 读取每个新属性；`None` 策略 = 旧流水线。测试：现有套件 + `test_policy_compat.py::test_bare_handler_wiring_still_works`。 |
| R2-C2 | M | `RouteInfo` 是被第三方按位置构造的公共数据类；插入字段会破坏它们。 | 新字段追加在现有字段**之后**并带默认值；`RouteTable.register` 的新增参数仅限关键字。 |
| R2-C3 | M | `GET /capabilities` 的消费者可能断言精确的键集合。 | 现有键不变（保留 `groups`），新增内容是新键；有"精确超集"测试固定。 |
| R2-C4 | M | 错误响应体新增 `code`；对响应体字典做相等比较的客户端会坏。 | 现有键/值不变，仅在存在稳定 code 时才添加 `code`；已文档化为增量。 |
| R2-C5 | M | `ABX_SERVER_DISABLED_GROUPS` 与策略 `groups` 的优先级。 | 已取代：该变量已删除。只有一层（端点规则）说了算；`ABX_SERVER_ENABLED_GROUPS` 是唯一的组环境变量，并且只能打开组。 |
| R2-C6 | M | `Image()` 默认基础镜像：草案把默认值绑定到 ubuntu；改成官方基础镜像会悄悄改变每一次构建。 | 默认**不变**；新增 `Image.official_base()`；基础镜像不是官方镜像时 `DockerBuilder` 只发*警告*（不报错）（基础镜像文档第 3 节）。 |
| R2-C7 | M | 服务端必须保持仅标准库且支持 Python 3.10+：不能用 `tomllib`（3.11），不能硬依赖 PyYAML。 | 服务端只有 JSON 解析器；仅在可导入 PyYAML 时才接受 YAML；没有新依赖。由服务端 only 导入测试验证（`server-sdk/tests/test_server_only_import.py`）。 |
| R2-C8 | M | 版本同步发布：新客户端对旧服务端（反之亦然）。 | 客户端把缺少 `endpoints` 键视为 `legacy`，除非调用方设置，否则从不发送新参数（`cwd`、`env` 等）；旧服务端上的新端点表现为 `EndpointNotAvailableError`（404 映射），而不是原始 HTTP 错误。测试：带旧版桩服务端的客户端测试。 |
| R2-C9 | L | `SandboxTemplate` 严格性：新增 `server:` 不能拒绝现有模板；`server:` 的内容要延迟校验，以免客户端导入服务端包。 | 可选字段，`dict` schema，由客户端中的小型结构校验器（共享词汇常量）校验，而不是导入服务端包。 |
| R2-C10 | L | 现有的 `enable_builtin`/`_enabled_builtins` 旧开关。 | 已取代：已删除。`enable_group` / `disable_group` 修改端点规则的 code 层。 |

**第 2 轮结论：** 两项 **H** 级安全问题是既有缺陷（R2-S1、R2-S3），因为它们严格属于缺陷修复，所以在所有模式（而不只是策略模式）下修复。这是"未配置行为"唯一发生变化的地方，
并且两处原有行为都是泄漏/崩溃。其他所有变更都以配置了策略为前提。

## 3. 对齐文档与基础镜像文档的评审

两份文档经过了同样的两轮评审。主要发现：

| # | 文档 | 发现 | 解决 |
|---|------|------|------|
| R-A1 | 对齐 | 提议新增服务端 `process_output` 与 `process_stdin`，但没有说明它们与 `capture_output` 限制如何交互。 | 增加规范：有界环形缓冲（`limits.max_output_bytes`，默认每进程 1 MiB），基于游标读取。 |
| R-A2 | 对齐 | 客户端 `ServerClient.files.download` 与基于 envd 的 `Sandbox.files.read` 在用户看来可以互换。 | 在矩阵（第 5 节）中用决策表说明：必须在任意沙箱上工作的代码默认用 envd；模板作者提供的、受策略限定的访问使用 `ServerClient`。 |
| R-A3 | 对齐 | 流式方法需要取消语义。 | 异步生成器在 `aclose()` 时关闭响应；同步孪生返回带 `close()` 的迭代器。 |
| R-B1 | 基础镜像 | "值得做"的决定主要基于对网关的推断；"网关转发 `Authorization`"这一说法未经证实。 | 标为未决问题 OQ-3；服务端同时接受两种头，因此网关怎样处理都可行。 |
| R-B2 | 基础镜像 | `Image()` 默认值变更（现有构建的安全性）。 | 见 R2-C6。 |
| R-B3 | 基础镜像 | 控制台脚本 `agent-sandbox-server` 不能遮蔽 `abx`。 | 已检查名称：无冲突。 |
| R-B4 | 基础镜像 | 评审者攻击：`check-config`/`healthcheck` 子命令不能依赖网络或重量级导入（用作 Docker `HEALTHCHECK`）。 | `healthcheck` 仅使用 `urllib.request` 访问 `127.0.0.1`，超时 2 秒，退出码 0/1。 |

## 4. 测试可追溯性

服务端（`server-sdk/tests/test_server/`）：`test_policy_config.py`（54：schema、预设、大小、未知键）、`test_path_guard.py`（34：遍历、符号链接、编码、NUL、长路径、deny glob）、
`test_policy_pipeline.py`（38：认证、scope、命令 scope、速率/并发、审计、发现、秘密）、`test_policy_paths.py`（30：transfer-only 场景、展开目录的端点、只读、`symlinks: never`、归档泄漏修复）、
`test_policy_exec.py`（16：命令/语言/URL 规则、秘密环境）、`test_http_hardening.py`（18：`Content-Length`、分帧、方法覆盖、路由归一化、请求体上限）、
`test_new_endpoints.py`（15：新增/扩展端点）、`test_policy_pty.py`（7）、`test_policy_compat.py`（5）、`test_cli_main.py`（8）。

客户端（`client-sdk/tests/`）：`test_api/server_e2e/test_server_client_e2e.py`（33，对真实进程内 `SandboxServer`）、`test_server_client_policy.py`（18）、
`test_server_client_models.py`（23：错误映射、模型、能力发现、旧版桩服务端）、`test_server_client_matrix.py`（4：路由完整性守卫）、`test_sandbox_server_helpers.py`（12）、
`test_api/test_base_image.py`（52）、`test_models/test_template_server_block.py`（18）。

没有专门测试的发现：R2-S17（路径长度 / glob CPU）只由 `test_path_guard.py` 中的长路径用例覆盖；R-B4（`healthcheck`）由 `test_cli_main.py` 覆盖。

## 5. 遗留的未决问题

* **OQ-1** `OFFICIAL_BASE_IMAGE` 的默认标签（文档为 `v0.0.49`；固定版本，可用 `ABX_BASE_IMAGE_TAG` 覆盖）：需要平台确认。
* **OQ-2** 按身份的路径 scope（R1-F7）。
* **OQ-3** 网关是否转发 `Authorization`？（R-B1）
* **OQ-4** 模板设置了自己的 `start_command` 时，网关对 CMD/ENTRYPOINT 的处理行为。
* **OQ-5** 在 GA 之前，需要真正独立的第三轮评审（人工或全新智能体）。
