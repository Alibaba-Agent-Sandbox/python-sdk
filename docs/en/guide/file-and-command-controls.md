# File and command controls

How a template limits which paths and which programs the sandbox server will touch. How to turn the policy on, and the full endpoint catalogue, are in [Fine-grained capabilities](fine-grained-capabilities.md). The HTTP shapes of those routes are in the [template server HTTP API](template-server-api.md). The `server:` block of `template.yaml` is specified in the [template YAML spec](../reference/template-yaml-spec.md#server-policy-server). The design notes are in [Fine-grained capabilities](../design/fine-grained-capabilities.md).

The live routes call `check_env`, `check_url`, and `check_process` as well as the path and command checks below. `check_env` runs in `handle_env_set` (`POST /env`), in `enforce_exec_policy` (the `env` object on `POST /shell`, `POST /shell/stream`, and `POST /process/start`), and in `_handle_create_session` (`POST /pty/sessions`). `check_url` runs in `handle_browser_navigate` (`POST /browser/navigate`). `check_process` runs in `enforce_exec_policy` (argv for those shell and process routes), in `handle_code_run` (`POST /code/run`), and in `_handle_create_session` (the PTY shell). A denial is HTTP 403 with the guard's code: `env_var_denied`, `url_denied`, or `process_denied`. An empty env map stays allowed.

## What a template declares

Optional `server:` in `template.yaml`. Absent means the default policy: every path an endpoint takes stays under `ABX_SERVER_BASE_DIR` (default `/home/user`), including the `cwd` of `/shell` and process start, and shell commands are not filtered. Tooling compiles the block to `/etc/agent-sandbox/server-policy.json`. The process also loads `ABX_SERVER_POLICY` (inline JSON) or `ABX_SERVER_POLICY_FILE` when either is set. `agent-sandbox-server check-config --policy <file>` validates the document and prints lint warnings. An invalid document prevents startup.

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

Presets, applied before your endpoint rules: `default` (no extra restriction), `transfer-only` (upload and download endpoints only), `read-only` (process, terminal, dev tools, and browser off; write endpoints off), `hardened` (those groups off, plus deny globs on file routes), `locked` (only `list_commands` and `run_command`).

`paths.allow`, when present, replaces `base_dir` as the boundary for that endpoint. `paths.deny` is a directory prefix or a glob; a pattern with no `/` matches a path component (`*.pem`, `.env`). Deny wins. `paths.read_only: true` rejects write and delete on that endpoint. `paths.symlinks` is `within` (a symlink is allowed when the target stays inside the boundary) or `never`.

## What the file routes enforce

There is one policy engine and it is always present; no policy is an empty policy with the default boundary. Every handler receives an `EndpointContext`. File handlers call `EndpointContext.guard()`, which builds the `PathGuard` in `agent_sandbox.server.guard` from that endpoint's `allow` (the policy's `paths.allow`, else `base_dir`, else `ABX_SERVER_BASE_DIR`, else `/home/user`), `deny`, `read_only`, and `symlinks`. `routes_files.py` resolves the path through that guard and opens files with `open_checked` (`O_NOFOLLOW` on the final component). List, search, and archive skip entries the guard denies. A relative path is resolved from the server process's current directory and then still has to land inside the boundary.

The guard always denies `/proc`, `/sys`, and `/dev`, and refuses a root of `/`. Upload, download, and the `cwd` of shell and process start resolve through the same guard. A policy that sets `paths.allow` to `/` is still a lint warning (`L2`).

A path outside the boundary is HTTP 403 with `code: path_not_allowed`. The body names the endpoint. A denied endpoint is a different answer: HTTP 404 with `code: endpoint_disabled` and the `rule` that turned it off (see [Fine-grained capabilities](fine-grained-capabilities.md)).

## What the command routes enforce

`POST /shell`, `POST /shell/stream`, and `POST /process/start` split `command` with `shlex` and run `argv` with `shell=False`. `routes.py` `_check_command` calls `check_command`, which builds a `CommandGuard` from `params.allow_commands` and `params.deny_commands`. Deny is checked first. An empty `allow_commands` means there is no allow list. A non-empty list requires a match. The error code is `command_not_allowed` (HTTP 403).

An allow entry that is only an executable name matches `argv[0]`, so `allow_commands: ["ls"]` admits `ls -la`. An entry with more tokens matches the whole argument list: `cat {path}` pins the path argument, `...` skips a span, and `{int}` matches an integer. Grouped short flags are expanded, so a deny of `-R` also denies `-lR`. `cwd` goes through the path guard (`403` `path_not_allowed` outside the boundary) and must be an existing directory. `limits.timeout_seconds` caps `timeout`. `limits.max_output_bytes` truncates `/shell` output and sets `"truncated": true`.

Named commands are a separate list. `POST /commands/{name}` runs a function registered with `@command` in `commands.py` (the one way to register a named command). It does not consult `allow_commands`. A command's own `scopes` are checked against the caller.

## What still bypasses a path rule

The policy linter warns (`L1`) when one identity can both use a path-scoped file endpoint and execute a program (`shell`, `shell_stream`, `process_start`, `code_run`, PTY). That combination is allowed by the server; the warning is the signal to turn `process` and `terminal` off, or to put `allow_commands` on `shell`. `code_run` has `params.languages`, not `allow_commands`. PTY shells use `params.shells` on `pty_create_session`, not `allow_commands`.
