# Independent security and policy-bypass review of Server SDK v2

Reviewer: independent adversarial reviewer (did not write the design). Lens: security and policy bypass.
Scope: `README.md` (decisions D1-D24), docs 01-10, the executable prototype in `spikes/ebxp`, and the current server
code under `server-sdk/src/easy_sandbox/server` (read only; other workers are editing it, nothing was changed).

Executable evidence: `spikes/independent-security/` (stdlib only, no network, no secrets).

```bash
cd python-sdk/docs/en/design/server-sdk-v2/spikes/independent-security
python3 run_all.py            # prints VULNERABLE / HELD / ERROR per check; exit 1 only if a HELD- check regresses
python3 run_all.py IS-C       # filter by id prefix
python3 run_all.py --strict   # exit 1 while any finding still reproduces (use as the fix-verification gate)
```

Current result against the prototype: **30 reproducing findings, 11 held-up checks, 0 errors**. A PoC marked
"design-only" has no executable counterpart because the prototype does not implement that part (agents, lazy install);
the clause and fix are still normative-text bugs.

"Prototype vs. design" matters: a few PoCs fail because the spike is looser than the text (IS-P5b, IS-A5, IS-A7).
Those are still findings, because 10 section 5 says the spike is the executable oracle for the tests.

## 1. Verdict

**Not ready to implement as written. Ready after the two critical and sixteen high findings are folded into the
design text.** The core architecture is sound: operations as identity, default-deny with deny-overrides, canonical
paths plus `open_beneath`, typed command tokens, authenticate-before-404, restrict-only operator layers. The attacks
that most people try first (`..`, symlinks, read/write races, `O_TRUNC` victims, caller `PATH`, `LD_PRELOAD`, shell
metacharacters, cross-session reads) held (section 4).

What fails is the layer between the building blocks and the promise in the goals:

1. **Scopes are optional and silently absent.** A bare `allow(commands.run)` or `allow(files.download)` is the
   natural thing for an author (or an AI) to write, and it is either everything or undefined (IS-P1, IS-P1c, IS-P1b).
2. **Deny rules are weaker than allow rules** because they match different strings (relative vs canonical, `command`
   vs `argv`, directory entry vs descendants): IS-P2, IS-P2b, IS-P3, IS-P4.
3. **The server's own secrets and state are inside every broad scope** (`/proc/self/environ`, `/proc/<pid>/environ`,
   `/tmp/easy-sandbox/*`): IS-F1, IS-C6, IS-L1. The headline example "files: only under /tmp" collides with the default
   agent state and tools directories.
4. **Legacy ops keep their group membership**, so `system.*` and `group:system` mount `system.env.set`, which can
   rewrite the server's own environment and with it the tool resolver and install guards (IS-C2, IS-C2b, IS-L3).
5. **The agent API is a policy bypass by construction** (IS-G1): `agents.<a>.sessions.create` runs an LLM-driven CLI
   with the server user's privileges, so a principal denied `commands.run` and `files.*` can still read files and
   execute commands unless AgentScope is mandatory and conservative.
6. **Transport has no timeouts and no cross-origin defence** (IS-A2, IS-A3), and a missing token secret turns the server
   into an open admin endpoint (IS-A1).

## 2. Findings summary

| Severity | Count | IDs |
|----------|------:|-----|
| Critical | 2 | IS-A1, IS-C2 |
| High | 16 | IS-A2, IS-A3, IS-P1, IS-P2, IS-P2b, IS-P3, IS-P4, IS-P9, IS-F1, IS-F2, IS-C1, IS-C2b, IS-C6, IS-U1, IS-L1, IS-G1 |
| Medium | 18 | IS-P1b, IS-P1c, IS-P5, IS-P5b, IS-P8, IS-F4, IS-F5, IS-A7, IS-C2c, IS-C5, IS-C7, IS-U1b, IS-S1, IS-L2, IS-L3, IS-L4, IS-G2, IS-T1 |
| Low | 5 | IS-A5, IS-A8, IS-L5, IS-I1, IS-J1 |
| Total | 41 | |

Prioritised fix order: IS-A1, IS-C2 + IS-C2b + IS-L3 (one change set: env and resolver), IS-G1, IS-P1/P1b/P1c (scope required),
IS-P2/P2b/P3/P4 (deny parity), IS-F1 + IS-C6 + IS-L1 (protected paths and dumpable), IS-A2 + IS-A3 (transport), IS-C1,
IS-F2, IS-U1, IS-P9, then the medium and low items.

Decision conflicts, summarised: D4 (IS-A1, IS-A5, IS-A7), D5 (IS-P2, IS-P2b, IS-P3, IS-P4, IS-P5, IS-P5b), D6 (IS-C2, IS-P4,
IS-L2), D7 (IS-F1, IS-F2, IS-F4, IS-F5), D8 (IS-P1, IS-C1, IS-C2b, IS-C2c, IS-C5, IS-C6, IS-C7), D9 (IS-A3, IS-P8, IS-P9),
D11 (IS-C2, IS-G2), D15 (IS-S1, IS-U1), D17 (IS-L1, IS-I1, IS-J1), D18 (IS-L1, IS-L3, IS-L4, IS-L5).

Each finding: clause, exploit, fix wording (paste-ready), PoC.

---

## 3. Findings

### Critical

#### IS-A1 Missing token secret yields open admin server
- **Severity**: critical. **Contradicts**: D4 (default-deny), D12 (open mode only when nothing is configured).
- **Clause**: 03 section 5: "`token_env` ... secret from env", "No token configured -> open mode (legacy): principal
  `{id: anonymous, roles: [admin]}`".
- **Exploit**: a template declares `auth.tokens: [{id: grader, token_env: EBX_TOKEN_GRADER}]`. The variable is not
  injected (typo, forgotten secret, provider bug). The resolver drops the entry, sees "no token configured" and serves
  every request as anonymous admin. No error, no log line the operator is forced to read.
- **Fix wording** (03 section 5, replace the last bullet group):
  > A configuration that lists any `auth.tokens` entry is an *authenticated* configuration. If any entry's
  > `token_env` is unset or empty, or a `token_sha256` is not 64 hex characters, the server **refuses to start**
  > (`config.auth_secret_missing`), naming the entry id and variable name, never a value. Open mode is entered only
  > when the *configuration* declares no auth entries and `EBX_SERVER_TOKEN` is unset, and is refused on a non-loopback
  > bind unless `--allow-open` (or `EBX_SERVER_ALLOW_OPEN=1`) is given. `check-config` and `doctor` report open mode as an error, not a warning, whenever any policy
  > other than `presets.legacy()` is configured.
- **PoC**: `poc_transport.py::IS-A1`.

#### IS-C2 Legacy `system.env.set` is mounted by `system.*` and `group:system`
- **Severity**: critical. **Contradicts**: D6 (explicit-only ops), D11 (a runtime op rewrites layer-3/4 inputs), D8.
- **Clause**: 03 section 2 selector table: `ns.*` and `group:<name>` match all legacy ops; D6 lists only `agents.<a>.install` and
  `core.reload` as explicit-only. The in-flight handler writes `os.environ[key] = value`.
- **Exploit**: an operator grants "system information" with `allow("system.*")` or `group:system` (also what
  `presets.full_access()` implies). The caller then runs `system.env.set` for `EBX_TOOL_CODEX=/tmp/x/evil`,
  `EBX_INSTALL_UNPINNED=1`, `PATH`, `HTTPS_PROXY`, or clears `EBX_SERVER_ENV`. The next agent session executes the
  attacker's binary (06 section 5: `EBX_TOOL_<NAME>` is first in the resolver order); with `HTTPS_PROXY` the next lazy
  install goes through an attacker proxy. Net effect: a read-only "info" grant becomes code execution.
- **Fix wording** (02 section 4 / D6 / 04): 
  > Explicit-only operations are all ops whose effects include `admin`, plus these named ops: `agents.<a>.install`,
  > `core.reload`, `system.env.set`, `system.env.unset`, `process.signal`, `terminal.create`, `commands.run`,
  > `commands.stream`, `files.delete`, `files.upload`. They are never matched by `ns.*`, `ns.**`, `group:`, `effect:` or
  > `*` on the **allow** side (they remain matched by every selector on the **deny** side, see IS-P4). `system.env.set`
  > writes only to a per-server `ctx.env_overlay` that is merged into the *child* environment of commands the same
  > principal starts through the server; it never writes `os.environ` and refuses every name in `env_deny`
  > (IS-C2b) and every name starting `EBX_`.
- **PoC**: `poc_commands.py::IS-C2`.

### High

#### IS-A2 Cross-origin and DNS-rebinding requests are executed
- **Clause**: 03 section 5 (token auth only) and 02 section 6 step 1 (no Host/Origin/Content-Type rule).
- **Exploit**: open mode on loopback (the default in dev and in many template runs) is reachable from any web page in a
  browser on the same host: `fetch("http://127.0.0.1:8080/ops/commands.run", {method: "POST", mode: "no-cors",
  headers: {"Content-Type": "text/plain"}, body: "{...}"})` is a CORS "simple" request, so no preflight; the server parses
  the body as JSON regardless. DNS rebinding reaches it with a foreign `Host`. WebSocket handshakes (`/terminal`) have no
  Origin rule at all (cross-site WebSocket hijacking).
- **Fix wording** (02 section 6, new step 1a, normative):
  > Before routing: (a) a request with a body whose `Content-Type` is not `application/json` (or the op's declared
  > binary type) is `415 request.unsupported_media_type`; (b) if an `Origin` header is present it must equal an entry
  > of `server.allowed_origins` (default: empty = reject any request that carries `Origin`; same-origin browser UIs
  > are listed explicitly); (c) `Host` must match `server.allowed_hosts` (default: the bind address, `localhost`,
  > `127.0.0.1`, `[::1]`, and the configured public hostname); otherwise `403 request.host_not_allowed`; (d) WebSocket
  > upgrades apply (b) and (c) and additionally require the token in a header or in the first message, never in
  > the URL (IS-T1). No CORS headers are ever emitted unless `allowed_origins` is set.
- **PoC**: `poc_transport.py::IS-A2`.

#### IS-A3 No header/body read timeout: one idle socket per slot is a total outage
- **Contradicts**: D9 (transport bounds), 03 section 9 (max_connections 64).
- **Clause**: 03 section 9: "caps concurrent request threads (`max_connections`, default 64; excess get 503)".
- **Exploit**: 64 sockets that send a partial request line (slowloris) occupy all slots indefinitely; the cap that
  protects memory becomes the denial of service, and unauthenticated callers can do it (authentication happens after
  parsing).
- **Fix wording** (03 section 9): 
  > Each connection has `header_timeout` (default 10 s from accept to end of headers), `body_timeout` (default 30 s of
  > inactivity between body reads; total bounded by the op's `timeout`) and `idle_timeout` (default 30 s keep-alive).
  > Exceeding any closes the socket (`408` when a response is still possible). Connections not yet authenticated
  > count against a separate pool (`max_unauthenticated`, default 16) so they cannot starve authenticated
  > callers. A per-source-address cap (default 16 connections) applies before parsing.
- **PoC**: `poc_transport.py::IS-A3`.

#### IS-P1 Bare `allow(commands.run)` admits any command
- **Contradicts**: D8 (allowlist-first). **Clause**: 03 section 7 ("allow=" is a field of `CommandScope`; the statement
  form without `commands=` is not addressed) and section 3 step 3 ("check/resolve the command through its
  `CommandScope`" - nothing when there is none).
- **Exploit**: `Policy().allow(ops.commands.run, principals=["role:grader"])` admits `id`, `curl`, `sh -c ...`. `check-config`
  stays silent in the spike. This is the default thing an AI emits when asked "let graders run commands".
- **Fix wording** (03 section 3 step 3 and section 7): 
  > Every op declaring `command=` (or effects including `exec`) **requires** a `CommandScope` in each allow statement
  > that mentions it, directly or through a preset. A statement without one is a configuration error
  > (`config.scope_required`, loader and `check-config`), not a permissive default; the only way to run unrestricted
  > commands is `commands=CommandScope.unrestricted()` which is `*`-selector-lint-equivalent (lint error unless
  > `unsafe=True`). The same rule applies to every declared `paths=` / `urls=` / `languages=` parameter (IS-P1c).
- **PoC**: `poc_policy.py::IS-P1`.

#### IS-P2 Relative path bypasses a separate deny rule
- **Contradicts**: D5 (deny beats allow), D7. **Clause**: 03 section 3 step 2 (deny pass matches "any declared path parameter
  matching a glob") versus section 6.1 step 2 (relative paths anchor at the *allowing statement's* first root).
- **Exploit**: `deny(files.download, paths="/srv/data/secret/**")` plus `allow(files.download, paths="/srv/data")`. The
  caller asks for `secret/k`. The deny pass has no anchor and compares the raw string `secret/k` with an absolute glob:
  no match. The allow pass anchors at `/srv/data` and reads the file.
- **Fix wording** (03 section 3, before step 2): 
  > Path parameters are canonicalised **once**, by `resolve_path` against the *request's* anchor (the matching
  > statement's first root for the allow pass; the process cwd is never used), and **every** pass (deny and allow)
  > matches against that canonical string. A deny rule with `paths=` is evaluated once per candidate allow statement's
  > anchor (so a relative argument is denied if it is denied under *any* anchor that some allow statement could
  > give it). Relative arguments are rejected outright (`policy.path_invalid`) when the winning scope has more than one
  > root and the call has no explicit `anchor`.
- **PoC**: `poc_policy.py::IS-P2`.

#### IS-P2b Command deny and allow read different fields (`command` vs `argv`)
- **Contradicts**: D5, D8. **Clause**: 03 section 3 step 2 (deny with `commands=`) vs section 7.1 ("a command string is split ... an `argv`
  list is used as is").
- **Exploit**: `deny(commands.run, commands=["rm ..."])`, allow with `CommandScope(allow=["..."])`. The request carries
  `{"command": "echo hi", "argv": ["rm", "-rf", "x"]}`. The deny pass inspects `command`; the allow pass inspects
  `argv`; `rm` runs.
- **Fix wording** (02 section 3 and 03 section 7.1): 
  > `command` and `argv` are mutually exclusive request fields (`args.invalid` when both are present). The pipeline
  > normalises to exactly one `argv: list[str]` in step 6 and **every** policy step (deny patterns, allow patterns,
  > lint, hooks, audit) sees only that value; the executed process receives that same list.
- **PoC**: `poc_policy.py::IS-P2b`.

#### IS-P3 A deny glob for a directory does not cover its descendants
- **Contradicts**: D5. **Clause**: 03 section 6 `deny` field: "`**/.ssh`" style patterns.
- **Exploit**: `deny=("**/.ssh",)` blocks the directory entry only; `home/.ssh/id_rsa` matches `^(.*/)?\.ssh$` no
  longer, and is readable. Authors write `**/.git`, `**/node_modules`, `**/.aws`, expecting subtree semantics (as in .gitignore).
- **Fix wording** (03 section 6 table): 
  > A `deny` glob matches a path when it matches the path **or any ancestor directory of the path** (below the root).
  > `**/.ssh` therefore denies `.ssh`, `.ssh/id_rsa`, and every descendant. Use a trailing `/!` only in `allow`-side
  > exceptions of the same statement (not supported in v2).
- **PoC**: `poc_policy.py::IS-P3`.

#### IS-P4 Deny does not reach explicit-only ops
- **Contradicts**: D5 vs D6 (the two decisions interact). **Clause**: D6 "never matched by wildcard/group/effect/preset".
- **Exploit**: an operator hardening step writes `deny("agents.**")` or `deny("group:agents")` ("no agents on this
  image"). Because D6 is implemented as "wildcards never match", the deny does not match `agents.codex.install`; an
  unrelated explicit `allow(agents.codex.install, principals=["role:ops"])` in another layer remains effective, and
  more importantly the operator believes the family is disabled. The prototype returns HTTP 200 for install.
- **Fix wording** (D6, 02 section 4, 03 section 2): 
  > Explicit-only restricts **allow** matching. `deny` selectors match explicit-only ops exactly like any other op:
  > `deny("agents.**")`, `deny("group:agents")`, `deny("*")` and `EBX_SERVER_DISABLED_*` all cover
  > `agents.<a>.install` and `core.reload`.
- **PoC**: `poc_policy.py::IS-P4` (the allow side is pinned in `poc_held.py::HELD-explicit-deny`).

#### IS-P9 Regex backtracking in deny globs freezes the whole server
- **Contradicts**: D9. **Clause**: 03 section 6 `deny`: "`**` crosses `/`" implemented by translating to a regex.
- **Exploit**: `**/a/**/a/**/b` against a 3.8 KB path of repeated `a/` took over 4 s with the GIL held; with 4 `**` the
  time is exponential in path length. One authenticated guest request stalls every other request on the process.
- **Fix wording** (03 section 6.1): 
  > Glob matching is implemented as a linear-time segment matcher (split on `/`, `**` as a segment wildcard with
  > memoised two-pointer matching), never by compiling to `re`. Path length is capped at 4096 *and* segment count at 256
  > before any glob runs. A policy pattern with more than 3 `**` is a config error.
- **PoC**: `poc_policy.py::IS-P9`.

#### IS-F1 `presets.readonly()` reads `/proc/self/environ` (every token env var)
- **Contradicts**: D7. **Clause**: 03 section 4 (`presets.readonly(paths="/")`) and 03 section 6.2 "`/proc` magic links (denied by
  default glob list: `/proc/**` unless explicitly rooted)".
- **Exploit**: `readonly(paths="/")` is explicitly rooted at `/`, so by the clause `/proc/**` is reachable.
  `files.download` of `/proc/self/environ` returns `EBX_SERVER_TOKEN`, every `token_env` secret and all LLM keys. The
  prototype demonstrates this for a role holding only the readonly preset. Same-uid `/proc/<pid>/mem`, `/proc/<pid>/cmdline`,
  `/proc/self/cwd`, `/proc/self/root` links are similar.
- **Fix wording** (03 section 6 and 6.2): 
  > Every `PathScope` carries a **non-removable system deny list** evaluated on the canonical path and on the opened
  > fd's `/proc/self/fd` target: `/proc/**`, `/sys/**`, `/dev/**` (except `/dev/null`, `/dev/zero`, `/dev/urandom`
  > for exec only), the server's own state dirs (`$EBX_AGENTS_STATE_DIR`, the tools dir, the config dir, `policy.d`,
  > `server.json`) and any file owned by a different user than the server when the scope is `/`-rooted. Authors can
  > *add* deny entries but cannot remove these; there is no `unsafe` switch. `readonly(paths="/")` is a config error;
  > the shortest accepted preset root is a named subtree.
- **PoC**: `poc_paths.py::IS-F1`.

#### IS-F2 `files.delete` follows a parent swapped after admission
- **Contradicts**: D7, P2 in 03 section 12. **Clause**: 03 section 6.2 ("open_beneath ... never pass O_TRUNC") only describes open
  and truncate; delete/move/mkdir/chmod are not covered by "Handlers use only this value".
- **Exploit**: admission resolves `/srv/a/sub/f` (inside). Between admission and `os.unlink(path)` another actor with
  write access to `/srv/a` replaces `sub` with a symlink to `/etc`; `unlink` of the string path deletes the target
  outside the root. The prototype unlinked a file outside the root.
- **Fix wording** (03 section 6.2, add bullet): 
  > **Every** mutating handler operation (`unlink`, `rmdir`, `rename`, `mkdir`, `symlink`, `chmod`, `chown`, `utime`,
  > `truncate`, `copy`, archive extraction) is performed with `*at` calls relative to the `open_beneath` directory fd
  > of the *parent* (`unlinkat`, `renameat2(RENAME_NOREPLACE)`, `mkdirat`, `fchmodat(AT_SYMLINK_NOFOLLOW)`), never with
  > a path string. `files.move` opens both parents beneath their roots and issues one `renameat` between the two
  > fds. A handler that calls `os.*` / `shutil.*` / `pathlib` with a path argument is a lint failure in the op-authoring
  > tests (10 section 5).
- **PoC**: `poc_paths.py::IS-F2`.

#### IS-C1 Glob token traversal in command scopes
- **Contradicts**: D8. **Clause**: 03 section 7.1 table: "literal / fnmatch glob (`*.py`, `-q`) matches exactly one argv element"
  alongside `{path}` which is canonicalised.
- **Exploit**: `allow=["cat /srv/pub/*"]`. `fnmatch` `*` crosses `/`, so `cat /srv/pub/../../etc/passwd` matches; the
  executed argv is the raw one. The review that introduced `{path}` fixed only typed tokens (F1.4).
- **Fix wording** (03 section 7.1): 
  > A literal/glob token containing `/` or `..` is matched with segment-aware semantics (`*` never crosses `/`, `..` and
  > `.` segments in the **argument** are rejected `policy.command_invalid` before matching). An argument that
  > begins with `/` or contains `/` and is matched by a glob is **canonicalised through the cwd PathScope exactly like
  > `{path}`**, and the canonical value replaces it in argv. `check-config` rejects glob tokens that can match a path
  > unless they are written `{path}` or `{path:/srv/pub}`.
- **PoC**: `poc_commands.py::IS-C1`.

#### IS-C2b Default `env_deny` covers a handful of names; `env_set` can then set `PATH`, `HOME`, proxies, `EBX_*`
- **Contradicts**: D8. **Clause**: 03 section 7.2: default deny list "`LD_*`, `DYLD_*`, `PYTHON*`, `NODE_OPTIONS`, `BASH_ENV`, `ENV`, `PERL5*`, `RUBY*`,
  `GIT_*`, `IFS`".
- **Exploit**: an author lists `env_set=["PATH", "HTTPS_PROXY"]` (reasonable-looking) or the AI copies a Dockerfile.
  Nothing in the default list stops: `PATH`, `HOME`, `TMPDIR`, `*_PROXY`, `SSL_CERT_FILE`/`SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE`,
  `NODE_PATH`, `npm_config_*`, `PIP_*`, `JAVA_TOOL_OPTIONS`, `GCONV_PATH`, `SHELLOPTS`, `PS4`, `PROMPT_COMMAND`, `LESSOPEN`,
  `XDG_*`, `EBX_*`, `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`. The prototype lists 24 such names.
- **Fix wording** (03 section 7.2): 
  > `env_set` is a list of **exact names**, each validated against a built-in `ENV_NEVER` set that cannot be
  > overridden: `PATH`, `HOME`, `USER`, `SHELL`, `TMPDIR`, `LD_*`, `DYLD_*`, `PYTHON*`, `NODE_*`, `npm_config_*`, `NPM_*`,
  > `PIP_*`, `UV_*`, `JAVA_*`, `_JAVA_*`, `JDK_JAVA_OPTIONS`, `GCONV_PATH`, `LOCPATH`, `NLSPATH`, `HOSTALIASES`, `*_PROXY`,
  > `*_proxy`, `SSL_*`, `CURL_*`, `REQUESTS_*`, `GIT_*`, `BASH_*`, `ENV`, `IFS`, `SHELLOPTS`, `PS4`, `PROMPT_COMMAND`,
  > `LESSOPEN`, `LESSCLOSE`, `PERL*`, `RUBY*`, `XDG_*`, `EBX_*`, `*_API_KEY`, `*_BASE_URL`, `*_TOKEN`. A config listing
  > one is an error; a caller supplying one is `policy.env_var_denied`. Values are limited to
  > `[A-Za-z0-9_@%+=:,./-]{0,256}` unless the name is declared with `pattern:`.
- **PoC**: `poc_commands.py::IS-C2b`.

#### IS-C6 A scrubbed child can read the server's secrets via `/proc/<ppid>/environ`
- **Contradicts**: D8 ("allowlisted environment (no inherited EBX_*)", 05 section 7).
- **Clause**: 03 section 7.2 environment scrubbing only; no mention of same-uid `/proc`.
- **Exploit**: an allowed `cat`, `python3 grader.py`, or any agent turn runs as the server user. Scrubbing its *own*
  environment does nothing: `/proc/<parent pid>/environ` holds every token and LLM key. Confirmed in the prototype.
- **Fix wording** (03 section 7.2 and 05 section 7, new bullet): 
  > The server calls `prctl(PR_SET_DUMPABLE, 0)` at startup (before reading secrets, and again after any `setuid`),
  > so `/proc/<pid>/{environ,mem,maps,fd}` are root-only for same-uid readers; it removes every secret it no longer
  > needs from `os.environ` after config load (secrets live in `Principal` objects and an in-memory table only), and
  > runs children through the launcher in a fresh PID namespace/`hidepid=2` mount when available (`doctor` reports
  > which protection is active). Tests: `HELD-C6b` pins the dumpable behaviour; add the same for the agent turn runner.
- **PoC**: `poc_commands.py::IS-C6`; the fix is validated by `HELD-C6b`.

#### IS-U1 `UrlScope` glob matching is fooled by URL parser differentials
- **Contradicts**: D15 (`llm_hosts`), 04 section 9. **Clause**: 04 section 9 "`allow`/`deny` glob lists over `scheme://host/path`".
- **Exploit**: `allow=["https://*.example.com/*"]` matches `https://evil.test#.example.com/x`,
  `https://evil.test?.example.com/x`, `https://evil.test\.example.com/x`, `https://user@evil.test:80@a.example.com/`
  depending on the parser. The browser or `urllib` connects to `evil.test`. Same applies to `llm_hosts`.
- **Fix wording** (04 section 9): 
  > `UrlScope` parses the URL once with a strict parser (`urllib.parse.urlsplit`, then reject any URL with userinfo, a
  > backslash, whitespace/control characters, a fragment before the path, a non-ASCII or non-IDNA host, or port outside
  > `ports=`), compares the **parsed, lowercased, IDNA-encoded hostname** against `hosts=` (exact or `*.suffix` with
  > the dot boundary), the scheme against `schemes=`, and the path against `paths=`. Globs over the raw URL string are not
  > offered. The URL passed to the handler is the re-serialised canonical form.
- **PoC**: `poc_misc.py::IS-U1`.

#### IS-L1 Default agent state and tools directories live under `/tmp`, inside the most common file scope
- **Contradicts**: D17 (session ownership), D18 (tools dir integrity), and the product example "files: only under /tmp".
- **Clause**: 05 section 9: `$EBX_AGENTS_STATE_DIR` default `/tmp/easy-sandbox/agents`; 06 section 5: tools-dir chain ends
  `/tmp/easy-sandbox/tools`; 03 section 4 `download_only(root="/tmp")`.
- **Exploit**: (a) a principal granted `files.download` under `/tmp` reads other principals' session journals
  (prompts, outputs, file contents), bypassing D17 because the journal is just a file; (b) a principal with
  `files.upload` under `/tmp` replaces the target of `/tmp/easy-sandbox/tools/bin/<binary>` or a `.cache/<sha256>` entry
  (the cache is trusted by hash name, not re-hashed) when the fallback tools dir is in use, i.e. code execution as the
  server user at next agent turn; (c) another local user pre-creates `/tmp/easy-sandbox` and owns it.
- **Fix wording** (05 section 9 and 06 section 5): 
  > Defaults: state dir `<tools-parent>/state` resolved with the same chain as the tools dir; the final `/tmp`
  > fallback is created `0700`, with `mkdir` + `lstat` verifying owner == euid, mode `0700`, not a symlink, not
  > world/group writable, otherwise the server refuses to use it (`install.unsafe_dir`). All of: state dir, tools dir,
  > install cache, staging, `turn_dir`s and `policy.d` are in the **non-removable system deny list** of IS-F1 and are
  > refused by every `PathScope` whatever the roots (also for archive and search). `.cache/<sha256>` entries are
  > re-hashed on use when the directory is not root-owned. `check-config` errors when a path scope contains the
  > state or tools dir.
- **PoC**: design-only (the prototype has no agents or installer); the system deny list is exercised by IS-F1.

#### IS-G1 The Agents API is a confused deputy that bypasses file and command policy
- **Contradicts**: D8 and the product goal "command execution restricted to a scope"; 03 section 12 explicitly does "not promise"
  agent confinement (the honest disclosure is good; the default is the problem).
- **Clause**: 05 section 8 ("`workspace-write` (default)", lint "AgentScope ... the agent process is not confined by PathScope"), 03 section 4
  `agent_host` ("`commands.run` off").
- **Exploit**: a principal denied `commands.run` and `files.*` but granted `agents.codex.sessions.create`. The prompt
  "run `cat /etc/passwd` and print it" (or `curl` to an attacker host) executes through the CLI with the server user's
  privileges; `workspace-write` is the CLI's own sandbox, which is absent in a container without Landlock/seccomp and
  never limits reads. With `permissions="full-access"` it is root-equivalent for the sandbox user.
- **Fix wording** (05 section 8, replace the paragraph below the table): 
  > Creating an agent session is an op with effects `exec, write, net` and is **never** matched by `agents.*`,
  > `group:agents`, `effect:*` or presets other than `presets.agent_host`. Each allow statement must carry an
  > `AgentScope` with explicit `permissions` (no default; `config.scope_required`). `permissions` defaults for presets
  > to `read-only`. An adapter that cannot enforce the level on **this host** (Landlock/bubblewrap availability probed by
  > `doctor`, reported in `agents.<a>.status.enforcement`) refuses `workspace-write` and `full-access`
  > (`policy.agent_option_denied`) unless the statement sets `AgentScope(unconfined_ok=True)`, which is a `check-config`
  > warning shown in `explain`. Document in the first paragraph of 05 section 8: **"granting an agent op is
  > granting command execution."** The lint "agents allowed together with `files.*`" is an error, not a warning, when
  > `files.*` has a deny list the agent cannot see.
- **PoC**: design-only.

### Medium

#### IS-P1b Omitted `cwd` runs in the server's cwd
- **Clause**: 03 section 7.2 ("`cwd` is checked through the cwd PathScope"): behaviour when absent is unspecified.
- **Exploit**: caller omits `cwd`; the prototype ran `pwd` in the server's own working directory, outside the cwd scope.
- **Fix**: > When a `CommandScope.cwd` is set and the request has no `cwd`, the command runs in the scope's first root;
  > when the scope has no `cwd`, the request must provide one or the call is `policy.command_invalid`. The server's
  > process cwd is never inherited. Hooks see the resolved `ctx.cwd`.
- **PoC**: `poc_policy.py::IS-P1b`.

#### IS-P1c Bare `allow(files.download)` is undefined
- **Clause**: 03 section 3 step 3 "resolve every declared path param through the statement's PathScope" when none exists.
- **Exploit**: the prototype raises `KeyError`; an implementer who "fixes the crash" by passing the path through gets a
  full-filesystem read.
- **Fix**: see IS-P1 wording: "every declared `paths=` parameter requires a PathScope in each allow statement
  (`config.scope_required`); `paths="*"` is spelled `PathScope.anywhere()` and is a lint error without `unsafe=True`."
- **PoC**: `poc_paths.py::IS-P1c`.

#### IS-P5 A hook can mutate admitted paths
- **Contradicts**: D5 (veto/narrow only), P4 in 03 section 12. **Clause**: 03 section 8 "`ctx` ... `ctx.paths` canonical".
- **Exploit**: a hook that normalises `ctx.paths["path"]` (a plausible "helper") swaps in a deny-listed `.env`; the
  handler reads the mutated value, after the deny pass. Hooks written by AI copy-edit `ctx` freely.
- **Fix**: > Hooks receive a frozen view: `ctx.paths`, `ctx.argv`, `ctx.env`, `ctx.cwd` are `MappingProxyType`/tuples; the
  > handler is given the *admission snapshot* taken before hooks ran, and the pipeline compares the snapshot hash after the hooks and denies
  > (`policy.hook_error`) on any difference.
- **PoC**: `poc_policy.py::IS-P5`.

#### IS-P5b Hook returning a truthy non-`Decision` value is treated as allow
- **Clause**: 03 section 8 "returns an unknown type denies" (text correct, prototype and a likely implementation wrong).
- **Exploit**: `return "denied"`, `return 0`, `return {"allow": False}` all pass; `return Deny` (the class, not an instance) passes.
- **Fix**: > The pipeline accepts exactly `None`, `True`, `False`, `Deny` instances and `Narrow` instances (`type(x) is`
  > checks; no truthiness). Anything else denies with `policy.hook_error`. Add the parametrised test list from the PoC to 10 section 5.
- **PoC**: `poc_policy.py::IS-P5b`.

#### IS-P8 Negative or oversized caller limits defeat policy limits
- **Contradicts**: D9. **Clause**: 03 section 9 "effective limit = min", requested limits not validated.
- **Exploit**: `max_entries=-1` in the request produced 5 entries under a policy cap of 2 (`min(2, -1)` then "negative = unlimited").
- **Fix**: > Caller-supplied limit-like arguments are schema-typed `integer >= 1` (or `>= 0` where zero is meaningful);
  > `bool`, floats, strings are `args.type`. Effective limit = `min` over positive values only; a missing policy limit
  > is the op default, never "infinite".
- **PoC**: `poc_policy.py::IS-P8`.

#### IS-F4 FIFO inside a scope blocks a worker thread forever
- **Clause**: 03 section 6.2 "reject non-regular files for write" (read side silent).
- **Exploit**: a caller who can create a FIFO (via an allowed command or a prior upload tool) then asks for
  `files.download`; `open(O_RDONLY)` blocks. 64 requests exhaust `max_connections`.
- **Fix**: > Reads also reject non-regular files: `open_beneath` opens with `O_NONBLOCK|O_NOFOLLOW`, `fstat` must be
  > `S_ISREG` (directories only for list), then `O_NONBLOCK` is cleared. Devices, sockets and FIFOs are
  > `policy.not_regular_file` in every effect.
- **PoC**: `poc_paths.py::IS-F4`.

#### IS-F5 Hard link bypasses a deny glob
- **Clause**: 03 section 6.2 "Known limits (documented): hard links ... created inside the root by a different actor".
- **Exploit**: a legitimately allowed `cp -l` / `ln` (or any prior command) creates `notes.txt` as a hard link to `.env`;
  the deny glob `**/.env` does not match `notes.txt`. This is not "a different actor" - it is the same principal using
  an allowed command.
- **Fix**: > `open_beneath` refuses a regular file with `st_nlink > 1` when the scope has any `deny` entries or
  > `readonly=False`, unless `PathScope(allow_hardlinks=True)`; `check-config` mentions the cost. Remove hard links from
  > the "known limits" list.
- **PoC**: `poc_paths.py::IS-F5`.

#### IS-A7 `principals=["*"]` ("any authenticated") matches the anonymous principal
- **Contradicts**: D4. **Clause**: 03 section 3.1 "`*` (any authenticated)" versus "An empty list means every principal including anonymous".
- **Exploit**: in the prototype `*` admits anonymous; an author relying on "any authenticated" gets "anyone", especially
  in open mode where anonymous is admin anyway.
- **Fix**: > `principals=["*"]` matches principals with `authenticated=True` only; `principals=[]` and the literal
  > `anonymous` match the anonymous principal. Open mode creates a principal with `authenticated=False`.
- **PoC**: `poc_policy.py::IS-A7`.

#### IS-C2c `env_pass` reads the live server environment
- **Contradicts**: D8. **Clause**: 03 section 7.2 "`env_pass` ... taken from the server's environment".
- **Exploit**: combined with a mutable `os.environ` (IS-C2), a later `system.env.set` value flows into every scoped command.
- **Fix**: > `env_pass` values are snapshotted at startup (and on `core.reload`); `os.environ` is not consulted per request.
- **PoC**: `poc_commands.py::IS-C2c`.

#### IS-C5 Escape-capable-executable lint misses common executables
- **Clause**: 03 section 7.3 list ("sh bash python3 env find xargs awk perl ruby node git vim less man tar sed busybox docker sudo su script nice nohup timeout strace time").
- **Exploit**: lint is silent for `pytest -q {path}` (08 section 4.2 ships it; conftest.py/plugins execute code; paired with a writable
  workspace it is arbitrary code execution), `npm run ...`, `curl -o {path} ...` (write + net), `cp`, `tee`, `go test`,
  `make`, `cargo`, `pip`, `ssh`, `rsync`, `zip`, `7z`, `gdb`, `jq` (`@sh`-free but reads), `openssl`, `ssh-keygen`.
- **Fix**: > The lint classifies executables into `exec-capable` (error with `...` or glob args), `exec-via-project-file`
  > (`pytest make npm npx yarn pnpm go cargo mvn gradle tox nox pip uv poetry` - **warning escalated to an error** when any
  > allow statement can write under the command's cwd root), `writer` (`cp mv tee dd curl wget rsync install ln
  > zip unzip tar`) and `network` (`curl wget ssh scp nc socat`). Shipped examples (08 section 4.2) are changed to pin file names
  > (`pytest -q tests/test_grade.py`) and the example workspace is read-only for the grader principal.
- **PoC**: `poc_commands.py::IS-C5`.

#### IS-C7 `CommandScope.readonly`/cwd read-only has no effect on tokens
- **Clause**: 03 section 7 (`{path}` canonicalised through cwd PathScope) vs 03 section 6 `readonly` ("refuse write/delete effects through this statement").
- **Exploit**: `{path}` carries no effect; `rm {path}` under a `readonly=True` cwd scope was admitted. The author's
  mental model is "this principal cannot modify the workspace".
- **Fix**: > `{path}` tokens are checked with the `read` effect, `{path:w}` with `write`, `{path:rw}`; a
  > command allow pattern whose executable is not in the read-only utility list (`cat ls head tail wc stat file grep`) may only use
  > `{path}` under a scope with `readonly=False` (`check-config` error otherwise). Say plainly in 03 section 7.3: a command
  > scope's `readonly` is **not** a sandbox; only `exec_dirs` + pinned argv constrain behaviour.
- **PoC**: `poc_commands.py::IS-C7`.

#### IS-U1b `block_private` misses CGNAT and the Alibaba metadata address
- **Clause**: 04 section 9 "literal loopback/link-local/metadata addresses".
- **Exploit**: `100.100.100.200` (Alibaba Cloud metadata, the target environment), `100.64.0.0/10`, RFC1918, `0.0.0.0`, IPv4-mapped IPv6
  and decimal/hex/octal IP encodings reach internal services.
- **Fix**: > `block_private` rejects any literal or resolved address for which `ipaddress` reports `is_private`,
  > `is_loopback`, `is_link_local`, `is_multicast`, `is_reserved`, `is_unspecified`, or in `100.64.0.0/10`, `169.254.0.0/16`,
  > `100.100.100.200/32`, `fd00::/8`, `::ffff:0:0/96` (checked after unmapping). Numeric hosts in non-dotted-quad form
  > are rejected. Resolution is performed once and the connection is pinned to the checked address by the server-run
  > fetchers; for Chromium (`browser.navigate`) the limit is documented and `browser` requires platform egress control.
- **PoC**: `poc_misc.py::IS-U1b`.

#### IS-S1 LLM credentials are readable by the agent that uses them
- **Contradicts**: D15 (secrets never in argv/logs; intention). **Clause**: 05 section 7 ("env or stdin only") and section 10.7 ("known secret values scrubbed from journal text").
- **Exploit**: the CLI runs with `OPENAI_API_KEY` in its environment; the model (prompt-injected by repo content)
  runs `env`, base64-encodes the value, and exfiltrates it. Redaction by exact-match scrubbing fails on transformed values.
- **Fix**: > Credentials given to an agent child are scoped: prefer a per-session short-lived key minted by the
  > configured gateway (`llm.session_key_url`) or a server-side loopback proxy (`llm.proxy: true`) that injects the real key and
  > enforces `models`/`max_turns`, so the child only holds a revocable local token. When the real key must be in the
  > env, `doctor` and `explain` print "key is exposed to agent-executed code" for that adapter.
- **PoC**: design-only.

#### IS-L2 Lazy install is triggered by `sessions.create` and bypasses `deny(install)`
- **Contradicts**: D6, D18. **Clause**: 02 section 6 step 8 "lazy-install `ensure` for declared requirements"; 05 section 10.5 "`agents.<a>.install` is an explicit
  `admin`-effect op".
- **Exploit**: an operator denies `agents.codex.install` to keep the image immutable; any principal with
  `agents.codex.sessions.create` still triggers an install on first use (disk fill, egress, long-running holds a request thread, and a
  version the operator never reviewed).
- **Fix**: > The pipeline's `ensure` step consults `install.mode` **and** the effective policy for
  > `agents.<a>.install` for the *principal*: an implicit install happens only if that principal could call the install op
  > (`allow` present, no `deny`), otherwise `424 install.required`. Implicit installs are rate-limited globally
  > (1 concurrent, `install.max_per_hour`), count towards `max_connections` as long-running, and are audited with the
  > triggering principal.
- **PoC**: design-only.

#### IS-L3 Tool resolver trusts a mutable environment and PATH
- **Contradicts**: D18. **Clause**: 06 section 5: "explicit `EBX_TOOL_<NAME>` path > `<tools>/bin` > PATH (only when `install.use_path=true`, default **true**)".
- **Exploit**: `EBX_TOOL_*` can be set via `system.env.set` (IS-C2) or inherited; a user-writable directory early on PATH
  satisfies "`--version` passes"; `use_path` default true means a planted `codex` in `~/.local/bin` is accepted with only a version string check, which any script can fake.
- **Fix**: > `EBX_TOOL_<NAME>` and `EBX_TOOLS_DIR` are read once at startup from the *process* environment and are
  > refused unless the target is owned by root or the server uid, not group/other writable, and every parent
  > directory likewise; paths from `PATH` are used only if they satisfy the same ownership rule. `use_path` defaults to
  > `false` when `install.mode` is `lazy`, to `true` only in `build`/`off` mode. The `verify` check compares a digest
  > recorded at `prepare` time, not `--version` output.
- **PoC**: design-only (the env half is IS-C2b / IS-C2).

#### IS-L4 `hosts` allowlist cannot be enforced for `npm ci` and Playwright
- **Contradicts**: D18. **Clause**: 06 section 6 step 5 ("redirects must stay within `hosts`") versus step 6 ("`npm ci` is the only step that may reach the registry"); 06 section 3 `playwright-browser` row.
- **Exploit**: `package-lock.json` `resolved` URLs may point to any host; npm follows them (integrity then protects the
  bytes, but a transitive `resolved` to an attacker host still leaks the request and works as a tracking channel); `playwright install` downloads from a CDN with revision pins, not content hashes
  controlled by the project; `.npmrc` in the staging `HOME` is attacker-free but `npm_config_registry` from "mirrors" is
  trusted configuration.
- **Fix**: > `lock` validates that every `resolved` URL host is in `hosts` and every entry has `integrity`
  > (`install.manifest_invalid` otherwise); `npm ci` runs with `--ignore-scripts --registry=<manifest registry> --no-fund`
  > and `npm_config_replace_registry_host=never`. For `playwright-browser`, `lock` records the SHA-256 of each downloaded archive
  > (`PLAYWRIGHT_DOWNLOAD_HOST` pointed at the manifest host) and the installer verifies it before use; unrecorded =
  > `install.manifest_invalid`.
- **PoC**: design-only.

#### IS-G2 `EBX_SERVER_READONLY=1` only constrains ops tagged `write`
- **Contradicts**: D11 (restrict-only layers must restrict). **Clause**: 03 section 10 layer 4.
- **Exploit**: an operator sets READONLY on a hardened image. `commands.run` (effects `exec`), `agents.*.sessions.create` (exec) and `process.start`
  still mutate the filesystem.
- **Fix**: > `EBX_SERVER_READONLY=1` removes every op whose effects include `write`, `delete`, `exec` or `admin`, and every
  > `PathScope` becomes `readonly=True`. Ops with effects `net` only (read) are not affected. `explain` prints the removed
  > ops.
- **PoC**: design-only.

#### IS-T1 Token in the URL for WebSocket and SSE
- **Clause**: 03 section 5 lists headers only; the in-flight `routes_pty.py` builds a `ws_url` containing `&token=` and 05 section 5 SSE resume `?after=`.
- **Exploit**: query strings land in proxy logs, browser history and `Referer`; the audit log in the in-flight code records request paths.
- **Fix**: > Tokens are never accepted in the query string. WebSocket clients authenticate with the
  > `Sec-WebSocket-Protocol: ebx.token.<one-time ticket>` subprotocol or a first message, where the ticket is a
  > 30 s single-use value minted by an authenticated `POST /terminal/{id}/ticket`. Audit and access logs record `path`
  > without the query string, and redact the `Authorization`, `X-Access-Token`, `Cookie`, `Sec-WebSocket-Protocol` headers.
- **PoC**: design-only (spot check in the in-flight code).

### Low

#### IS-A5 Unknown op and unmounted op have different bodies (existence oracle)
- **Contradicts**: D4 ("byte-identical to unknown"). **Clause**: 03 section 11 table gives `op.unknown` (with suggestions) and `op.not_enabled` different codes.
- **Exploit**: an authenticated principal enumerates the op catalog through the `code` and the suggestions.
- **Fix**: > For authenticated principals, an op that does not exist **or** is not granted both return
  > `op.not_enabled`; `op.unknown` with suggestions is only returned to principals that can call `core.capabilities` for the
  > `admin` role, or when `server.verbose_errors=true` (dev).
- **PoC**: `poc_policy.py::IS-A5`.

#### IS-A8 `//x/shell` is dispatched as `/shell`
- **Clause**: 02 section 6 step 1-2: no request-target normalisation rule.
- **Exploit**: `urlparse` treats `//x/shell` as authority `x`, path `/shell`; an upstream path-prefix ACL sees `//x/shell`.
- **Fix**: > The request target is split manually (`path = target.split("?", 1)[0]`); a path not beginning with a single `/`,
  > containing `//`, `/./`, `/../`, `%2f`, `%2e` or NUL is `400 request.bad_target` before routing.
- **PoC**: `poc_transport.py::IS-A8`.

#### IS-L5 `.installed.json` marker is trusted without re-verification
- **Clause**: 06 section 6 step 2 "marker present, manifest sha256 equal, `verify` passes -> ready".
- **Fix**: > For tool dirs that are not root-owned, `ready` additionally requires the recorded tree digest of the `bin`
  > target (size + sha256, cached per process) to match; `doctor --verify` recomputes the whole tree.
- **PoC**: design-only.

#### IS-I1 Idempotency-Key reuse with a different body returns the first result
- **Clause**: 05 section 5 "returns the original result for 24 h" and section 10.6 namespacing by principal.
- **Fix**: > The key table stores `(principal, key) -> (sha256(canonical request), response)`; a key replayed with a
  > different body is `409 agents.idempotency_conflict`. Keys are ≤ 128 printable ASCII characters; the table is capped
  > (default 10000) with LRU eviction and is not persisted across principals.
- **PoC**: design-only.

#### IS-J1 Session identifiers are 48 bits
- **Clause**: the in-flight `uuid4().hex[:12]` for session/process ids; design silent.
- **Fix**: > Session, process, terminal and turn ids are `secrets.token_urlsafe(16)`; ownership check precedes any lookup
  > result, so wrong id and foreign id are byte-identical (already specified in 05 section 10.6).
- **PoC**: design-only.

---

## 4. Attacks tried that held up

Each has an executable check in `spikes/independent-security/poc_held.py` (`HELD-*`) that fails the runner if it regresses.

| Check | What was tried | Why it holds |
|-------|----------------|--------------|
| HELD-paths | `..`, double slash, `a.txt/../../x`, NUL, 5000-char path, `pub/../pub/../secret` | anchoring then lexical normalisation (03 section 6.1) |
| HELD-symlinks | directory symlink out of root, two-level symlink chains | `realpath` + `within` rule |
| HELD-read-race | swap a parent for a symlink between admission and open | `open_beneath` `O_NOFOLLOW` walk -> `policy.path_changed` |
| HELD-write-race | final component swapped for a symlink to a victim, opened with `O_TRUNC` requested; check victim not truncated | no `O_TRUNC` at open, `ftruncate` after `fstat` |
| HELD-typed-path | `ls {path}` with `--help`, `-R`, `../..`, a symlink out of the root, `/etc`, extra or missing args | `{path}` rejects leading `-`, canonicalises, replaces argv |
| HELD-exec-dir | `/usr/bin/../../x`, `./ls`, `../ls`, `/tmp/ls`, `ls/../../x` as argv[0] | executable resolved only against `exec_dirs` |
| HELD-env-shell | `LD_PRELOAD`, `PYTHONPATH`, `NODE_OPTIONS`, `BASH_ENV`, `GIT_SSH_COMMAND`, `IFS`, unlisted names via `env`; `shell=True` | default `env_deny` + `env_set` allowlist + `policy.shell_not_allowed` |
| HELD-explicit-deny | `allow` of `agents.*`, `agents.**`, `group:agents`, `effect:admin`, `*`, `core.*`, `effect:net` never mounts `agents.codex.install` or `core.reload`; a principal-scoped deny overrides an allow | explicit-only on the allow side (D6), deny-overrides (D5) |
| HELD-auth-size | unauthenticated unknown routes get 401; oversized `Content-Length` rejected before reading | pipeline order (D10), size cap |
| HELD-hook-limits | hook exception fails closed; `Narrow` can only lower limits | min semantics, fail-closed |
| HELD-C6b | the fix for IS-C6: `PR_SET_DUMPABLE=0` blocks a scrubbed same-uid child from `/proc/<ppid>/environ` | kernel semantics, verified on this kernel |

Also reviewed without finding a defect in the *design text* (the spec says the right thing):
cross-principal session and journal reads through the API (D17, 05 section 10.6; the file-level leak is IS-L1), `Idempotency-Key`
namespacing, constant-time token comparison, generic 401 bodies, `llm_override` default off and the caller `base_url` ban, `allow_scripts=false`
and `npm ci --ignore-scripts`, mandatory sha256 and no TOFU, safe extractor (zip-slip, absolute paths, links), digest verified before
extraction, atomic publish via rename, restrict-only layers 4-5 (a lower layer cannot widen: `allow` in 4-5 is a startup error),
`core.reload` explicit-only, hooks fail closed on exception/timeout, legacy rollback switch staying a documented, loud opt-in.

## 5. Notes on areas not exercised

* The agents runtime and lazy installer have no prototype; findings there are reading-based (design-only). A prototype
  of the installer's safe extractor and the state-dir ownership check would turn IS-L1/IS-L5 into executable checks.
* Archive/zip-slip for `files.archive`/`extract` is covered by the design (05/06 safe extractor; 04 archive) but not by a PoC;
  the same `*at`-only rule from IS-F2 must apply to extraction (hence the explicit mention there).
* The in-flight (v1 plus WIP) code could not be imported as a whole while other workers edit it, so PoCs target the
  prototype; IS-C2 and IS-T1 were cross-checked by reading the in-flight handlers only.

## 6. Prioritised action list

1. **IS-A1**: fail closed on missing token secrets (03 section 5).
2. **IS-C2, IS-C2b, IS-L3, IS-C2c**: explicit-only set widened, `system.env.set` writes an overlay not `os.environ`, `ENV_NEVER` list, resolver trust.
3. **IS-G1**: agent session creation is an exec-effect op, scope required, enforcement probed, default `read-only`.
4. **IS-P1, IS-P1b, IS-P1c**: scopes are mandatory per declared parameter; cwd defaults to scope root.
5. **IS-P2, IS-P2b, IS-P3, IS-P4**: deny parity (canonical, single `argv`, descendants, explicit-only on deny).
6. **IS-F1, IS-C6, IS-L1**: non-removable system deny list, dumpable=0, safe default state and tools directories.
7. **IS-A2, IS-A3, IS-T1**: Content-Type/Origin/Host rules, timeouts, unauthenticated pool, no token in URLs.
8. **IS-C1, IS-F2, IS-U1, IS-P9**: glob traversal, `*at` mutation, strict URL parser, linear-time globs.
9. Medium: IS-P5/P5b/P8, IS-F4/F5, IS-A7, IS-C5/C7, IS-U1b, IS-S1, IS-L2/L4, IS-G2.
10. Low: IS-A5, IS-A8, IS-L5, IS-I1, IS-J1.

Verification gate: add `spikes/independent-security/run_all.py --strict` to the design CI so each fix flips its
check from VULNERABLE to HELD; once all are fixed, rename the `IS-*` checks to `HELD-*`.
