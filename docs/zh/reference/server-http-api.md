# Server HTTP API 参考

沙箱内服务端（`agent_sandbox.server`，端口 9000；PTY WebSocket 在 9001）的线上契约。逐路由的行为见[模板服务器 HTTP API](../guide/template-server-api.md)。Agents 路由见 [Agents API 参考](agents-api.md)。设计背景见 [Server API 设计文档](../design/server-api.md)。

## 每个端点一个 id

每条路由是一个端点，有一个 id（`files_download`、`shell`、`agents_sessions_create`）。策略、审计日志、`GET /capabilities` 和客户端用的是同一个 id。共 118 个端点：`core` 3、`commands` 2、`file_ops` 12、`process` 8、`terminal` 6（含 WebSocket `pty_connect`）、`system` 6、`dev_tools` 3、`browser` 8、`agents` 70。声明表是 `agent_sandbox.server.endpoints.ENDPOINTS`。表外的东西不会被提供，也没有 `/ops` 或 RPC 路由。

## 一条管线

每个请求按同样的顺序经过：

1. 把方法和路径匹配到端点。匹配不到是 `404` `Not found: <path>`。
2. 认证：`Authorization: Bearer <token>` 或 `X-Access-Token`。缺失或错误是 `401` `unauthorized`。两个不同的 `X-Access-Token` 值是 `400` `ambiguous_credentials`。
3. 经策略引擎放行：端点必须是开的（`404` `endpoint_disabled`，带 `rule`），调用方必须具备 scope（`403` `missing_scope`），频率和并发上限必须还有余量（`429`）。
4. 重复的查询参数是 `400` `duplicate_parameter`。
5. 读取正文之前先检查大小上限（10 MiB）：`413` `payload_too_large`。
6. 处理函数运行。路径、命令、进程、环境变量和 URL 的 guard 在这里应答。
7. 写审计记录（`audit: off|deny|all`）。

`GET /health` 是唯一跳过第 2 步的路由。

## 错误体

```json
{"error": "<message>", "type": "<ExceptionName>", "code": "<machine code>", "endpoint": "<endpoint id>"}
```

策略和 guard 的拒绝会带 `code` 和 `endpoint`。被关闭的端点还带 `rule`。`/v1/` Agents 路由使用 OpenAI 信封 `{"error": {"message", "type", "param", "code"}}`。

| `code` | 状态 | 含义 |
|---|---|---|
| `unauthorized` | 401 | 令牌缺失或错误 |
| `ambiguous_credentials` | 400 | 一个请求里有两个不同的凭据值 |
| `endpoint_disabled` | 404 | 端点是关的。`rule` 指出是哪一层，例如 `policy:endpoints.shell`、`preset:read-only`、`code:enable_group:file_ops`、`env:ABX_SERVER_ENABLED_GROUPS:agents`、`default:opt-in:browser` |
| `missing_scope` | 403 | 调用方缺少端点（或命令）需要的 scope |
| `scope_required` | 403 | 命令 guard 里没有能放行该调用的允许项 |
| `path_not_allowed` | 403 | 路径在允许的目录之外（包括 shell 的 `cwd`） |
| `path_denied` | 403 | 路径命中 `paths.deny` 的模式 |
| `read_only` | 403 | 端点的 `paths.read_only` 拒绝写和删除 |
| `symlink_denied` | 403 | `paths.symlinks` 拒绝符号链接 |
| `invalid_path` | 400 | 缺失、含 NUL 字节或过长 |
| `command_not_allowed` | 403 | `allow_commands` / `deny_commands` 拒绝该命令 |
| `command_invalid`、`process_invalid` | 400 | 可执行文件为空或格式错误 |
| `process_denied` | 403 | 进程 guard 拒绝该程序 |
| `env_var_denied`、`env_var_not_allowed` | 403 | 环境变量被拒绝 |
| `env_invalid`、`url_invalid` | 400 | 环境变量表或 URL 格式错误 |
| `url_denied` | 403 | `url_allow` / `url_deny` / 私网规则拒绝该 URL |
| `language_not_allowed` | 403 | `code_run` 的语言不在 `params.languages` 里 |
| `extension_not_allowed` | 403 | 上传后缀被拒绝 |
| `file_exists` | 409 | `overwrite: false` 且文件已存在 |
| `payload_too_large` | 413 | 正文或文件超过上限 |
| `rate_limited`、`concurrency_limited` | 429 | 上限用尽，带 `Retry-After` |
| `duplicate_parameter` | 400 | 查询参数重复 |

## 发现

`GET /capabilities` 返回每个端点对调用方的状态（`enabled`、`allowed`、`reason`、`rule`、`scopes`、limits），以及推导出的 `groups` 和 `group_summary`。`POST /capabilities/check` 回答某个端点（可再带一个路径）是否会被允许，不会真的执行。两者见[模板服务器 HTTP API](../guide/template-server-api.md)。

## 切换端点

只有一层说了算：端点规则。组名是它的端点 id 的别名。见[细粒度能力](../guide/fine-grained-capabilities.md)。唯一的组环境变量是 `ABX_SERVER_ENABLED_GROUPS`。
