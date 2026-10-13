# 04 - Built-in modules and operation catalog

> Status: archive. Not the current specification.

> **Status: target design, not implemented.** The shipped server uses endpoint ids and one policy engine; see [README](README.md) section 1 for what exists and section 2 for what does not.

> Part of [Server SDK v2](README.md). Generated tables: the table bodies below are produced by
> `python -m agent_sandbox.server describe --markdown` and verified by the drift test (R5); edit the `@op`
> declarations, not the tables. Legacy bindings are exactly today's routes (41 HTTP endpoints plus the PTY
> WebSocket make the "42 endpoints" of the current server).
> **v2.1**: package `ops/` renamed `builtin/` (IF-03); default registry is **105 ops** (50 non-agent + 35 generic agent + 5 x 4 adapter ops); effects, explicit-only
> flags and the agent catalog are the target catalog. The in-flight code is mapped in the parity ledger of [07](07-client-mirror.md) section 6.

## 1. Modules and groups

| Namespace | Module file | Legacy group (`group:`) | Default | Third-party imports |
|-----------|-------------|--------------------------|---------|---------------------|
| `core` | `builtin/core.py` | `core` | enabled | stdlib |
| `files` | `builtin/files.py` | `file_ops` | enabled | stdlib |
| `commands`, `process` | `builtin/commands.py`, `builtin/process.py` | `process` | enabled | stdlib |
| `custom`, `ext` | `builtin/custom.py`, `builtin/ext.py` | `commands` | enabled | stdlib |
| `terminal` | `builtin/terminal.py` | `terminal` | enabled (PTY listener starts lazily) | `websockets` (lazy import) |
| `system` | `builtin/system.py` | `system` | enabled | stdlib |
| `devtools` | `builtin/devtools.py` | `dev_tools` | **disabled** | stdlib (`git` binary) |
| `browser` | `builtin/browser.py` | `browser` | **disabled** | `playwright` (optional extra, lazy-installed, see 06) |
| `agents` | `agents/` (adapters, wire, state) | `agents` (new) | **disabled** | stdlib; agent CLIs lazy-installed; imported lazily (fixes the in-flight circular import `routes_agents`, IF-09) |

"Enabled" is the *legacy* default of a server with no policy. A server with a policy has exactly what its
allow rules mount; groups are only used when a rule or `ABX_SERVER_ENABLED_GROUPS` says so.

**Legacy path jail.** The legacy server already confines file paths to `ABX_SERVER_BASE_DIR` (comma list; default
the process home/app dirs) through `_resolve_safe_path`. `presets.legacy_compat()` therefore carries
`PathScope(roots=BASE_DIRS)` on every `files.*` op and on `cwd` of command ops; this is not an optional detail
(see review round 2, finding F2.1). Under `legacy_compat`, a violation keeps the **v1 status and body as recorded from HEAD by the v1 fixture generator** (IF-04: not every v1 message contains "traversal"; the
fixtures, not this prose, are normative) *and* gains `code: policy.path_not_allowed`. `legacy_compat` is loud and unsafe (03 section 4); `legacy_diff(server)` reports which of the **40 legacy op ids** (plus
`POST /commands/{name}` = 41 routes) the effective policy no longer mounts, so "I added a policy and my routes vanished" is visible (B-6).

## 2. Effects and limits legend

Effects: `R`=read, `W`=write, `D`=delete, `X`=exec, `N`=net, `A`=admin. Limit keys: `bytes`=max_bytes,
`ent`=max_entries, `to`=timeout, `out`=max_output_bytes, `cpu`, `mem`, `proc`, `rate`, `conc` (rate and
concurrency apply to every op).

## 3. `core`

| Op ID | Legacy binding | Eff | Params | Notes |
|-------|----------------|-----|--------|-------|
| `core.health` | `GET /health` | R | - | anonymous allowed (legacy `auth_required=False`); returns `{status, version}` only |
| `core.capabilities` | `GET /capabilities` | R | - | superset of the legacy body, see 02 section 7 |
| `core.describe` | `GET /ops` | R | `all`, `namespace`, `ids` | `all=1` is admin-only |
| `core.check` | `POST /capabilities/check` | R | `op`, `args` | dry-run policy decision; never executes. Offline twin: `SandboxServer.explain` / `agent-sandbox-server explain` |
| `core.openapi` | `GET /openapi.json` | R | - | generated document, filtered to the caller's mounted ops |
| `core.reload` | `POST /admin/reload` | A | - | **explicit-only**; only mounted when reload is enabled (03 section 10); never in a preset. `core.health` is always mounted unless explicitly denied (B-1) |

## 4. `files` (group `file_ops`) - path-scoped

| Op ID | Legacy binding(s) | Eff | Path params | Notes |
|-------|-------------------|-----|-------------|-------|
| `files.list` | `GET /files/list` | R | `path` | `ent` limit; entries outside scope omitted; returns `truncated` |
| `files.stat` | `GET /files/stat` | R | `path` | policy first, existence second |
| `files.mkdir` | `POST /files/mkdir` | W | `path` | `parents` flag |
| `files.delete` | `DELETE /files` | D | `path` | `recursive`; refuses to delete a scope root |
| `files.move` | `POST /files/move` | R+D / W | `src` (read+delete), `dst` (write) | both must be admitted |
| `files.search` | `POST /files/search` | R | `path` (root) | `ent`, `to`; results re-checked |
| `files.upload` | `POST /upload` | W | `path` | JSON base64 (`content_base64`); `bytes` enforced on decoded size |
| `files.upload_stream` | `POST /files/upload-stream` | W | `path` | chunked-decoding twin of `files.upload`; same shape |
| `files.download` | `GET /download` | R | `path` | JSON base64 response; `bytes` |
| `files.download_stream` | `GET /files/download-stream` | R | `path` | chunked twin; also serves `Accept: application/octet-stream` raw bytes (new) |
| `files.archive` | `POST /files/archive` | R+W | `paths[]` (read), `dest` (write, optional) | tar.gz/zip; `bytes` caps archive size |
| `files.watch` | `GET /files/watch` (SSE) | R | `path` | new (client-server alignment); inotify via polling fallback; events re-checked against scope |

* The "twin" ops exist because their legacy request/response shapes differ slightly and old clients use both. `deprecated` metadata points new code to `files.download`/`files.upload`.
* **(v2.1, B-7, one rule)** A policy mounts exactly what it names, **and** `files.download` / `files.download_stream` are a *family*: the `allow()` of one of
  the two without the other produces the lint `warn config.download_family_split` (the legacy `/files/download-stream` route would 404 under an
  `allow(download, stat, list)` that the author believed served downloads). The `download_only`, `files_readonly` and `readonly` presets name all
  four read ops (`list stat download download_stream`). Every statement mounting a path op needs a `PathScope` (03 section 3, scope-required).
* **Handlers use `*at()` calls on a parent fd** (`open_parent_beneath`, `unlink_beneath`) for delete/move/upload (IS-F2); non-regular files are refused (IS-F4).

## 5. `commands` and `process` (group `process`) - command-scoped

| Op ID | Legacy binding | Eff | Command/path params | Limits | Notes |
|-------|----------------|-----|---------------------|--------|-------|
| `commands.run` | `POST /shell` | X | `command` **xor** `argv`, `cwd`, `env` | to, out, cpu, mem, proc | one-shot; `shell` flag; `timed_out`, `truncated` fields; needs a `CommandScope` (a bare allow is `policy.scope_required`); omitted `cwd` = scope root |
| `commands.stream` | `POST /shell/stream` | X | same | same | SSE: `stdout`/`stderr`/`exit` events |
| `process.start` | `POST /process/start` | X | `command`, `cwd`, `env` | proc, out | background process, returns `pid` |
| `process.list` | `GET /process/list` | R | - | | only processes started through the server (and visible to the principal) |
| `process.get` | `GET /process/{pid}` | R | - | | status, exit code |
| `process.signal` | `POST /process/{pid}/signal` | X | - | | **explicit-only**; signal allowlist (03 section 7.2) |
| `process.stdin` | `POST /process/{pid}/stdin` | X | - | bytes | new |
| `process.output` | `GET /process/{pid}/output` | R | - | out | new; `offset`/`wait` long-poll |

`commands.run` is the *shell execution* op. It is **not** the home of user-defined commands (`custom.*`): the
in-flight design's `server.commands.*` naming for custom commands is retired (reconciliation in 10).

## 6. `terminal` (group `terminal`)

| Op ID | Legacy binding | Eff | Notes |
|-------|----------------|-----|-------|
| `terminal.create` | `POST /pty/sessions` | X | **explicit-only**; command-scoped like `commands.run`; never in a preset except `full_access(unsafe=True)` |
| `terminal.list` | `GET /pty/sessions` | R | |
| `terminal.get` | `GET /pty/sessions/{id}` | R | new |
| `terminal.resize` | `POST /pty/sessions/{id}/resize` | X | new |
| `terminal.delete` | `DELETE /pty/sessions/{id}` | D | |
| `terminal.connect` | `WS :9001/pty/{id}` | X | `stream="ws"`; `pty.*` accepted as namespace alias for selectors |

## 7. `system` (group `system`)

| Op ID | Legacy binding | Eff | Notes |
|-------|----------------|-----|-------|
| `system.info` | `GET /system/info` | R | OS, CPU, memory, uptime |
| `system.metrics` | `GET /system/metrics` | R | |
| `system.env.get` | `GET /env` | R | secrets: values of variables matching `*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*` are masked unless the principal has role `admin` |
| `system.env.set` | `POST /env` | A+W | **explicit-only, never in a group or preset (IS-C2)**: writes only the server's env overlay (never `os.environ`), refuses `ENV_NEVER` names and `ABX_*`; `group:system` no longer contains it; `legacy_compat` mounts it only with `ABX_SERVER_LEGACY_ENV_SET=1` |
| `system.ports` | `GET /ports` | R | |
| `system.packages` | `GET /packages` | R | |

## 8. `devtools` (group `dev_tools`, default off)

| Op ID | Legacy binding | Eff | Notes |
|-------|----------------|-----|-------|
| `devtools.code.run` | `POST /code/run` | X+W | `language` allowlist via `languages=` scope (`policy.language_not_allowed`) |
| `devtools.git.status` | `GET /git/status` | R+X | `path` (repo root, path-scoped) |
| `devtools.git.diff` | `GET /git/diff` | R+X | |

## 9. `browser` (group `browser`, default off)

| Op ID | Legacy binding | Eff | Notes |
|-------|----------------|-----|-------|
| `browser.navigate` | `POST /browser/navigate` | N | `url` is a declared `urls=` param: `UrlScope(hosts=[...], schemes=("https",), ports=(), paths=("/**",), block_private=True)` (03 section 15.4); the canonical URL is used |
| `browser.screenshot` | `POST /browser/screenshot` | R | |
| `browser.content` | `GET /browser/content` | R | |
| `browser.click`, `browser.type` | `POST /browser/click`, `/type` | X | |
| `browser.evaluate` | `POST /browser/evaluate` | X | arbitrary JS in the page; not in any preset |
| `browser.pdf` | `POST /browser/pdf` | R | |
| `browser.console` | `GET /browser/console` | R | |

`UrlScope` (v2.1, replaces the glob-over-string design that IS-U1 broke): strict parser, compares the parsed hostname, `schemes`, `ports`, `paths`, `block_private` (RFC 1918, loopback, link-local, CGNAT incl. `100.100.100.200`, ULA, IPv4-mapped IPv6). Chromium does its own
DNS so rebinding is only mitigated by platform egress policy - documented as a limit. Literal hosts first; wildcard host suffixes (`*.example.com`) are deferred.

## 10. `custom` and `ext` (group `commands`)

| Op ID | Legacy binding | Eff | Notes |
|-------|----------------|-----|-------|
| `custom.list` | `GET /commands` | R | |
| `custom.<name>` | `POST /commands/{name}` | declared | registered per `registry.command(name, effects=...)`; the compatibility loader **declares** `{"exec"}` for legacy commands (an explicit declaration); a native `@op` without `effects=` is `admin` + explicit-only (B-3); names are mangled (`Hello-World.v2` -> `custom.hello_world_v2`, 02 section 2); reserved names `list`, `describe` |
| `ext.<handler>` | the registered method/path | `{"admin"}` default (explicit-only) | legacy `table.route(...)` extensions; set `effects=` to relax. They are **not** in any preset or `full_access`; `legacy_compat` mounts them by exact id. A custom op that no rule mounts is the lint `warn config.unmounted_custom_op` (B-5) |

`POST /commands/{name}` is a **wire alias** (02 section 5): it resolves to `custom.<name>` before authorization.

## 11. `agents`

Specified in [05-agents-api.md](05-agents-api.md). The default registry holds **105 ops** (spike `ebxp.catalog`, `tests_catalog.py`): 50 non-agent ops + **35 generic `agents.*` ops** (3 non-wire + 32 that mirror the official SDK) +
**5 adapters x 4 per-adapter ops** (`agents.<a>.run`, `.install`, `.sessions.create`, `.sessions.send_event`; adapters `codex`, `claude_code`, `qwen_code`, `cursor`, `qoder`; the last three are flagged *experimental*).

| Group of ops | IDs |
|---|---|
| runtimes (non-wire) | `agents.runtimes.list` (what the in-flight code called `agents.list`; N-1), `agents.runtimes.doctor`, `agents.models.list` |
| definitions | `agents.definitions.create get update list delete` |
| environments | `agents.environments.create get list`; reserved: `agents.environments.files.create list` (T-4) |
| sessions | `agents.sessions.create get update list delete send_event stream_events list_items` (N-2: verbs only; `send_event` is the official `events.create`) |
| turns | `agents.sessions.turns.list get list_items` |
| artifacts (tier 1, T-1) | `agents.sessions.artifacts.list get content delete` |
| traces, subagents | `agents.sessions.traces.list` (empty list), `agents.sessions.subagents.list` (empty list) and refused `agents.sessions.subagents.get list_items turns.list turns.get turns.list_items` (404 `not_found_error`, T-2) |
| per adapter x5 | `run`, `install` (explicit-only, admin+net), `sessions.create` (explicit-only, exec+net, `AgentScope`), `sessions.send_event` (exec+net, `AgentScope`) |

Cancel is not an op: it is the input event type `agent.session.input.cancel` of `send_event`. Generic `agents.sessions.create`/`send_event` additionally require the selected adapter's op (two-level gate, 05 section 4). `agents.<a>.**` is accepted
as selector sugar for "everything of adapter a that is not explicit-only" (IF-29 mitigation). The registry-size row of the in-flight 152-op plan is **superseded**: wire-shaped ops replaced the 12 + 5 x 18 family (05 section 3 records why per-adapter ops are kept and what generation does about them).

## 12. Group golden lists (no privilege creep)

`group:<name>` expands to exactly:

| Group | Ops |
|-------|-----|
| `core` | `core.health core.capabilities core.describe core.check core.openapi` |
| `file_ops` | `files.*` (12 ops above; **no explicit-only op**) |
| `process` | `commands.run commands.stream process.start process.list process.get process.stdin process.output` (`process.signal` is explicit-only and not in the group) |
| `commands` | `custom.*`, `ext.*` (all registered at start) |
| `terminal` | `terminal.list get resize delete connect` (`terminal.create` is explicit-only) |
| `system` | `system.info system.metrics system.env.get system.ports system.packages` (**`system.env.set` removed**, IS-C2) |
| `dev_tools` | `devtools.code.run devtools.git.status devtools.git.diff` |
| `browser` | `browser.*` (8 ops) |
| `agents` | `agents.**` minus explicit-only ops (`install`, `sessions.create` of adapters); generic `agents.sessions.create/send_event` are members but need an `AgentScope` |

A new built-in op joins a group only through an edit to the golden snapshot file
(`tests/golden/groups.json`) in the same change; the reviewer checklist asks whether enabling the group on an existing
server would newly expose the op (for example `process.stdin` and `files.watch` are new and join `process` and `file_ops`
because their effects are covered by the existing group's trust level). **(v2.1)** Membership never carries an explicit-only op; `system.env.set` left `group:system` (the legacy ABX_SERVER_ENABLED_GROUPS=system no longer mounts it; the compat preset documents the opt-in).

## 13. Behavioural contracts shared by all built-ins

1. Handlers never take raw paths; they use `ctx.paths` and `ctx.open`.
2. No handler spawns a shell unless the op says so and the policy admitted `shell=True`.
3. Handlers that list or search re-check entries; handlers that stream honour `ctx.limits` and `ctx.deadline`.
4. Responses keep every legacy key; new keys are additive. Legacy result shapes are pinned by the existing 308 tests
   plus contract tests.
5. Each op has: a unit test, a policy-bypass test (if it touches paths/commands), and a client/server contract test
   generated from the catalog.
6. "Complete" is defined as: every envd-facing client module method has a server-plane op *or* a justified
   asymmetry entry in [07](07-client-mirror.md) section 6; nothing in the legacy server lacks an op ID.
