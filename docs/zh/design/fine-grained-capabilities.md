# 细粒度能力、路径范围与权限

> 状态：**v2（已评审）**。v1 草案经过 [fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md)
> 记录的两轮评审；评审结论已并入下文，并在第 11 节汇总。
> 范围：`agent-sandbox-server`（`agent_sandbox.server`）的强制执行、`template.yaml` 声明式配置，以及
> `agent-sandbox`（`agent_sandbox`）客户端的发现 / 错误 / 辅助方法。
> 相关文档：[client-server-alignment.md](client-server-alignment.md)、
> [base-image-and-server-sdk.md](base-image-and-server-sdk.md)、[server-api.md](server-api.md)。
> 英文版为准：[../../en/design/fine-grained-capabilities.md](../../en/design/fine-grained-capabilities.md)。

## 1. 问题

服务端目前以**粗粒度能力组**（`FILE_OPS`、`PROCESS` 等）暴露端点。打开 `FILE_OPS` 会一次性暴露 11 个端点
（list、stat、mkdir、delete、move、search、upload、download、archive、旧版 upload/download），并且只受一个进程级的
`ABX_SERVER_BASE_DIR` 约束。产品需要更细的控制：

* **只**暴露上传和下载端点；
* 下载只能从指定目录进行；
* 逐端点的权限（谁能调用什么）、大小限制、只读模式；
* 同一套规则对客户端 SDK 可见，并被一致地执行。

非目标：这**不是**操作系统级沙箱。路径范围是 API 层面的控制；如果同一调用方还能运行任意进程（`shell`、`code_run`、PTY、
`process_start`），就能绕过任何文件规则。服务端会对这种组合给出 lint 警告（见 3.9）。

## 2. 设计原则

1. **一个引擎，始终开启。** 没有"未配置"的代码路径。没有策略就是空策略，仍然套用默认边界（`/home/user`）和可选组。项目尚未发布，
   不为兼容保留任何东西。
2. **失败即关闭。** 存在但无效的策略会使服务端无法启动，绝不退化为"全部放行"。
3. **单一决策点，以匹配到的路由为键。** 策略附着在路由器选中的 `RouteInfo` 上，而不是重新解析的 URL 字符串，因此路由器与策略之间
   不会出现差异（编码路径、方法覆盖、尾部斜杠）。
4. **只解析一次，使用解析后的值。** 路径检查返回的解析结果就是后续操作所用的路径（不二次解析）；打开文件时防范符号链接替换。
5. **收窄容易，放宽必须显式。** 预设从拒绝姿态开始；deny 规则在各选择器间累加；allow 根目录必须显式给出。
6. **发现 <= 执行。** 调用方看到的（并可预检查的）恰好是它能使用的。
7. **一份 schema，两种写法。** JSON 策略（标准库服务端）== `template.yaml` 的 `server:` 块（由工具链编译为 JSON）。

## 3. 模型

### 3.1 端点标识

每个内置路由已有稳定的 `name`（`files_list`、`files_download_stream`、`shell`、`process_signal` 等）。该名称就是策略、发现、
审计和客户端错误中使用的**端点 ID**。方法 + 路径**不是**标识。通过 `RouteTable.route(...)` 注册的自定义路由同样按其 `name` 处理。

为客户端/服务端对齐新增的内置端点（见对齐文档）：`files_watch`、`process_stdin`、`process_output`、`pty_detail`、`pty_resize`、
`capabilities_check`。

### 3.2 Scope（权限模型）

每个端点要求一组 **scope**（须全部满足）。默认值来自内置目录（`policy.ENDPOINT_CATALOG`；单元测试保证每个已注册的内置路由都有条目）。

| Scope | 默认对应的端点 |
|-------|----------------|
| `core:read` | `capabilities`、`capabilities_check`（每个已认证身份隐含拥有） |
| `commands:list` / `commands:run` | `list_commands` / `run_command`（外加按命令的 scope，3.8） |
| `files:read` | `download`、`files_list`、`files_stat`、`files_search`、`files_download_stream`、`files_archive`、`files_watch` |
| `files:write` | `upload`、`files_mkdir`、`files_upload_stream` |
| `files:write` + `files:delete` | `files_move` |
| `files:delete` | `files_delete` |
| `process:run` | `shell`、`shell_stream`、`process_start` |
| `process:read` | `process_list`、`process_detail`、`process_output` |
| `process:manage` | `process_signal`、`process_stdin` |
| `terminal:use` | `pty_*` 与 PTY WebSocket |
| `system:read` / `system:write` | `system_info`、`system_metrics`、`ports`、`packages`、`env_get` / `env_set` |
| `devtools:run` / `devtools:read` | `code_run` / `git_status`、`git_diff` |
| `browser:use` / `browser:evaluate` | `browser_*` / `browser_evaluate` |

Scope 语法：`namespace:action`；`*` 授予全部；`namespace:*` 授予整个命名空间。`health` 无需认证（不变）。

### 3.3 身份与令牌

今天：一个可选的 `ABX_SERVER_TOKEN`，与 `X-Access-Token` 比对。

* **默认不变。** 无令牌 -> 具有 scope `*` 的匿名身份（本地模式）。一个 `ABX_SERVER_TOKEN` -> 身份 `legacy`，scope `*`
  （可通过 `auth.legacy_scopes` 覆盖）。
* **新增：** `auth.tokens`，形如 `{id, scopes, token_env | token_sha256}` 的列表。文件中永远不接受明文令牌（烤进镜像的文件里的秘密就是泄漏）。
  `token_env` 指定启动时读取的环境变量名；`token_sha256` 是令牌的十六进制摘要。
* 存在 `auth.tokens` 时禁用匿名访问（`auth.allow_anonymous: true` 并配合 `auth.anonymous_scopes` 可重新开启）。
* **传输。** `X-Access-Token`（与 FC 网关头兼容）*或* `Authorization: Bearer <token>`。两者同时出现时，服务端身份使用 `Authorization`
  头（网关令牌合理地可能不同）。
* 对**所有**已配置令牌做恒定时间比较（先取摘要再 `compare_digest`，不提前退出），响应时间不会泄露匹配的是哪一个令牌。

### 3.4 端点规则

```jsonc
{
  "version": 1,
  "preset": "default",                // default | transfer-only | read-only | hardened | locked
  "base_dir": "/home/user",           // 可选；覆盖 ABX_SERVER_BASE_DIR
  "groups": { "dev_tools": true },    // 该组端点 id 的别名；也可以写列表 ["dev_tools"]
  "defaults": { "audit": "deny", "limits": { "max_request_bytes": 10485760 } },
  "auth": {
    "tokens": [
      { "id": "uploader", "token_env": "ABX_TOKEN_UPLOADER", "scopes": ["files:write"] },
      { "id": "reader",   "token_sha256": "9f86d0...", "scopes": ["files:read"] }
    ]
  },
  "endpoints": {
    "*":                       { "enabled": false },               // 通配选择器
    "files_download_stream":   {
      "enabled": true,
      "scopes": ["files:read"],                                    // 替换目录默认值
      "paths": { "allow": ["/home/user/out"], "deny": ["**/.env", "**/*.pem"],
                 "read_only": false, "symlinks": "within" },
      "limits": { "max_bytes": 5242880, "rate_per_minute": 60, "max_concurrency": 4 },
      "audit": "all"
    },
    "files_upload_stream": {
      "enabled": true,
      "paths": { "allow": ["/home/user/uploads"] },
      "limits": { "max_bytes": 10485760 },
      "params": { "overwrite": false, "deny_extensions": [".sh", ".so"] }
    }
  }
}
```

**选择器**（`endpoints` 的键）：精确 ID、通配（`files_*`、`*`）或 `group:<name>`。
**合并顺序**（后者优先，按字段）：内置默认 < 预设 < `defaults` < `group:` 规则 < 通配规则（字面前缀短者在前）< 精确规则。
字段合并语义：标量和 `allow` 列表**替换**；`deny` 列表与 `deny_*` 参数**取并集**；同一特异度下 `enabled: false` 胜过 `true`。

**组是别名，不是闸门。** `groups: {file_ops: false}`、`groups: [agents]`、`table.enable_group(...)` 和
`ABX_SERVER_ENABLED_GROUPS=agents` 都展开成该组的端点 id，并成为五层之一里的普通端点规则：default（可选组一开始是关的）、
code（`enable_group` / `disable_group`）、preset、policy、environment（只能打开）。没有单独的组闸门，也没有组级状态。更具体的选择器优先
（精确 id > glob > `group:` > `@defaults`），然后是更靠后的层；同样具体、同一层时，一条 `enabled: false` 胜出。每次拒绝都会指出规则
（`policy:endpoints.shell`、`preset:read-only`、`code:enable_group:file_ops`、`default:opt-in:browser`）。`CORE` 端点
（`health`、`capabilities`、`capabilities_check`）不能被禁用。

### 3.5 路径范围

对接受文件系统路径的端点（`files_*`、`upload`、`download`、`git_*`，以及 `shell`、`shell_stream`、`process_start` 的 `cwd`；`code_run` 没有 cwd）：

* `paths.allow`：绝对目录。**存在时它取代 `base_dir` 成为该端点的边界**（因此即使 `base_dir` 是 `/home/user`，也可以只暴露 `/tmp/exports`）。
  缺省 -> `base_dir`（行为不变）。每次请求都会对 allow 根目录做 `realpath`。
* `paths.deny`：绝对目录前缀或 glob 模式（`**/.env`、`*.pem`）。不含 `/` 的模式匹配基本名。deny 永远优先，作用于*解析后*的路径。
* `paths.read_only`：拒绝该端点上的写/删除操作（每个端点的操作分为 `read`、`write`、`delete`、`exec`）。
* `paths.symlinks`：`within`（默认；只要*目标*仍在允许边界内即可跟随符号链接）或 `never`（请求路径中出现任何符号链接即拒绝）。

算法（`PathGuard.resolve(raw, op)`）：拒绝 NUL/非字符串 -> 转为绝对路径（相对路径的解析见下方兼容说明）-> `realpath` -> 边界检查 -> deny 检查 ->
只读检查 -> 返回解析后的路径。策略在**任何**存在性检查**之前**求值，因此错误响应不会成为文件系统的探测口。打开文件时对最后一个路径分量使用
`O_NOFOLLOW`，并重新校验已打开的 fd（`/proc/self/fd/N`，回退为 `fstat` 身份比较），以缩小检查/使用之间的窗口。

兼容说明：今天相对路径相对服务进程的 CWD 解析。未配置策略时保持不变；配置了 `paths.allow` 时相对路径相对第一个 allow 根目录解析，这是唯一合理的解读。

展开目录的端点对**每个产出的条目**都执行策略：`files_list` 与 `files_search` 省略被拒绝的条目且不会进入被拒绝的目录；`files_archive`
排除被拒绝的后代，并拒绝指向边界之外的文件符号链接（这也修复了现有 `zipfile` 的符号链接读取问题）。

### 3.6 限制与参数

每个端点的词汇表是封闭的（未知键是校验错误，因此笔误会明显失败）。

| 位置 | 键 |
|------|----|
| 所有端点 | `limits.max_request_bytes`、`limits.rate_per_minute`、`limits.max_concurrency`、`audit` |
| `upload`、`files_upload_stream` | `limits.max_bytes`；`params.overwrite`、`params.allow_extensions`、`params.deny_extensions` |
| `download`、`files_download_stream` | `limits.max_bytes` |
| `files_list` | `limits.max_entries`、`limits.max_depth` |
| `files_search` | `limits.max_results`、`limits.max_depth`、`limits.timeout_seconds` |
| `files_archive` | `limits.max_files`、`limits.max_bytes` |
| `files_watch` | `limits.max_duration_seconds` |
| `shell`、`shell_stream`、`process_start` | `params.allow_commands`、`params.deny_commands`（argv[0] 的基本名*和*完整路径）、`limits.timeout_seconds`（上限）、`limits.max_output_bytes`、`limits.max_processes` |
| `process_signal` | `params.allowed_signals` |
| `pty_create_session` | `params.shells`、`limits.max_sessions`、`params.env_deny` |
| `env_get`、`env_set` | `params.allow_vars`、`params.deny_vars`（glob） |
| `code_run` | `params.languages`、`limits.timeout_seconds`、`limits.max_output_bytes` |
| `browser_navigate` | `params.url_allow`、`params.url_deny`、`params.block_private_networks` |

未设置时限制取*今天的*常量。已配置的限制只会是用户写下的值，没有隐藏的上限。

### 3.7 速率限制、并发、审计

按 `(身份, 端点)` 的令牌桶（`rate_per_minute`，突发 = 速率）和信号量（`max_concurrency`）。超限返回 `429` + `Retry-After`。审计事件写入
`agent_sandbox.server.audit` 日志器，每行一个 JSON 对象：`ts, identity, endpoint, method, decision, code, status, paths(解析后，截断)`，
绝不包含令牌、请求体或文件内容。`audit`：`off` | `deny`（默认）| `all`。

### 3.8 按命令的 scope（自定义命令）

`registry.command("deploy", scopes=["deploy"])`：调用方需要 `commands:run` **和** `deploy`。`GET /commands` 只列出调用方可以运行的命令（发现 <= 执行）。

### 3.9 Lint

`ServerPolicy.lint()` 返回人类可读的警告，在启动时记录日志，并由 `agent-sandbox-server check-config` 打印：配置了路径范围，同时同一批 scope 可以访问
`process`/`terminal`/`dev_tools`/`browser` 端点；allow 根目录为 `/`；定义了其他令牌却给某令牌通配 scope；`overwrite: false` 却没有 `paths.allow`；等等。

### 3.10 子进程环境

配置了 `auth.tokens` 时，由 `shell*`、`process_start`、`code_run`、`git_*` 和 PTY 会话启动的子进程拿到 `os.environ` **去掉** `ABX_SERVER_TOKEN`、
`ABX_SERVER_POLICY*` 以及所有 `token_env` 变量，使 `process:run` 身份无法读取其他身份的秘密。未配置的服务端保持今天的行为。（只会去掉服务端自己的秘密，从不触碰任意用户变量。）

## 4. 配置入口

解析顺序（低 -> 高）：代码默认值 < 约定文件（存在时 `/etc/agent-sandbox/server-policy.json`）< `ABX_SERVER_POLICY_FILE` <
`ABX_SERVER_POLICY`（内联 JSON）< `SandboxServer(policy=...)`（取最高的现存来源，来源之间不合并）。`ABX_SERVER_BASE_DIR`、
`ABX_MAX_UPLOAD_SIZE`、`ABX_SERVER_TOKEN` 作为最低优先级输入读取。唯一的组环境变量是 `ABX_SERVER_ENABLED_GROUPS`（打开，environment 层）；
没有用来关闭组的变量。

Python：

```python
from agent_sandbox.server import SandboxServer, ServerPolicy

policy = ServerPolicy.from_dict({
    "preset": "transfer-only",
    "endpoints": {"files_download_stream": {"paths": {"allow": ["/home/user/out"]}}},
})
SandboxServer(policy=policy).serve(9000)
```

辅助方法：`ServerPolicy.preset(name, **overrides)`、`ServerPolicy.only(*endpoint_ids, paths=None, **rule)`、`ServerPolicy.from_file(path)`、
`policy.with_endpoint(selector, **rule)`、`policy.explain(endpoint, *, scopes, path=None, op=None)` -> 判定（调试辅助）。

声明式（`template.yaml`）：

```yaml
server:
  preset: transfer-only
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out] }
      limits: { max_bytes: 5MB }          # 支持人类可读大小：5MB、1GiB
```

大小字符串（`5MB`、`1GiB`）在 YAML/JSON 中均可使用，由加载器规范化为整数。客户端 SDK 校验该块（`SandboxTemplate.server`），工具链把它编译为
`server-policy.json`，放到镜像中的 `/etc/agent-sandbox/server-policy.json`（CLI 跟进项）。容器内服务端保持仅标准库：原生支持 JSON，仅当碰巧安装了 PyYAML 时才支持 YAML。

预设（都是普通策略字典，见 `server-api.md`）：`default`（今天的行为）、`transfer-only`、`read-only`、`hardened`、`locked`。

## 5. 请求流水线

```
route = match(method, raw_path)                 # 不接受任何覆盖头/参数
identity = authenticate(headers)                # 401（auth_required=False 时跳过）
rule gate: enabled -> scopes -> rate -> concurrency       # 404 endpoint_disabled(+rule) / 403 / 429
重复的查询参数                                            # 400
body gate: Content-Length 合法 -> <= max_request_bytes    # 400 / 413（读取之前）
handler(request, request.context["policy"]=EndpointContext)
   PathGuard / 限制 / 参数在处理器内部、对其实际使用的*同一批值*执行
audit(decision)
```

处理器抛出 `PolicyDenied(code, message, ...)`，分发器映射为 `403`。每个处理器都会收到 `EndpointContext`；没有无上下文的模式。

## 6. 发现契约

`GET /capabilities`（需认证）保持向后兼容（保留 `groups`），并新增：`api_version: 2`、`server_version`、`identity {id, scopes}`、`policy {preset, revision}`、
`groups` 和 `group_summary`（由端点状态推导）、`endpoints{name -> {method, path, group, summary, streaming, enabled, allowed, reason, rule, scopes, limits, paths{allow, read_only, deny_count}, params}}`、
`warnings`（仅对持有 `*` 的身份）。`POST /capabilities/check` `{endpoint, path?, op?, paths?}` 返回服务端对一次假设调用的权威判定
（只做策略计算，从不触碰文件系统），客户端无需重新实现路径规则。`revision` 是有效策略的哈希，缓存可据此失效。

## 7. 错误契约

所有错误响应体保留 `{"error", "type"}`，并新增 `code`（稳定的机器字符串）以及可选的 `endpoint`、`scope`、`retry_after`。

| HTTP | `type` | `code` 示例 |
|------|--------|-------------|
| 401 | `AuthError` | `unauthorized` |
| 403 | `PolicyDenied` | `missing_scope`、`path_not_allowed`、`path_denied`、`read_only`、`symlink_denied`、`command_not_allowed`、`language_not_allowed`、`signal_not_allowed`、`shell_not_allowed`、`url_denied`、`extension_not_allowed`、`env_var_not_allowed`、`env_var_denied`、`process_denied` |
| 404 | `ValueError` | `endpoint_disabled`（+ `rule`） |
| 409 | `FileExistsError` | `file_exists`（`overwrite: false` 的上传） |
| 413 | `ValueError`（保留） | `payload_too_large`（+ `limit`） |
| 429 | `RateLimited` | `rate_limited`、`concurrency_limited` |

客户端异常（新的 `E9xxx` 系列，语义吻合时继承现有类，使现有 `except` 子句继续有效）：`ServerAPIError`（E9000）、`ServerAuthError`（E9001，同时是
`AuthenticationError`）、`PolicyDeniedError`（E9002；`FilePolicyDeniedError` 同时是 `PermissionDeniedError`）、`EndpointNotAvailableError`（E9003，同时是
`CapabilityNotSupportedError`）、`PayloadTooLargeError`（E9004）、`RateLimitedError`（E9005，`retry_after`）。操作系统层面的 404/403 映射到现有的
`FileNotFoundError_` / `PermissionDeniedError`；进程超时映射到 `CommandTimeoutError`。

## 8. 客户端 SDK

* `agent_sandbox.api.server_client.ServerClient`：覆盖**每一个**服务端端点的类型化异步客户端，带 `*_sync` 孪生方法（见对齐文档）；
  `Sandbox.server`（9000 端口）与 `Sandbox.server_at(port, token=...)` 返回绑定到沙箱端口 URL 和网关头的实例。
* `await client.discover()` -> `ServerCapabilities`，提供 `can(endpoint)`、`require(endpoint)`、`limit(endpoint, key)`、`check_path(endpoint, path, op)`
  （服务端检查）和 `endpoints_for(scope)`。方法会查询已填充的缓存，并在网络往返*之前*以类型化错误快速失败；服务端响应仍然权威，并映射为相同的异常。
  客户端绝不会发起隐式的发现请求。
* `template.yaml` 新增 `server:`（由 `SandboxTemplate` 做结构校验；未知键被拒绝）。

## 9. 没有策略时的行为

| 行为 | 取值 |
|------|------|
| 默认能力组 | 除 `dev_tools`、`browser`、`agents` 外全部（这三组是可选的） |
| `ABX_SERVER_TOKEN` / `X-Access-Token` 或 `Authorization: Bearer` | 全有或全无；身份 `legacy`，scope `*`（没有令牌时是 `anonymous`） |
| 路径边界 | 所有接收路径的端点（含 shell 的 `cwd`）都在 `ABX_SERVER_BASE_DIR`（默认 `/home/user`）内；违规是 `403 path_not_allowed` |
| `GET /capabilities` | 逐端点状态、`rule`，以及推导出的 `groups` 和 `group_summary` |
| 错误响应体 | `{error,type}`，按需加 `code`、`endpoint`、`rule` |
| 相对路径解析 | 服务端 CWD，之后仍须在边界内 |
| 不支持的 HTTP 方法 | stdlib 501 |
| 能力开关 | 只有一层：端点规则（`enable_builtin`、`disable_builtin` 和 `ABX_SERVER_DISABLED_GROUPS` 都不存在） |

## 10. 安全测试计划（绕过矩阵）

路径：`..`、`//`、`/./`、尾部斜杠、指向外部 / 内部到被拒绝位置的符号链接、符号链接替换（`symlinks: never`）、`%2e%2e` 与双重编码 `%252e%252e`、NUL 字节、
Unicode 形近字符、超长路径、重复的 `path=` 查询参数、相对路径与 allow 根目录、deny glob 的大小写变体、archive/search/list 泄漏被拒绝条目、
`files_move` 进出范围、存在性探测的顺序。传输：方法覆盖头/参数、HEAD/PUT/PATCH、负数或非数字的 `Content-Length`、超过端点上限的请求体、分块编码、两个 `X-Access-Token` 头。
鉴权：错误/缺失/其他身份的令牌、经 `shell` 的 scope 提升、按命令 scope、发现列表、速率与并发耗尽、经 `GET /env` 和子进程的令牌暴露。

## 11. 评审后的变更（v1 -> v2）

完整发现见 [fine-grained-capabilities-review.md](../archive/fine-grained-capabilities-review.md)。

* **`ServerPolicy.only(*ids)`** 是规范性的：先禁用所有非核心端点，再启用列出的 ID；令牌 `"transfer"` 展开为 `upload`、`download`、`files_upload_stream`、
  `files_download_stream`。`transfer-only` 预设就是带默认大小上限的同一件事。
* 多路径端点的**路径角色**：`files_move` 的源是 `delete`，目标是 `write`；两者都必须通过 allow/deny/只读检查。归档/搜索/列表会重新检查*每个产出的条目*。
* **字节限制**：请求体由 `max_request_bytes`（默认为传输上限）约束，作用于读取请求体*之前*已校验的 `Content-Length`；`max_bytes` 约束解码后的负载；策略模式下拒绝分块
  `Transfer-Encoding`；上传中止时删除不完整文件。（没有计数读取器：服务端恰好读取声明的长度。）
* **严格配置**：未知键和未知的精确端点 ID 都是错误，附带拼写建议和 JSON 路径。
* **所有模式下的 HTTP 加固**（缺陷修复）：严格的 `Content-Length`（非数字/负数/重复 -> 400），zip 归档永远不跟随指向边界之外的符号链接。
* **仅策略模式的加固**：拒绝重复的查询参数和 `Transfer-Encoding`；在任何 `stat` 之前做边界/deny 检查（没有存在性探测口）；相对路径相对第一个 allow 根目录解析；拒绝歧义的凭据头；优先使用 `Authorization: Bearer`。
* **秘密**：身份模式下 `GET /env` 脱敏服务端自己的秘密（`ABX_SERVER_*` 和所有 `token_env` 名称）；`env_set` 拒绝它们以及 `ABX_` 前缀；子进程环境只去掉相同的名称。
  任意用户变量不会被触碰（旧模式的 `GET /env` 仍返回完整环境；可用 `endpoints.env_get` / `groups.system` 加以限制）。
* **PTY WebSocket** 受策略覆盖（`pty_connect`，scope `terminal:use`，头部认证）；旧的 `?token=` 仍可用。
* **自定义路由**可以声明 `scopes=`，并接收 `request.context["policy"]`。
* **残余风险**（已记录，标准库 Python 无法彻底消除）：检查与打开之间中间路径分量的符号链接替换、通过进程端点创建的硬链接、按 IP 的暴力破解限流（交给网关）。
  Lint L1（`process`/`terminal`/`dev_tools`/`browser` 与路径范围同时可达）覆盖前两项。
* **推迟**：按身份的路径 scope（OQ-2）。
* `Image()` 默认基础镜像不变；官方基础镜像是可选的（见基础镜像文档）。
