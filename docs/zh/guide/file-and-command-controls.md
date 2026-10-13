# 文件与命令控制

模板如何限制沙箱服务器可以触及的路径和程序。这些路由的 HTTP 形状见[模板服务器 HTTP API](template-server-api.md)。`template.yaml` 的 `server:` 块见 [template.yaml 规范](../reference/template-yaml-spec.md#服务端策略server)。设计说明见[细粒度能力](../design/fine-grained-capabilities.md)。

实时路由会调用 `check_env`、`check_url` 和 `check_process`，下文的路径检查和命令检查也同样在路由里。`check_env` 用在 `handle_env_set`（`POST /env`）、`enforce_exec_policy`（`POST /shell`、`POST /shell/stream`、`POST /process/start` 的 `env` 对象）和 `_handle_create_session`（`POST /pty/sessions`）。`check_url` 用在 `handle_browser_navigate`（`POST /browser/navigate`）。`check_process` 用在 `enforce_exec_policy`（上述 shell 与进程的 argv）、`handle_code_run`（`POST /code/run`）和 `_handle_create_session`（PTY 的 shell）。拒绝是 HTTP 403，错误码是 guard 自己的码：`env_var_denied`、`url_denied` 或 `process_denied`。空的 env 映射仍然允许。

## 模板声明什么

`template.yaml` 里可选的 `server:`。没有它时，服务器保持原有行为：路径留在 `EBX_SERVER_BASE_DIR`（默认 `/home/user`）之下，shell 命令不做过滤。工具链把这块编译成 `/etc/easy-sandbox/server-policy.json`。进程在设置了 `EBX_SERVER_POLICY`（内联 JSON）或 `EBX_SERVER_POLICY_FILE` 时也会加载它们。`easy-sandbox-server check-config --policy <文件>` 校验文档并打印 lint 警告。无效文档会阻止启动。

```yaml
server:
  preset: transfer-only
  base_dir: /home/user
  groups:
    process: false
    terminal: false
  endpoints:
    files_download_stream:
      paths:
        allow: [/home/user/out]
        deny: ["**/.env", "*.pem"]
        read_only: false
        symlinks: within
      limits:
        max_bytes: 5MB
    files_upload_stream:
      paths:
        allow: [/home/user/in]
      params:
        overwrite: false
        deny_extensions: [".sh", ".so"]
    shell:
      params:
        allow_commands: ["ls", "cat"]
        deny_commands: ["rm"]
      limits:
        timeout_seconds: 30
        max_output_bytes: 1048576
```

预设在你的端点规则之前生效：`default`（没有额外限制）、`transfer-only`（只留上传和下载端点）、`read-only`（关掉 process、terminal、dev tools、browser，并关掉写端点）、`hardened`（关掉这些组，并在文件路由上加拒绝 glob）、`locked`（只留 `list_commands` 和 `run_command`）。

`paths.allow` 一旦给出，就取代 `base_dir`，成为该端点的边界。`paths.deny` 是目录前缀或 glob；不含 `/` 的模式匹配路径分量（`*.pem`、`.env`）。拒绝优先。`paths.read_only: true` 拒绝该端点上的写和删除。`paths.symlinks` 为 `within`（符号链接的目标留在边界内才允许）或 `never`。

## 文件路由实际执行什么

加载了策略时，文件处理函数调用 `EndpointContext.guard()`，用该端点的 `allow`、`deny`、`read_only`、`symlinks` 构造 `easy_sandbox.server.guard` 里的 `PathGuard`。`routes_files.py` 通过这个 guard 解析路径，并用 `open_checked` 打开文件（最后一段使用 `O_NOFOLLOW`）。列表、搜索和归档会跳过 guard 拒绝的条目。

没有策略时，上传、下载和 `files_*` 路由只用基目录检查。路径经过 `realpath`，必须是 `EBX_SERVER_BASE_DIR` 本身或其子路径。相对路径先按服务器进程的当前目录解析，然后仍然必须落在这个基目录里。这种模式下没有按端点划分的允许列表。

`guards/paths.py` 提供 `path_guard()` 和 `path_guard_from_context()`。这两个构造函数总是拒绝 `/proc`、`/sys`、`/dev`，并且拒绝把 `/` 当作根。`routes.py` 的上传、下载和 shell 的 `cwd` 通过 `path_guard_from_context` 解析路径。`routes_files.py` 的打开、列表、搜索和归档也使用同一个 guard。策略把 `paths.allow` 设成 `/` 时，仍然只是一条 lint 警告（`L2`）。不要把 `path_guard()` 写成模板旗标；`template.yaml` 里没有任何字段会打开它。

## 命令路由实际执行什么

`POST /shell`、`POST /shell/stream`、`POST /process/start` 用 `shlex` 拆开 `command`，并以 `shell=False` 运行 `argv`。加载了策略时，`routes.py` 的 `_check_command` 调用 `check_command`，用 `params.allow_commands` 和 `params.deny_commands` 构造 `CommandGuard`。先检查拒绝列表。空的 `allow_commands` 表示没有允许列表。非空列表则必须命中。错误码是 `command_not_allowed`（HTTP 403）。

允许项如果只有可执行文件名，就只匹配 `argv[0]`，所以 `allow_commands: ["ls"]` 会放行 `ls -la`。允许项如果还有更多片段，就匹配整条参数：`cat {path}` 会钉住路径参数，`...` 跳过一段，`{int}` 匹配整数。组合短旗标会展开，因此拒绝 `-R` 也会拒绝 `-lR`。`cwd` 用 `path_guard_from_context` 解析，并且必须是已存在的目录。`limits.timeout_seconds` 封顶 `timeout`。`limits.max_output_bytes` 截断 `/shell` 的输出并设置 `"truncated": true`。

命名命令是另一张表。`POST /commands/{name}` 运行 `commands.py` 里用 `@registry.command` 注册的函数。它不查阅 `allow_commands`。

## 什么仍然能绕过路径规则

同一个身份既能使用带路径范围的文件端点，又能执行程序（`shell`、`shell_stream`、`process_start`、`code_run`、PTY）时，策略 linter 会警告（`L1`）。服务器允许这种组合；这条警告是关掉 `process` 和 `terminal`，或给 `shell` 加上 `allow_commands` 的信号。`code_run` 用的是 `params.languages`，不是 `allow_commands`。PTY 的 shell 用 `pty_create_session` 上的 `params.shells`，不是 `allow_commands`。
