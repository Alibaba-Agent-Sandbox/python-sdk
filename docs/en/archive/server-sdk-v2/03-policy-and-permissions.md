# 03 - Policy and permissions

> Status: archive. Not the current specification.

> **Status: target design, not implemented.** The shipped server uses endpoint ids and one policy engine; see [README](README.md) section 1 for what exists and section 2 for what does not.

> Part of [Server SDK v2](README.md). Rules R2-R4. Supersedes the scope/endpoint-rule model of
> `fine-grained-capabilities.md` (identity is the dotted op ID; scopes become derived sugar, section 13).
> **v2.1**: hardened after the independent security review (41 findings, all 41 PoCs now HELD). The normative v2.1 rules are
> consolidated in **section 15**; the earlier sections were edited to agree with them. Changes are marked **(v2.1)**.

## 1. Summary, with the motivating example

"Only download is enabled, and only under `/tmp`":

```python
from agent_sandbox.server import start, Policy, ops, PathScope

policy = Policy().allow(
    ops.files.download, ops.files.stat, ops.files.list,
    paths=PathScope("/tmp", deny=["**/.env"], max_bytes="10MB"),
)
start(policy=policy)       # (v2.1) core.health is mounted unless explicitly denied; start() refuses lint errors
```

or without writing code, as a preset (`presets.download_only(root="/tmp")` expands to the policy above **plus** `core.health`, which a
bare `allow` would otherwise leave unmounted, B-1):

```python
start(preset="download-only", root="/tmp")
```

or as a file baked into the image (`/etc/agent-sandbox/server.json`, authored as YAML in `template.yaml`):

```yaml
server:
  preset: download-only
  root: /tmp                  # one keyword for every preset; aliases `paths:` and `workspace:` are accepted (B-8)
```

Effect (all verified against the spike): `GET /files/download-stream?path=/tmp/a.txt` works;
`/tmp/../etc/passwd` and a symlink in `/tmp` pointing outside get `403 policy.path_not_allowed`;
`/tmp/.env` gets `403 policy.path_denied` (and so does `deny(paths="/tmp/secret")` for every descendant of `/tmp/secret`, B-4); `files.upload`, `files.delete`, `commands.run`... answer
`404 op.not_enabled` and are absent from `/capabilities`.

## 2. Model

A **policy** is an ordered list of **rules** plus optional **hooks** and **audit sinks**.

```python
Policy()                                     # empty: nothing is mounted (default-deny); allow()/deny() with no selector is a ValueError
  .allow(*selectors, principals=(), paths=None, commands=None, limits=None, authorize=None, name="")
  .deny (*selectors, principals=(), paths=None, commands=None, reason="", name="")
  .without(*selectors)                       # sugar for deny(selectors) with a clear reason
  .authorize(fn)                             # global hook (decorator)
  .audit(sink)                               # audit sink (decorator)
policy_a + policy_b                          # union of rules/hooks (deny still overrides)
```

**Selectors** (strings or `ops.*` nodes):

| Selector | Matches | Specificity rank |
|----------|---------|------------------|
| `files.list` / `ops.files.list` | exactly that op | 4 |
| `files.*` / `files.**` | **(v2.1, IF-30)** `ns.*` = ops **one level** below the namespace (`files.list`); `ns.**` = any depth (`agents.**` includes `agents.codex.sessions.create`; `agents.*` does not) | 3 |
| `group:file_ops`, `effect:read` | legacy group list / all ops carrying the effect | 2 |
| `*` | every op (including future ones - discouraged, lint warns in non-`legacy` policies) | 1 |

**Explicit-only operations (v2.1, IS-C2, IS-P4, IS-G1; amends D6).** On the **allow side** an explicit-only op is mounted only by a rule that names its exact
ID; wildcard, `ns.*`, `ns.**`, `group:`, `effect:` and `*` never match it. The explicit-only set is:
all ops whose effects include `admin`, `core.reload`, **`system.env.set`**, `terminal.create`, `process.signal`, `agents.<a>.install` and
`agents.<a>.sessions.create`. Ops registered without `effects=` default to `admin` and are therefore explicit-only (lint
`warn core.effects_undeclared`). On the **deny side the opposite holds**: every selector reaches them (`deny("effect:exec")` denies `terminal.create`;
`deny("system.*")` denies `system.env.set`), so a deny is never weaker than the allow it must beat. A *selector that is a
group* may not contain `system.env.set` (the legacy `group:system` loses it; the compat preset adds it back only on request, section 4).
**Presets may name explicit-only ops** (an operator must be able to say "this preset mounts `process.signal`") **except** `system.env.set`,
`core.reload` and every `install`, which only a hand-written `allow(<exact id>)` mounts. `agents.<a>.sessions.create` is explicit-only because creating a
session starts a process (agent sessions are exec-effect ops, section 15.6).

**Effects** are coarse tags declared by each op ([04](04-builtin-modules.md) lists them):

| Effect | Meaning |
|--------|---------|
| `read` | reads sandbox state (files, system info, listings) |
| `write` | creates/modifies files or state |
| `delete` | removes files/processes/sessions |
| `exec` | runs a process or code inside the sandbox |
| `net` | makes outbound network requests (browser navigation, installs, LLM calls) |
| `admin` | changes server/sandbox configuration or exposes policy (env set, definitions, reload, describe-all) |

`effect:read` is a *convenient* selector (a read-only server = `allow("effect:read")`), but `exec` is not
`read`-safe: effect-selected rules never include ops whose effects also contain `exec`, `write`, `delete` unless the
selector says so (`allow("effect:read")` mounts only ops whose effects are a subset of `{read}`).

**Mounted** = at least one `allow` rule matches the op *for this principal*. Not mounted -> `404 op.not_enabled`.
`core.health` is the one exception: it is mounted for everyone unless a rule explicitly denies it (B-1; `readiness` must not depend on
the policy author remembering it).

**Rule hygiene (v2.1, IS-P1, IS-P1c, B-2).**
* A bare `allow("commands.run")` (no `CommandScope`) and a bare `allow("files.download")` (no `PathScope`) are **not** "unrestricted": they fail with
  `403 policy.scope_required` at request time and with `error config.scope_required` in `check-config`; `start()` refuses to run with lint errors
  (`config.lint_errors`) unless `allow_lint_errors=True`.
* `Policy.allow/deny` accept selectors that match nothing only with `strict=False`; by default `SandboxServer` raises
  `PolicyError config.unknown_selector` (with did-you-mean) at construction, so the card's promise "typos error" is true.
* `principals=["*"]` means any **authenticated** principal; the anonymous principal never matches it (IS-A7).
* `without(*selectors)` is sugar for `deny`; hyphen and underscore spellings of presets are both accepted (`download-only` == `download_only`, B-13).

## 3. Evaluation algorithm (normative)

Inputs: `op`, `args`, `principal`. Steps (spike: `Policy._decide`):

1. **Mount check.** Let `A` = allow rules whose selectors match `op` and whose `principals` match. If `A` is empty:
   `404 op.not_enabled` (identical body for "unknown to policy" and "unknown to you").
2. **Deny pass (deny-overrides).** For each `deny` rule matching `op` and principal (**every selector kind reaches explicit-only ops**):
   * no scope -> `403 policy.denied_by_rule` (with the rule's `reason`);
   * with `paths=` globs -> the **canonical** value of every declared path parameter is matched, **and every ancestor of it**, so
     `deny(paths="/secret")` covers `/secret/a/b` (IS-P3, B-4); a **relative** argument is canonicalised against **every allow anchor** of the op
     (the roots of each candidate allow statement) and denied if any anchor yields a denied path (IS-P2); a bare directory pattern means "this
     directory and everything below it"; -> `403 policy.path_denied`;
   * with `commands=` deny patterns -> the **same normalised argv** that the allow pass uses (`command` xor `argv`, otherwise `400 args.invalid`; one
     normalisation, IS-P2b) -> `403 policy.command_denied`.
   A deny is absolute: no allow rule, hook or preset can override it. A **non-removable system deny list** (`/proc`, `/sys`, `/dev` and every directory
     registered with `protect_dir`, section 15.3) is applied to every path of every statement even when no rule mentions it (IS-F1, IS-L1).
3. **Allow pass.** Sort `A` by `(selector rank desc, has principals desc, declaration order asc)`. For each
   statement, try to **admit** the call: **require** the scope kinds the op declares (path, command, url, agent; otherwise `policy.scope_required`),
   resolve every declared path param through the statement's `PathScope`, check/resolve the command through its `CommandScope`, the URL through its `UrlScope`,
   the agent options through its `AgentScope`, apply limits. The **first admitting statement wins** and
   supplies `scope`, canonical values and `limits`. If none admits: `403` with the *first* statement's denial code
   (`policy.path_not_allowed`, `policy.command_not_allowed`, ...).
   Consequence: allow statements are a union of *alternative* grants, each fully constrained
   ("`/tmp` read-only" OR "`/workspace` read-write").
4. **Hooks (veto only).** The winning statement's `authorize=` hook, then global hooks, run with the admitted
   context. A hook may return `None`/`True` (no objection), `False`, `Deny(reason, code=...)`, or
   `Narrow(limits=Limits(...))` (tighten limits further). Hooks cannot add permissions. Exceptions, timeouts
   (default 2 s) and unawaitable results **deny** (`403 policy.hook_error`) - fail-closed. **(v2.1, IS-P5, IS-P5b)** The hook receives a **frozen view**
   (`MappingProxyType` for `args`, `paths`, `claims`; tuples for argv), so it cannot mutate admitted values; any return value other than `None`/`True`,
   `False`, `Deny`, `Narrow` is `403 policy.hook_bad_return` (a truthy string is not an "allow").
5. **Operator layer** (section 10) is applied as additional deny rules and limit minima *before* step 3, so it
   behaves identically to author rules but cannot be removed by them.
6. **Audit** record is always emitted (allowed or denied).

Why "first admitting statement wins" and not "most permissive"? Predictability for humans and AI: the more
specific statement is listed (or sorts) first; limits therefore come from one statement and never from a hidden
merge. `check-config` flags **shadowed** statements (a later statement for the same op that can never be reached
because an earlier unconstrained one always admits).

### 3.1 Per-principal and per-op limits (the "different limits for different callers" case)

```python
policy = (Policy()
  .allow(ops.files.download, principals=["role:guest"],
         paths="/srv/public", limits=Limits(max_bytes="1MB", rate="10/min"))
  .allow(ops.files.download, principals=["role:staff"],
         paths=["/srv/public", "/srv/internal"], limits=Limits(max_bytes="1GB", concurrency=4))
  .allow(ops.commands.run,  principals=["id:grader"],
         commands=CommandScope(allow=["python3 /workspace/grade.py"], cwd="/workspace", timeout=60)))
# per-tenant roots (v2.1, B-15): "{principal.id}" is substituted after validating the id as ONE safe path component
  .allow(ops.files.list, ops.files.download, principals=["*"], paths=PathScope("/data/{principal.id}"))
```

Principals come from authentication (section 5). Rule `principals` entries: `id:<id>`, `role:<role>`, `*`
(any **authenticated**; never the anonymous principal, IS-A7). An empty list means *every* principal including anonymous. `check-config` warns
(B-19) for a `principals` entry that no configured token or `authenticate` result can produce (`id:` / `role:` naming nobody).

## 4. Presets

Presets are functions returning a `Policy`; they compose with `+` and refine with `.without(...)`. **(v2.1, B-8)** Every preset that needs a directory takes
the **one keyword `root=`** (aliases `paths=` and `workspace=` are accepted for the in-flight spellings); there is **no default root**: omitting it is a `ValueError`
because "default `/`" is how `/proc/self/environ` got readable (IS-F1). In config files the names are hyphenated (`download-only`) and in Python
underscored (`download_only`); both spellings are accepted in both places (B-13). Every preset includes `core.health`.

| Preset | Expands to |
|--------|-----------|
| `presets.minimal()` | `core.health`, `core.capabilities` only |
| `presets.files_readonly(root, deny=("**/.env", "**/*.pem"))` | `files.list/stat/download/download_stream` only (B-7: `download_stream` is part of every download grant), read-only scope |
| `presets.readonly(root)` | `files_readonly` plus `files.search/archive`, `system.info/metrics/ports/packages`, `process.list/get/output`; read-only scope; the system deny list applies |
| `presets.download_only(root, deny=("**/.env",), max_bytes="100MB")` | `files.download/download_stream/stat/list` under `root` |
| `presets.commands_only(root, allow=(...), timeout=60)` | `commands.run/stream` with the given `CommandScope` (cwd = `root`) |
| `presets.workspace_jail(root, readonly=False, commands=None)` | all `files.*` jailed to `root` (secrets denied), `commands.run/stream` only if `commands=` is given, `system.info` |
| `presets.ci_runner(root, commands=(...), timeout=600, writable=False)` | **(v2.1, B-9)** a **read-only** workspace plus the command allowlist; `writable=True` is an explicit opt-in and then `check-config` applies the writable-script rule and escape-capable lint to the commands. `terminal.*` off |
| `presets.agent_host(root, agents=("codex",), permissions="read-only")` | **(v2.1, B-10)** the generic agent ops a first SDK call needs (`agents.definitions.create/get/list/update/delete`, `agents.environments.create/get/list`, `agents.sessions.*`, `agents.runtimes.list`, models), the adapter ops `agents.<a>.run`, `agents.<a>.sessions.create`, `agents.<a>.sessions.send_event` for each listed adapter (exact IDs; `install` is **not** included), and an `AgentScope(workdir=root, permissions="read-only")`. Experimental adapters carry a lint warning (B-16) |
| `presets.full_access(root, commands, unsafe)` | every non-explicit-only op of every group enabled by default in v1 with a **`root` jail** and a `CommandScope`; `PathScope.anywhere`/`CommandScope.unrestricted` only with `unsafe=True`. Never mounts `system.env.set`, `core.reload`, installs |
| `presets.legacy_compat()` | **loud and unsafe (v2.1, IS-C2)**: the 40 legacy op ids with the v1 `BASE_DIR` jail and v1 renderer for the legacy bindings; `system.env.set` only when `ABX_SERVER_LEGACY_ENV_SET=1`. `start()` logs `legacy_compat is active` at WARNING and `check-config` prints the diff from `legacy_diff(server)` (the legacy ids the effective policy drops, B-6). It is the implicit default **only** when `ABX_SERVER_TOKEN` is set or the bind is loopback |

Every preset is documented with its exact expansion in `describe --preset <name>`; a golden snapshot test pins the op lists (**no privilege creep**: adding a new op to
a namespace does not add it to a preset unless the snapshot is updated in the same change, reviewed by a security owner).

## 5. Authentication and principals

* **Credentials and precedence (v2.1, IF-17; amends D16).** Both `Authorization: Bearer <token>` and `X-Access-Token: <token>` are accepted on every route (the
  official `openai` client can only send `Authorization`). **`Authorization: Bearer` wins**; `X-Access-Token` is the legacy alias. When both are present and
  differ the request is `401 auth.conflicting_credentials` (equal values are accepted). Comparison is `hmac.compare_digest`. The same rule applies to
  the generated client: it sends `Authorization: Bearer` and, only when `legacy_header=True`, also `X-Access-Token` with the same value. Tokens in URLs
  (query string) are never accepted for HTTP; WebSocket and SSE use headers or a one-time ticket (IS-T1, deferred to the terminal WP).
* **Fail closed (v2.1, IS-A1 critical).** An `auth.tokens` entry whose `token_env` is **unset or empty** is `ConfigError config.auth_secret_missing` and the server **refuses
  to start** (it never falls back to open mode). A secret shorter than 16 characters is `config.auth_secret_weak`; an inline `token:` value in a file is
  `config.secret_inline`; the id `anonymous` is reserved (`config.reserved_id`). Tokens in config are only `token_env` names or `token_sha256` digests.
* **Single token (legacy)**: `ABX_SERVER_TOKEN` -> principal `{id: "token", roles: ["admin"]}`; when no `auth:` block exists the variable becomes an admin token, and if it is
  set but empty the server refuses to start.
* **Several principals** (`server.json`):
  ```yaml
  auth:
    tokens:
      - {id: grader,  roles: [grader], token_env: ABX_TOKEN_GRADER}   # secret from env, never in the file; must be set and >= 16 chars
      - {id: viewer,  roles: [viewer], token_sha256: "…"}              # or a hash
    anonymous: false                                                    # default: false when any token is configured
  ```
* **Open mode (no token configured; v2.1, B-18).** The principal is `{id: "anonymous", authenticated: false, roles: ["admin"]}` **only** when
  the listener is loopback **and** the policy mounts no exec/admin-effect op. Otherwise `start()` refuses: `config.open_non_loopback` (bind is not loopback) or
  `config.open_exec` (policy mounts `exec`/`admin` ops, which includes every agent session op and `commands.run`), unless `allow_open=True`
  (a lint error; `doctor` prints it in red). `serve --require-auth` makes the refusal unconditional.
* **Python hook for external auth** (JWT etc.): `SandboxServer(authenticate=fn)` with the documented signature
  `fn(headers: Mapping[str, str]) -> Principal | None` (B-12). Header names are case-insensitive: the mapping is a case-insensitive `Mapping`, lookups
  `headers["authorization"]` and `headers["Authorization"]` both work. Return `None` for 401, a `Principal(id, roles=(), claims={}, authenticated=True)` otherwise;
  exceptions are 401. `AuthConflict` is raised before the hook is called.
* `401` bodies are generic (`auth.required` / `auth.invalid`); they never reveal which tokens exist.
* **Failed-auth rate limit (v2.1, IF-18).** 10 failures per 60 s **keyed by the credential fingerprint** (sha256 of the presented token, first 8 bytes) and,
  separately, by source address only when `trusted_proxies` names the gateway (then `X-Forwarded-For` is honoured for that peer only) -> `429 auth.rate_limited` with `Retry-After`.
  Keying by source alone is useless behind the gateway where every request has the same address.
* **Listener hardening (v2.1, IS-A2, IS-A3, IS-A8, IF-19)** is in section 15.1.

## 6. Path scoping

```python
PathScope(*roots, deny=(), readonly=False, symlinks="within", max_bytes=None, create_dirs=True, allow_hardlinks=False)
PathScope.anywhere(unsafe=True)    # (v2.1) the only way to say "no jail"; a lint error
paths="/tmp"                       # shorthand: PathScope("/tmp")
paths=["/srv/a", "/srv/b"]         # multiple roots
PathScope("/data/{principal.id}")  # per-principal root (id validated as one safe component)
```

**(v2.1)** `PathScope("/")` and glob characters in a root raise `ValueError` (a root is a directory, not a pattern; `/` made `/proc` reachable, IS-F1).

| Field | Meaning |
|-------|---------|
| `roots` | allowed roots (canonicalised with `realpath` at policy construction; the first root anchors relative paths) |
| `deny` | glob patterns; `**` crosses `/`, `*` does not, a pattern without `/` matches the basename anywhere (`**/.env`, `*.pem`, `/etc/shadow`). A pattern also matches **any ancestor** of the candidate, so a directory pattern denies its subtree (v2.1, IS-P3). Matching uses the linear-time segment matcher of section 15.3 (no regex, IS-P9) |
| `readonly` | refuse `write`/`delete` effects through this statement |
| `symlinks` | `"within"` (default): a symlink is fine iff its **target stays inside a root**; `"deny"`: any symlink component below the root is refused; `"follow"` (unsafe, lint error unless `unsafe=True`) |
| `max_bytes` | per-file cap for reads/writes through this scope (also caps archive/search output) |

### 6.1 Resolution algorithm (spike `resolve_path`)

1. Reject NUL bytes, non-strings, > 4096 chars, > 256 segments -> `policy.path_invalid`.
2. Anchor relative paths at the first root; **normalise lexically only after anchoring** (so `a/../..` cannot
   escape by being collapsed away from the root).
3. If `symlinks="deny"`: `lstat` every component below the root; any symlink -> `policy.symlink_denied`.
4. `realpath` (non-strict so not-yet-existing files resolve). Must be inside a root, else `policy.path_not_allowed`.
5. Match `deny` globs against the **canonical** path and each of its ancestors, then the system deny list -> `policy.path_denied`.
6. `readonly` + write/delete effect -> `policy.read_only`.
7. Return the canonical path. **Handlers use only this value.**

### 6.2 Race-free use (the TOCTOU fix)

Canonicalise-then-open is racy: an attacker with write access to a directory under a root can swap a parent
for a symlink between steps 4 and the `open()`. The spike demonstrated that opening with `O_TRUNC` first and
verifying through `/proc/self/fd` afterwards **already truncated the victim file**. The normative mechanism is
`open_beneath(scope, canonical, flags)`:

* open the matching root as a directory fd; for each remaining component `openat(parent_fd, name, O_NOFOLLOW |
  (O_DIRECTORY for non-final))`; an `ELOOP`/`ENOTDIR` anywhere means the tree changed -> `policy.path_changed`;
* **never pass `O_TRUNC` to `open`**; after the final `fstat` proves a regular file, `ftruncate(fd, 0)`;
* refuse opening a root directory for writing; **refuse non-regular files for read and write** (FIFOs, devices, sockets: `policy.not_regular_file`, IS-F4; opened with `O_NONBLOCK` then checked with `fstat`);
* **mutations go through the parent fd (v2.1, IS-F2)**: `unlink_beneath`, `open_parent_beneath` and the `*at()` family (`unlinkat`, `renameat`, `mkdirat`) operate on a parent directory fd obtained with the same `O_NOFOLLOW` walk, so a parent swapped for a symlink after admission cannot redirect `files.delete`/`move`/`upload`;
* **hard links (v2.1, IS-F5)**: a regular file with `st_nlink > 1` is refused (`policy.hardlink_denied`) when the scope has deny entries or is writable, unless `allow_hardlinks=True`;
* directory listings and searches re-check every entry's canonical path (`ctx.recheck`) and **omit** entries
  that are outside the scope or denied (symlink pointing out of the jail is not listed).
* Known limits (documented, tested as "known"): hard links in a read-only, deny-free scope; bind mounts; `/proc` magic links (**denied
  by the non-removable system deny list**, not by an overridable default); filesystems without `O_NOFOLLOW` semantics. A scope is a **server-operation** guard, not a mount namespace.

### 6.3 Multi-path and list-valued parameters

`files.move(src, dst)`: `src` is checked as `read+delete`, `dst` as `write`, both under the same winning statement
(or `paths={"src": scopeA, "dst": scopeB}` in the statement for different scopes). `files.archive(sources[], dest)`:
every source is `read`, `dest` is `write`. `files.search(root, pattern)`: root is `read`; results are re-checked.
A call is admitted only if **every** path parameter is admitted.

## 7. Command scoping

```python
CommandScope(
    allow=("ls {path}", "pytest -q ...", "python3 /workspace/grade.py"),
    deny=("ls ... -R ...", "ls ... --recursive ..."),      # defense in depth ONLY (see 7.3)
    shell=False,                                            # shell=True is refused unless explicitly True
    exec_dirs=("/usr/bin", "/bin", "/usr/local/bin"),
    cwd=PathScope("/workspace"),                            # or "/workspace"
    env_pass=("PATH", "LANG", "HOME"),                      # copied from a STARTUP SNAPSHOT of the server environment (v2.1)
    env_set=(),                                             # names the CALLER may set (default: none)
    env_deny=("LD_*", "PYTHON*", "NODE_OPTIONS", ...),      # can never be set, even if listed in env_set (union with ENV_NEVER, v2.1)
    timeout=60, max_output_bytes="1MB", cpu_seconds=30, memory="512MB", processes=64,
)
```

### 7.1 Matching

* **Normalisation (v2.1, IS-P2b).** The request carries `command` (string) **xor** `argv` (list); both or neither is `400 args.invalid`. The string is split with `shlex.split` (POSIX) once and the resulting argv is what
  the deny pass, the allow pass and the launcher all see. Short flags are expanded (`-lR` -> `-l -R`) before matching.
* A command string is split with `shlex.split` (POSIX); an `argv` list is used as is. **Shell is off by default:**
  `shell=True` requests are `403 policy.shell_not_allowed` unless the statement says `shell=True`; with
  `shell=True` argv patterns cannot constrain the line, so `check-config` prints a warning and the statement
  should be used only for trusted principals.
* A pattern is a list of tokens (`shlex`-split if given as a string). Token kinds, matched one-to-one against argv:

  | Token | Matches |
  |-------|---------|
  | literal (`-q`, `pytest`) | exactly one argv element |
  | glob in **argument** position (`*.py`) | one argv element; **a glob never matches a token containing `/`, `..` or starting with `-` unless the pattern itself starts with that prefix** (IS-C1, glob-token traversal); use `{path}` for paths |
  | `...` | zero or more elements (anywhere, including leading: `... -R ...`) |
  | `{path}` | one element, not starting with `-`, no NUL; **canonicalised through the statement's `cwd` PathScope and the canonical value replaces it in the executed argv** |
  | `{int}` | `[0-9]{1,9}` |
  | `{word}` | `[A-Za-z0-9_][A-Za-z0-9_.@:+=,-]*` |

* The executable is resolved against `exec_dirs` (never the caller's `PATH`, never a name with a slash outside
  those dirs). The symlink path is executed, the directory is checked (busybox-style multi-call binaries keep
  working). Matching tries the given argv[0] and the resolved path.

### 7.2 Execution constraints

* `cwd` is checked through the cwd `PathScope` (`ctx.cwd`). **(v2.1, IS-P1b)** An omitted `cwd` defaults to the scope root (else `/`), never the server's own cwd, and `cwd` is covered by the `CommandScope` (no separate scope needed for the `cwd` parameter of command ops).
* **Environment** starts from `env_pass` taken from the server's environment; caller-supplied `env` entries must
  match `env_set` (default: none, so a caller cannot even override `PATH`; the first draft's single `env_allow` list let callers
  replace `PATH`, review round 3 finding S3.1) and none of `env_deny` (default deny list blocks `LD_*`, `DYLD_*`, `PYTHON*`, `NODE_OPTIONS`,
  `BASH_ENV`, `ENV`, `PERL5*`, `RUBY*`, `GIT_*`, `IFS`): `403 policy.env_var_denied`. **(v2.1, IS-C2b, IS-C2c)** `ENV_NEVER` (`PATH`, `HOME`, `USER`, `SHELL`, `LD_*`, `PYTHON*`, `NODE_*`, `*_PROXY`, `GIT_*`, `ABX_*`, `*_API_KEY`, `*_BASE_URL`, `*_TOKEN`, ...) can
  never be **set by a caller** (the list can only grow); `env_pass` is an operator-side copy from a snapshot taken at server start, so a later `os.environ` change cannot leak in.
* **Process secrets (v2.1, IS-C6).** `harden_process()` runs in `start_http`: `prctl(PR_SET_DUMPABLE, 0)` and `RLIMIT_CORE=0`, so a same-uid child cannot read `/proc/<ppid>/environ` or `/proc/<ppid>/mem` (PoC IS-C6 HELD). Children never inherit the server environment: they get only `env_pass` names from the start-up snapshot.
* **Resource caps** are applied by a small stdlib launcher (`python -m agent_sandbox.server.guards.launcher`, which calls
  `resource.setrlimit` then `os.execv`), **not** `preexec_fn` (not thread-safe in a threaded server). The child runs
  in its own session/process group (`start_new_session=True`); on timeout the group receives SIGTERM then SIGKILL.
  Output is captured through bounded readers (`max_output_bytes`), reporting `truncated: true`.
* `process.start` and `terminal.create` use the **same** `CommandScope` machinery (a PTY with a free shell is
  `commands.run(shell=True)` by another name and defaults to unmounted in every preset but `full_access`).
* **Signals** (`process.signal`): allowed signal list per statement (default `TERM, INT, KILL, HUP`), only for
  processes started through the server by the same principal (default).

### 7.3 What command scoping does and does not give you

* **Allowlist-first.** Deny patterns are defense-in-depth: an attacker can reach the same effect through aliases
  (`ls -R` vs `ls -lR` vs `ls --recursive`). The spike's first version denied `ls -R ...` and was bypassed by `-lR` and
  `--recursive`; short-flag expansion fixes the first, but **long-flag aliases need enumerating** -> never rely on a
  deny list for security; pin arguments in the allow pattern instead.
* **Escape-capable executables** (`sh bash python3 env find xargs awk perl ruby node git vim less man tar sed busybox
  docker sudo su script nice nohup timeout strace time ...) plus **project-file executables** (`make`, `pytest`, `npm`, `pip`, `cargo`, `python3 -m pytest` execute repository files: `conftest.py`, `Makefile`, `package.json` scripts), **writers** (`cp mv tee dd install ln`) and **network** tools (`curl wget nc ssh git clone`) (v2.1, IS-C5): `check-config` errors when an allow pattern for one of them
  contains `...` or a glob in argument position ("`python3 ...` is arbitrary code execution"). Pin the whole argv
  (`python3 /workspace/grade.py`) or wrap the behaviour in a **named custom op** - the recommended safest option:
  `@op("custom.grade", effects="exec")` with fixed argv inside the handler and only a validated parameter exposed.
* **Writable-script rule.** An allowed command that executes a file (`python3 /workspace/grade.py`) is only as safe as that file: if the same policy also lets
  callers write under that path (`files.upload` to `/workspace`) the pair is arbitrary code execution. `check-config` warns for every allow pattern with an
  absolute-path token under a root where any allow rule can write (found in review round 3, S3.2; implemented in the spike's `Policy.lint`).
* **Read-only claims are checked (v2.1, IS-C7).** `CommandScope.lint(write_roots)` errors when a "read-only" cwd contains allowed command classes that can write (`WRITERS`, `PROJECT_FILE`, `ESCAPE_CAPABLE`); the `ci_runner` preset therefore defaults to a read-only workspace and lints `pytest`/`git` as `PROJECT_FILE`.
* A command scope never constrains what an allowed program does with its own privileges. See section 12.

## 8. Hooks: `authorize(ctx) -> Decision`

```python
from agent_sandbox.server import Deny, Narrow

@policy.authorize
def no_exe_uploads(ctx):
    if ctx.op == "files.upload" and ctx.paths["path"].endswith((".exe", ".dll")):
        return Deny("executables may not be uploaded", code="policy.extension_not_allowed")
    if ctx.principal.id == "guest":
        return Narrow(limits=Limits(max_bytes="1MB"))
```

* Per-rule form: `allow(ops.files.upload, paths="/srv", authorize=fn)`.
* `ctx` is the handler's `ctx` *as admitted* (`ctx.op`, `ctx.paths` canonical, `ctx.argv`, `ctx.principal`, `ctx.args` raw args, `ctx.limits`) - hooks
  see canonical paths, not raw strings.
* Sync callables; a coroutine function is accepted and driven with `asyncio.run` on the request thread. Budget 2 s
  (`hooks.timeout`); exceeding it denies.
* Veto-only. A hook that raises, times out or returns an unknown type denies with `policy.hook_error` (the exception
  class name only is returned; details go to the audit log).
* **(v2.1)** Hook views are read-only (`MappingProxyType`), return values are validated (section 3 step 4), and a hook may not be registered on an op that does not exist.
* Hooks are **not** the right place for slow external calls on hot paths (document; use `authenticate=` caching).

## 9. Limits

`Limits(max_bytes, max_entries, timeout, max_output_bytes, cpu_seconds, memory, processes, rate, concurrency)`.

* **(v2.1, IS-P8)** Caller-supplied limit-like arguments (`limit`, `max_entries`, `timeout`, ...) must be integers >= 1, otherwise `400 args.type`; they are clamped to the effective limits, never raised by them.
* Each op declares which keys it honours (`limits=` in `@op`; shown in the catalog).
* **Effective limit = min** over: op default, winning statement, `Narrow` hooks, operator layer. Never max.
* `rate="10/min"` token bucket per `(principal, op selector of the winning statement)`; `concurrency=n` semaphore
  likewise. Exceeding -> `429 limit.rate` / `limit.concurrency` with `Retry-After`.
* `max_bytes` on uploads is enforced while streaming (reading `Content-Length + body`), not after buffering;
  on downloads by a counting writer. Violations: `413 limit.max_bytes`. `max_entries` truncates listings and sets
  `truncated: true` (not an error). Command `timeout` keeps the legacy shape (HTTP 200 with `timed_out: true` on the
  legacy `/shell` binding; `RPC` returns the same body) to stay compatible.
* **Memory/DoS bounds on the transport** (review round 4, S4.1): the body size is checked against `Content-Length` *before* reading
  (`limit.request_too_large`, default 100 MiB, per-op `max_bytes` x 4/3 for base64 ops); the server caps concurrent request threads
  (`max_connections`, default 64; excess get `503 server.unavailable`) so `threads x body size` is bounded; stream ops (`sse`, `ws`, `bytes`) default
  to `concurrency=8` per principal; archive/search/listing ops carry `max_entries` and a deadline.
* Size strings: `"10MB"` (10^6), `"10MiB"` (2^20), `"1GiB"`; integers are bytes; durations `"90s"`, `"5m"`, `"1h"`.

## 10. Configuration sources, layering, reload

Sources, from author to operator (later layers can only **restrict** from layer 3 on):

| # | Layer | How | Can allow? |
|---|-------|-----|-----------|
| 1 | Python code | `SandboxServer(policy=...)`, `start(policy=..., preset=...)`, `enable_builtin(...)` | yes |
| 2 | Baked config | `/etc/agent-sandbox/server.json` (or `ABX_SERVER_CONFIG`), compiled from the `server:` block of `template.yaml` or `server.yaml`; legacy `/etc/agent-sandbox/server-policy.json` is read as `{"policy": ...}` | yes |
| 3 | Environment (author inputs) | `ABX_SERVER_PRESET`, `ABX_SERVER_ENABLED_GROUPS`, `ABX_SERVER_ENABLED_OPS` (never able to mount an explicit-only op) | yes (equivalent to layer 1) |
| 4 | Environment (restrictions) | `ABX_SERVER_DISABLED_GROUPS` (legacy), `ABX_SERVER_DISABLED_OPS`, `ABX_SERVER_READONLY=1`, `ABX_SERVER_RESTRICT_PATHS=/workspace` | **no** - restrict only |
| 5 | Operator drop-ins | `/etc/agent-sandbox/policy.d/*.json` (root-owned, read-only mount on hardened images) | **no** - restrict only |

Merge rule: layers 1-3 are concatenated rule lists. Layers 4-5 contribute only `deny` rules, `limits` minima, path-root
**intersections** and group/op disables; an `allow` in layers 4-5 is a config error (`check-config` and startup fail).
The effective policy has a `revision` (sha256 of the canonical JSON) reported by `/capabilities`.

**Config file schema** (JSON; YAML accepted when PyYAML is importable; the runtime itself needs only JSON):

```yaml
version: 1
preset: workspace-jail            # optional; string or list; params via `presets: [{name, ...}]`
rules:
  - allow: [files.list, files.stat, files.download]       # selectors
    principals: [role:viewer]                              # optional
    paths: {roots: [/workspace], deny: ["**/.env", "**/*.pem"], readonly: true, max_bytes: 50MB}
    limits: {rate: 60/min}
  - allow: commands.run
    principals: [id:grader]
    commands:
      allow: ["python3 /workspace/grade.py", "pytest -q {path}"]
      cwd: /workspace
      timeout: 60s
      env_pass: [PATH, LANG]
      env_set: [CI]
  - deny: [files.delete, "terminal.*"]
    reason: "not in this template"
auth: {tokens: [...]}              # section 5
audit: {sink: stderr, redact: [env, content]}
hooks: {timeout: 2s}
```

* **Hot reload: off by default.** Rationale: a policy that can change under a running agent is hard to reason about
  and to audit. Opt in with `ABX_SERVER_POLICY_RELOAD=sighup` (or `server.reload()` from Python): the new config is
  fully parsed, linted (lint *errors* abort), and swapped atomically; in-flight requests finish on the old snapshot;
  an audit record `core.reload` with old/new `revision` is written. Layers 4-5 are re-read, layer 1 (Python) is not.
* **Strict parsing (v2.1, IF-31).** `from_config` rejects unknown keys at every level (`config.unknown_key` with did-you-mean) and requires `version`; unknown *selectors* are `config.unknown_selector`; the config schema is versioned (`schema_version` in `server.json`) so a newer file on an older runtime fails closed instead of being half-read.
* **`check-config`** (`agent-sandbox-server check-config`; for a single decision use `explain`) validates schema,
  selectors-that-match-nothing, shadowed statements, escape-capable allow patterns, writable-script pairs, undeclared path-like op parameters, scopes with root `/`, `follow`
  symlinks, shell enabled, `*` selectors, open mode on non-loopback, and prints the effective op table.
* **`explain`** (the only spelling, N-4): `agent-sandbox-server explain --op files.download --arg path=/etc/passwd --principal viewer` prints the
  decision and the rule that produced it (same engine as `core.check` and `SandboxServer.explain`, offline).

## 11. Error model (policy and pipeline)

Body (legacy-compatible superset; `error` and `type` are exactly what old clients parse):

```json
{"error": "path is not permitted", "type": "PolicyDenied", "code": "policy.path_not_allowed",
 "op": "files.download", "request_id": "r-7f3c", "details": {"param": "path"}}
```

On the OpenAI wire (`/v1/**` routes) the same condition renders as `{"error": {"message", "type", "param", "code"}}`.

| Family `code` | HTTP | Meaning |
|---------------|------|---------|
| `auth.required`, `auth.invalid`, `auth.conflicting_credentials` | 401 | missing/invalid token (generic message); Bearer and `X-Access-Token` differ |
| `auth.rate_limited` | 429 | failed-auth limit (credential fingerprint) |
| `request.bad_target`, `request.host_denied`, `request.origin_denied`, `request.bad_content_type`, `request.bad_json`, `request.busy` | 400 / 403 / 415 / 503 | transport checks of pipeline step 0-1 |
| `config.*` | start-up only | `auth_secret_missing`, `auth_secret_weak`, `secret_inline`, `reserved_id`, `open_non_loopback`, `open_exec`, `unknown_key`, `unknown_selector`, `unknown_preset`, `lint_errors`, `scope_required`, `state_dir_unsafe` |
| `policy.scope_required`, `policy.scope_unbound`, `policy.hook_bad_return`, `policy.hardlink_denied`, `policy.not_regular_file`, `policy.url_denied`, `policy.url_invalid` | 403 | v2.1 additions |
| `op.not_enabled` | 404 | **(v2.1)** unknown id, unknown route, unknown adapter **and** not mounted for this caller: one code, identical bytes (suggestions only in `verbose` dev mode, among mounted ops) |
| `op.method_not_allowed` | 405 | `Allow` header lists methods |
| `args.invalid`, `args.missing`, `args.unknown`, `args.type` | 400 | schema validation (`details.param`) |
| `policy.denied_by_rule`, `policy.denied_by_hook`, `policy.hook_error` | 403 | deny rule / veto / hook failure |
| `policy.path_invalid`, `path_not_allowed`, `path_denied`, `symlink_denied`, `path_changed`, `read_only` | 403 | path scope |
| `policy.command_invalid`, `command_not_allowed`, `command_denied`, `command_not_found`, `executable_not_allowed`, `shell_not_allowed`, `env_var_denied`, `signal_not_allowed` | 403 | command scope |
| `policy.language_not_allowed`, `model_not_allowed`, `agent_option_denied` | 403 | op-specific allowlists (URLs use `policy.url_denied`/`url_invalid`) |
| `policy.not_permitted` | 403 | a rule matched but its constraints rejected the call and no more specific code applies |
| `limit.max_bytes`, `limit.request_too_large` | 413 | size |
| `limit.rate`, `limit.concurrency` | 429 | with `Retry-After` |
| `install.required`, `install.pending`, `install.failed`, `install.checksum_mismatch`, `install.read_only`, `install.disabled`, `install.network_unreachable` | 424 / **202** / 502 / 502 / 503 / 403 / 503 | lazy install ([06](06-lazy-install.md)); `install.pending` is a 202 with a job id |
| `idempotency.mismatch` | 409 | same `Idempotency-Key`, different request hash (`x-should-retry: false`) |
| `agents.*` | 4xx/5xx | agents runtime ([05](05-agents-api.md)) |
| `server.internal`, `server.unavailable`, `server.shutting_down` | 500/503 | server faults (no internals leaked) |


**403 vs 404 leakage rules**

1. Not mounted for you = 404 (never 403): callers cannot probe which ops exist beyond what `/capabilities` shows them.
2. Paths: policy first, existence second; the same `403` for existing and non-existing out-of-scope paths. Messages
   never echo canonical or resolved paths (only the caller's own argument via `details.param`).
3. `policy.denied_by_rule` may include the rule's `reason` string authored by the operator; the rule *names* and glob
   lists are shown only to admin principals.
4. **(v2.1, IS-A5)** Unknown and unmounted ops are byte-identical **and** both are audited (the audit record notes `mounted: false`), so probing is visible to operators without being visible to callers.
5. 401 vs 403/404: unauthenticated callers always see 401 first, even for unknown routes (pipeline step 3 precedes every 404); `core.health` is anonymous by
   default (v1 behaviour, returns only `{status, version}`) and can be made authenticated with `auth.anonymous_health: false`.

## 12. Security properties and threat model

Promised (each should have a bypass test):

* P1. An op without a matching allow rule cannot be invoked by any route (including RPC, aliases, REST bindings).
* P2. A call that passes path policy touches only the canonical admitted path, race-free beneath the root, and
  never follows a symlink out of a `within` scope.
* P3. A call that passes command policy executes exactly the admitted `argv` with the admitted `env`/`cwd`, no shell.
* P4. Hooks and scope failures deny.
* P5. Operator layers cannot be loosened by author layers or callers.
* P6. Secrets (token values, env values, `content`) are never written to audit/logs by default.
* P7. **(v2.1)** A server with an unset/short auth secret, an open exec policy on a non-loopback bind, or lint errors does not start.
* P8. **(v2.1)** Server secrets and state (`state_dir`, tools dir, `/proc`, `/sys`, `/dev`) are unreachable through any path scope, and the server process is not readable by its own children (`PR_SET_DUMPABLE=0`).
* P9. **(v2.1)** A deny is at least as strong as the allow it overrides: canonical paths, ancestors, relative anchors, one argv normalisation, explicit-only ops reached.
* P10. **(v2.1)** Agent sessions are exec-effect operations and require an explicit `AgentScope`; they do not inherit file/command scopes (they are *not* confined by them: stated, linted, section 15.6).

Not promised (documented honestly): confinement of an *allowed program* (a permitted `git`/`python3 script.py`
can do what the process user can do), the agents (they run CLIs with the server user's privileges; `AgentScope` passes native sandbox flags to the CLI, **requires** an explicit workdir, permissions level and
command/model allowlists, and a lint warns that file/command scopes do **not** apply; `permissions="full"` needs `unconfined_ok=True`), kernel
isolation, DoS by an authenticated principal beyond the configured limits, hard-link tricks, other local users.
Network egress control is the platform's responsibility; the server only labels ops with the `net` effect.

## 13. Mapping from the legacy/in-flight concepts

| Old | New |
|-----|-----|
| `CapabilityGroup.FILE_OPS` etc. | `group:file_ops` selector (golden list in 04) |
| `enable_builtin(table, group)`, `table.disable_group(...)` | convenience over `Policy` rules; still work |
| `ABX_SERVER_DISABLED_GROUPS` | layer 4 (restrict) |
| `ABX_SERVER_ENABLED_GROUPS` | layer 3 (author) - needed to enable `browser`, `dev_tools`, `agents` |
| scopes like `files:read` | derived sugar: `scope:files.read` = `allow("effect:read")` over the `files.*` ops; not a primitive |
| `POST /capabilities/check` | `core.check` (alias `capabilities_check`), same JSON |
| `X-Access-Token` only | both headers on every route, `Authorization: Bearer` wins, conflict is 401 |
| default (no policy) | `presets.legacy_compat()` (loud; section 4) |

## 14. Observability

* **Audit record** (JSON line): `ts, request_id, op, principal, roles, allowed, code, rule, status, duration_ms,
  paths (canonical), argv_hash (not argv), bytes_in/out, remote_addr`. `audit.redact` list removes fields; `content`,
  `env` values and tokens are never recorded.
* Sinks: `stderr` (default when `ABX_SERVER_AUDIT=1`), `file:/var/log/agent-sandbox/audit.jsonl` (size-rotated,
  stdlib), Python callables via `@policy.audit`. A failing sink never fails a request.
* **Metrics/OTel**: counters `abx.op.calls{op,allowed,code}`, histogram `abx.op.duration{op}` through the host `otel`
  facade when configured; no dependency otherwise.
* `/capabilities` and `core.check` give callers their own effective view; `describe` gives operators the full one.

## 15. v2.1 hardening rules (normative)

These rules come from the independent security review (41 findings) and are the contract an implementation codes against.
Each carries its finding id.

### 15.1 Listener and transport (IS-A2, IS-A3, IS-A8, IF-19)

1. **Request target.** The target is taken from the raw request line (`BaseHTTPRequestHandler` rewrites a leading `//`). `//`, `/./`, `/../`, `%2f`, `%2e`, `%5c`, a backslash, NUL or control characters -> `400 request.bad_target`.
2. **Host and Origin.** `Host` must be a loopback name or in `allowed_hosts`; `Origin`, when present, must be in `allowed_origins` -> `403 request.host_denied` / `request.origin_denied`. This stops DNS rebinding and cross-origin browser calls
   to a loopback server (a browser can send a cross-origin `POST` with a token-less simple request; with the server's open mode that was a remote-code-execution primitive).
3. **Content-Type.** A request with a body must be `application/json` -> `415 request.bad_content_type`, so `text/plain` "simple requests" never reach a handler. The size check (`Content-Length` -> 413) precedes the body read.
4. **Timeouts and pool.** Socket header and body reads time out after 3 s per read (default; `header_timeout`). A bounded **pre-authentication pool** (`max_pre_auth`, default 64) answers `503 request.busy` beyond the bound; `core.health` and `core.capabilities` have a reserved slot
   so readiness probes are never starved (IF-19). Slow-loris sockets are closed without a traceback.
5. **Order** (normative): target -> host/origin -> auth -> size -> content-type -> body.

### 15.2 State, secrets, process (IS-L1, IS-C6, IS-A1)

* **State directory.** Agent journals, tools and the idempotency table live in `state_dir`, default `~/.local/state/agent-sandbox` (`/var/lib/agent-sandbox` for root), **never `/tmp`**. `prepare_state_dir` requires mode `0700`, owner = the server user, and not group/world writable,
  otherwise `config.state_dir_unsafe`; it registers the directory with `protect_dir` so **no `PathScope` can reach it** whatever its roots (the system deny list, 15.3).
* `harden_process()` (`PR_SET_DUMPABLE=0`, `RLIMIT_CORE=0`) is called by `start_http`; children receive only `env_pass` names from the start-up snapshot.
* `system.env.set` writes a per-server **overlay** (`ctx.env_overlay`) that is merged into *nothing but* the env of later children of the **same op family that declares env input**; it never writes `os.environ`, refuses `ENV_NEVER` names and `ABX_*`, is explicit-only (section 2), and is never part of any group or preset except `legacy_compat` with `ABX_SERVER_LEGACY_ENV_SET=1`.

### 15.3 Matching and path machinery (IS-P2, IS-P3, IS-P9, IS-F1, IS-F2, IS-F4, IS-F5)

* **Glob matcher.** Deny and allow globs are compiled to a segment matcher that runs in time linear in the path length; there is **no regex** built from user globs. Caps: path <= 4096 characters, <= 256 segments, <= 3 `**` per pattern. Over the cap is `policy.path_invalid` (never a hang).
* **System deny list** (always on, not removable): `/proc`, `/sys`, `/dev`, plus every `protect_dir`. It is checked on the lexical **and** the real path of every statement.
* `PathScope.anywhere(unsafe=True)` and `CommandScope.unrestricted(unsafe=True)` are the only unconfined forms and both are lint **errors**.
* Resolution, race-free opens, hardlink and non-regular-file refusal: section 6.1-6.2.

### 15.4 `UrlScope` (IS-U1, IS-U1b)

`UrlScope(hosts=(), schemes=("https",), ports=(), paths=("/**",), block_private=True)`. The URL is parsed **once** with a strict parser and the **parsed hostname** is compared (never a glob over the raw string). Rejected as `policy.url_invalid`: userinfo (`@`), fragments, backslashes, control or
non-ASCII characters, numeric/hex/octal host spellings, host characters outside `[a-z0-9.-]`, lengths over 2048. `scheme`, `port` (default per scheme) and the path glob are checked on the parsed parts; a mismatch is `policy.url_denied`. The handler receives the **canonical URL** and must use it.
`block_private=True` refuses every literal address that is not globally routable: RFC 1918, loopback, link-local, CGNAT `100.64.0.0/10` (includes Alibaba `100.100.100.200`), ULA, IPv4-mapped IPv6. DNS names are resolved by the handler's connector, which re-checks the resolved address (the
check is in the shared `fetch` helper, not in the handler). `browser.navigate`, `devtools.*` URL params and `agents.*` model endpoints use it.

### 15.5 Construction-time and start-time checks (IS-A1, IS-C2, B-2, B-18, IF-31)

`SandboxServer(...)` raises at construction: `config.unknown_selector`, `config.unknown_preset`, `config.reserved_id`, `config.secret_inline`, `config.auth_secret_missing`, `config.auth_secret_weak`, and (strict config) `config.unknown_key`. `start_http`/`start()` additionally raises `config.open_non_loopback`, `config.open_exec`,
`config.state_dir_unsafe`, `config.lint_errors`. Lints (`SandboxServer.check()`, `check-config`):

| Level | Lint |
|---|---|
| error | `config.scope_required` (allow of a path/command/url/agent op without its scope), anywhere/unrestricted scopes, `shell=True` with argv patterns, escape-capable/project-file/writer/network commands with `...` or glob arguments, `AgentScope(permissions="full")` without `unconfined_ok`, `follow` symlinks |
| warn | registered-but-unmounted custom op (not built-ins), experimental adapter mounted, principal selector that no configured token produces, `core.effects_undeclared`, shadowed statements, `*` selector, adapter `permissions` weaker than `read-only` |

### 15.6 Agent sessions are exec-effect operations (IS-G1)

`agents.<a>.run`, `agents.<a>.sessions.create`, `agents.<a>.sessions.send_event` and the generic `agents.sessions.create`/`send_event` carry effects `exec` + `net` and `agent_scope=True`.
Every allow statement that mounts one must carry an `AgentScope(workdir, permissions, commands=(), models=(), max_turns=None, unconfined_ok=False)`:
`workdir` is a `PathScope`-checked directory (the CLI's cwd and writable root), `permissions` is `"read-only"` (default and the only value the presets use), `"workspace-write"` or `"full"` (needs `unconfined_ok`), `commands` is the CLI's own command allowlist (passed as the native flag where the CLI has one),
`models` the allowed upstream model names, `max_turns` a cap. `permissions=None` is refused at admission. **The file and command scopes of other statements do not apply inside an agent process**; the lint and the docs say so, and `explain` prints "agent child is not confined by path/command scopes".
`sessions.create` is explicit-only and `install` is never implied (IS-L2): the implicit-install step of the pipeline runs only if the *same principal* could call `agents.<a>.install` (allow present, no deny) and `install.mode` permits, otherwise `424 install.required`; implicit installs are globally limited (one at a time, `install.max_per_hour`) and audited with the triggering principal.
LLM credentials (IS-S1): the child holds the key in its environment in 0.3.0; `doctor` and `explain` print "key is exposed to agent-executed code" per adapter. The loopback key-injecting proxy (`llm.proxy`) is **deferred** (post-0.3.0, tracked in the disposition table).

### 15.7 Installer trust (IS-L3, IS-L4, IS-L5)

`ABX_TOOL_<NAME>` and `ABX_TOOLS_DIR` are read once at start from the **process** environment and accepted only if the target and every parent are owned by root or the server uid and not group/other writable. `install.use_path` defaults to `false` in `lazy` mode. Trees not owned by root are re-verified against the recorded tree digest
(size + sha256, cached per process) before `ready`. `lock` rejects a manifest whose `resolved` URL hosts are not in `hosts` or that lacks `integrity` (`install.manifest_invalid`); `npm ci --ignore-scripts`; `playwright-browser` archives are pinned by sha256 recorded at `lock`. Details: [06](06-lazy-install.md).

### 15.8 Read-only mode, tokens in URLs, ids, idempotency (IS-G2, IS-T1, IS-J1, IS-I1)

* `ABX_SERVER_READONLY=1` (layer 4) removes **every** op whose effects include `write`, `delete`, `exec` or `admin` and forces every `PathScope` to `readonly=True`; `explain` lists the removed ops (not only `write`-tagged ones).
* Tokens are never accepted in a query string. WebSocket clients use a single-use 30 s ticket (`POST /terminal/{id}/ticket`, subprotocol `abx.token.<ticket>`); logs record paths without the query and redact `Authorization`, `X-Access-Token`, `Cookie`, `Sec-WebSocket-Protocol`. Until tickets exist, the PTY listener is bound to loopback only.
* Session, process, terminal, turn and event ids are `secrets.token_urlsafe(16)`; ownership is checked before lookup so a foreign id and a wrong id are byte-identical.
* `Idempotency-Key` (<= 128 printable ASCII) maps `(principal, key) -> (sha256 of the canonical request, response)`, LRU-capped (10 000); the same key with a different request is `409 idempotency.mismatch` with `x-should-retry: false`.
