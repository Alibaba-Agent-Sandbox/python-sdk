# Decision: Server SDK v2 guards package (path and command guards callable from the policy engine)

Status: proposed

## Problem
Design 03 (sections 6, 7, 15.3) and plan 10 (WP-3, `guards/{paths,commands}.py`) call for path scopes (allow roots, deny globs, read-only, non-removable system deny list) and command scopes (normalised argv, deny pass, allow-list, no shell by default). Today the checks are split: `server/guard.py` (`PathGuard`) and a private `_check_command` in `routes.py` (fnmatch on `argv[0]` only; `ls -lR` style aliases and argument pinning are impossible).

## Decision
New stdlib-only package `agent_sandbox/server/guards/`; `guard.py`, `policy.py`, `routes.py` and every error code are untouched (the v1 dispatcher stays).

| Module | Content |
|---|---|
| `paths.py` | re-exports `PathGuard`, `open_checked`, `OP_*`; `path_guard(*roots, deny, readonly, symlinks)` (refuses no root, `/`, relative or glob roots; always adds `SYSTEM_DENY = /proc /sys /dev`); `path_guard_from_context(ctx)` wraps `EndpointContext.guard()` plus the system deny list |
| `commands.py` | `CommandGuard(allow, deny, shell, path_guard, require_allow, legacy_codes)`; `normalise(command xor argv)`; `expand_short_flags`; `command_guard(...)` (fail-closed); `command_guard_from_context(ctx)` and `check_command(ctx, argv)` read the engine's `allow_commands` / `deny_commands` params |
| `env.py` | `check_env(updates, deny=())`: admits ordinary `KEY=VALUE` pairs; refuses `ABX_*` (any case) and any name matching the caller deny list. Does not write `os.environ` |
| `urls.py` | `check_url(url, allow_private=False)`: refuses loopback, link-local and private addresses unless `allow_private`; a public `https` URL is admitted. Literal address only (no DNS) |
| `process.py` | `check_process(argv)`: refuses an argv whose executable resolves under `/proc`, `/sys` or `/dev` (path as given and real path) |

Behaviour:

* Deny pass first and absolute; matched against the argv with short flags expanded (`-lR` -> `-l -R`).
* A one-token pattern constrains the executable (v1 semantics: full path or basename, fnmatch). A multi-token pattern constrains the whole argv: literal, glob (never crosses `/`, `..` or a leading `-` unless the token does), `...` (max 3, memoised matching, no regex), `{int}`, `{word}`, `{path}` (canonicalised through the path guard; never matches without one; the canonical value replaces the argument).
* Error codes are the existing ones, none renumbered or added to the v1 set: `command_not_allowed`, `path_not_allowed`, `path_denied`, `read_only`, `invalid_path`, `shell_not_allowed`, `command_invalid` (400) and `command_denied` (design 03 name). The engine bridge uses `legacy_codes=True`, so a deny match is `command_not_allowed` exactly as `routes._check_command` reports it (a test compares both on the same inputs).
* `allow=()` means "no allow-list" for the bridge (v1); `command_guard()` uses `require_allow=True` (`scope_required`).

## Alternatives considered
- Rewire `routes.py` / `routes_files.py` to the new guards now. Rejected: those files are outside this change; the bridge functions are drop-in (`check_command(ctx, argv)` replaces `_check_command(ctx, argv)`), switching is a follow-up.
- Convert `guard.py` to the package and delete it. Rejected: plan 10 section 1.2 wants a re-export so old imports keep working; it is kept as is.
- Regex-compile user globs. Rejected (IS-P9): fnmatch for deny/exe tokens, segment matching for argv.

## Not done (follow-ups)
`check_env`, `check_url` and `check_process` are called from the live routes. `check_env`: `handle_env_set` (`routes_system.py`, `POST /env`), `enforce_exec_policy` (`routes.py`; the `env` object on `POST /shell` via `handle_shell`, `POST /shell/stream` via `_handle_shell_stream`, and `POST /process/start` via `_handle_process_start`), and `_handle_create_session` (`routes_pty.py`, `POST /pty/sessions`). `check_url`: `handle_browser_navigate` (`routes_browser.py`, `POST /browser/navigate`). `check_process`: `enforce_exec_policy` (argv for those shell and process routes), `handle_code_run` (`routes_devtools.py`, `POST /code/run`), and `_handle_create_session` (the PTY shell argv). Still deferred: `env_pass`/`env_set`/`ENV_NEVER` startup snapshot, `harden.py` (`PR_SET_DUMPABLE`, `RLIMIT_CORE`), `launcher.py` (rlimits, no `preexec_fn`), `exec_dirs` executable resolution, race-free `open_beneath`/`unlink_beneath`, escape-capable command lint, `{path}` with grouped short flags, rewiring `core/policy.py` to call the guards (`routes.py` and `routes_files.py` already call `path_guard_from_context` and `check_command`), `PathScope`/`CommandScope` value objects and the `Policy.allow/deny` builders (WP-2). No `core/` or `policy.py` re-export was added: `guards` imports `policy`, so re-exporting there would be circular.

## Call-site audit
No gap. Every live HTTP handler that accepts a caller environment map, a caller URL, or a caller executable argv already calls `check_env`, `check_url`, or `check_process` (or, for the agents group, a stricter local check). `POST /ops/{id}` (`core/http.py` `serve_ops`) invokes those same handlers, so it does not bypass them. No route test was added.

Already guarded:

- `handle_env_set` (`POST /env`) — `check_env`
- `handle_shell` (`POST /shell`), `_handle_shell_stream` (`POST /shell/stream`), `_handle_process_start` (`POST /process/start`) — `enforce_exec_policy` calls `check_env` and `check_process`
- `_handle_create_session` (`POST /pty/sessions`) — `check_env` on `env`, `check_process` on the shell argv (shell is also limited to the fixed allow-list)
- `handle_browser_navigate` (`POST /browser/navigate`) — `check_url`
- `handle_code_run` (`POST /code/run`) — `check_process` on the language argv (`python3`/`node`/`bash`). The body has no env map and no caller executable.

Checked and not a gap (caller does not supply the executable, or a stricter agents check already runs):

- `handle_git_status`, `handle_git_diff` — argv is fixed `git ...`; the query supplies a work tree and an optional path, not an executable
- `handle_packages` — argv is fixed `pip` or `npm` from the `manager` enum; `_ports_via_ss` runs fixed `ss -tlnp` only as a fallback
- `handle_environments_create`, `handle_templates_create`, `handle_templates_update` — env maps go through `check_env_map`, which refuses `ABX_*` and a wider deny list (`LD_*`, `PATH`, `HOME`, proxies, provider keys)
- `handle_webhooks_create`, `handle_webhooks_update` — URLs go through `check_endpoint_url` → `url_check` (https, no userinfo/query/fragment, private and loopback hosts refused)
- Agent/response tool `server_url` and vault `auth.mcp_server_url` — `url_check`. MCP tool URLs pass `allow_private=True` on purpose (local MCP). `check_url` would either duplicate that allowance or reject private MCP hosts
- `AgentRuntime._supervise` and `prepare_workspace` — argv[0] is the adapter binary or `git`. The HTTP field allow-list rejects `command`, `extra_args`, and stdio MCP `command`. Environment create/update has no git URL field, so the clone path is not an HTTP input

Other registered handlers were checked and do not accept an env map, a URL, or an executable argv: file routes, the other browser routes, process list/detail/signal/stdin/output, the other PTY routes, capabilities, system info/metrics, and `POST /commands/{name}` (a registered Python callable, not a subprocess argv).

## Dependencies
Design 03 sections 6, 7, 15.3; plan 10 WP-3. Locked files owned by another worker were not touched.

## Test Strategy
`server-sdk/tests/test_server/test_guards_v2.py` (39 tests): allowed path under `/tmp`; denied path (glob, directory subtree, traversal, symlink escape, read-only, invalid input, system dirs, bad roots); denied command (executable, full path, short-flag alias, deny beats allow); argv patterns, `{path}` canonicalisation, shell grant, normalisation, bounded matching; engine bridge through `ServerPolicy.bind()` and parity with `routes._check_command`. `tests/test_server/test_guards_env_url.py` covers `check_env`, `check_url` and `check_process`. `tests/test_server/test_guards_live_routes.py` hits the HTTP routes (denied env key, private URL, argv under `/proc`; ordinary env, public https URL, normal command).
