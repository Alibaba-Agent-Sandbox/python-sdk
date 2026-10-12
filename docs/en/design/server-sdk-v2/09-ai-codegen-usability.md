# 09 - Usability for AI coding agents (and for humans in a hurry)

> Part of [Server SDK v2](README.md). Rule R7. The reference card in section 3 is **normative text**: it is
> what the "AI consumer" simulations in the review rounds were allowed to read, and it becomes
> `llms.txt`/`SKILL.md` content for `server-sdk` (see section 6).
> **v2.1**: the card was rewritten against the spike's real facade (every imported name exists, every preset has one `root=` keyword, lines wrapped at 100 columns), the examples
> that were wrong for the real `openai` package were fixed, and the eight sample template files of the UX review are executable under `spikes/templates/`
> (`t1`..`t8`, plus `card_imports.py`). Findings: B-1..B-22, N-1..N-8.

## 1. What goes wrong when an AI writes server configuration

Observed or predictable failure modes (each one is addressed by a design feature):

| Failure mode | Feature that prevents or exposes it |
|--------------|-------------------------------------|
| Hallucinated or misspelt IDs (`file.download`, `files_get`) | IDs are attributes (`ops.files.download` raises `AttributeError` at import in the generated `.pyi`/IDE; strings are validated: `check-config` and `Policy.allow` error with `did you mean`) |
| Over-broad grants (`allow("*")`, root `/`, `shell=True`) | lint warnings that become errors under `--strict`; presets as the first resort; `describe --effective` shows what is mounted |
| Confusing deny lists with security | card rule "allowlist first", lints for escape-capable executables, `{path}` typed tokens |
| Raw path arguments in custom handlers | `paths=` declaration + `ctx.paths`; lint for undeclared path-like params; `ctx.open` |
| "Where do I put the config?" (5 ways) | one canonical answer per situation (section 3, "Which surface?") |
| Unknown HTTP route/method guessing | RPC form `POST /ops/{id}` always works; OpenAPI/`describe` give bindings; client generated |
| Not knowing whether a policy actually denies | `explain` and `core.check` run offline/dry; example attacks in docs run in CI |
| Installing agent CLIs in Dockerfile with `npm -g` | `agents: [codex]` + lazy install; `prepare` for build-time; the card says so |
| Misreading 404 vs 403 | one sentence in the card + error bodies with `code` and hints |

Design rules that follow: **one obvious way**, **strings are validated**, **errors carry a fix**, **everything is discoverable offline**, **defaults deny**,
**examples are executable** (tested in CI).

## 2. Features, in the order an AI would use them

1. `from easy_sandbox.server import ...` exposes every user-facing name (no deep imports needed). `__all__` is the documented list.
2. `ops` attribute tree + generated `_ops.pyi` -> completion and static checking (`pyright` flags `ops.files.dowload`).
3. `presets.*` cover the common shapes; `Policy` composes with `+`; `.without()` removes.
4. `easy-sandbox-server describe` / `describe --effective --config F` / `explain` / `check-config --strict` / `doctor`.
5. Errors: every `ValueError` raised by the config layer has the form `<what is wrong> (<where>); <how to fix>; see: <doc id>` and, for names, close matches.
6. Executable cookbook: `docs/en/guide/server-cookbook.md` (generated from `tests/cookbook/*.py`; each recipe is a test).
7. Machine-readable surface: `operations.json`, `openapi.json`, `llms.txt`, and the reference card.

## 3. The reference card

> Everything below is the entire documentation the AI-consumer simulations used. It must stay under ~200 lines and 100 columns (147 lines today; B-22).
> It is executable: `spikes/templates/card_imports.py` parses the `from easy_sandbox.server import (...)` block and the preset list from this card and fails if a name is missing from the facade
> or a line exceeds 100 columns; `spikes/templates/t1..t8` run the eight sample template files of the UX review end to end (Python and YAML flavours), against the real HTTP listener and,
> for the agents, the real `openai` package (`spikes/agents_sdk_check.py`).

```text
EASY SANDBOX SERVER - REFERENCE CARD (v2.1)

CONCEPTS
  operation (op) = one capability with a dotted ID: files.download, commands.run, agents.codex.run
  ops            = attribute tree of IDs: ops.files.download == "files.download"; ops.custom["odd"]
  policy         = list of allow()/deny() rules. Nothing is enabled unless an allow rule covers
                   it (not mounted -> 404 op.not_enabled; an unknown id gives the same 404).
  deny beats allow, for EVERY selector (even explicit-only ops). A failing check denies.
  principal      = the caller (token): id, roles, claims. Rules can target principals.

WHICH SURFACE?
  A safe preset            -> SandboxServer(presets.readonly(root="/data"))
  Fine-grained, Python     -> Policy().allow(...).deny(...)  ->  SandboxServer(policy)
  Fine-grained, template   -> template.yaml  server: {rules: [...]}   (same fields as the kwargs)
  Your own capability      -> @op("custom.name", effects="exec", paths=("p",)) | server: {custom:}
  Coding agents (OpenAI)   -> server: {preset: agent_host, root: /workspace, agents: [codex]}

PYTHON  (every name below is importable from easy_sandbox.server)
  from easy_sandbox.server import (start, SandboxServer, Policy, ops, op, presets, PathScope,
      CommandScope, UrlScope, AgentScope, Limits, Deny, Narrow, Principal, Registry, configure,
      PolicyError, from_config)

  Policy().allow(*selectors, principals=(), paths=None, commands=None, urls=None, agents=None,
                 limits=None, authorize=None, name="")
  Policy().deny(*selectors, principals=(), paths=None, commands=None, reason="", name="")
  Policy().without(*selectors)       # deny with a reason. deny(paths=) hits a path or a parent
  policy_a + policy_b                # union; deny still wins
  SandboxServer(policy, authenticate=None, tokens=None, registry=None, *, verbose=False,
                state_dir=None, agents_default=None, trusted_proxies=(), strict=True)
  start(policy=None, *, config=None, port=9000, host="127.0.0.1", allow_open=False,
        allowed_hosts=(), allowed_origins=())      # config = dict | path to JSON/YAML
  from_config(dict) -> SandboxServer               # unknown keys are errors with did-you-mean
  server.call("files.download", principal=None, path="/tmp/a")   # (status, body); same pipeline
  server.explain(op, args, principal)  # dry-run decision trace      server.check() -> lint messages
  Register @op functions BEFORE constructing the server (the registry freezes).
  A typo in a selector raises PolicyError at construction (strict=True). core.health is always
  mounted unless you deny it.

  selectors: "files.download" | ops.files.download | "files.*" (one level) | "agents.**" (any
             depth) | "group:file_ops" | "effect:read" | "*" (avoid)
  effects  : read write delete exec net admin.  @op without effects= means admin (explicit-only).
  EXPLICIT-ONLY ops are mounted only by naming their exact id (wildcards/groups/effects/presets
  never reach them) but every deny selector DOES reach them: system.env.set core.reload
  terminal.create process.signal agents.<a>.install agents.<a>.sessions.create (+ admin ops).

  SCOPES ARE REQUIRED. An allow of an op with a path/command/url/agent parameter without its scope
  is 403 policy.scope_required and a check() error. allow(ops.commands.run) alone is refused.
  paths    PathScope(*roots, deny=("**/.env",), readonly=False, symlinks="within"|"deny",
                     max_bytes="10MB")   roots are directories (never "/" and no globs);
           "/data/{principal.id}" templates a per-caller root. Relative paths anchor at the first
           root; ".." and symlink escapes, /proc /sys /dev and the server's state dir are denied.
           PathScope.anywhere(unsafe=True) exists and is a lint error.
  commands CommandScope(allow=(patterns), deny=(patterns), shell=False, cwd="/workspace",
                        env_pass=("PATH","LANG"), env_set=(), timeout=60, max_output_bytes="1MB")
           pattern = argv template: literal/glob = one argument; ... = any number of arguments;
           {path} = one jailed path argument; {int} {word}.  cwd is covered by the scope; an
           omitted cwd is the scope root.  command XOR argv (never both).
           RULES: allowlist first; pin arguments ("python3 /workspace/grade.py"). NEVER allow
           "python3 ...", "sh ...", "env ...", "find ...", "git ..." with free arguments.
           SAFEST: a named op with a fixed argv. CommandScope.unrestricted(unsafe=True): lint error.
  urls     UrlScope(hosts=("*.example.com",), schemes=("https",), ports=(), paths=("/**",),
                    block_private=True)   canonical URL is checked, not the raw string.
  agents   AgentScope(workdir=PathScope("/workspace"), permissions="read-only"|"workspace-write"|
                      "full", commands=(), models=(), max_turns=None, unconfined_ok=False)
           REQUIRED on every allow of agents.*.run / sessions.create / sessions.send_event.
           Agents are NOT confined by other path/command scopes; "full" needs unconfined_ok=True.
  limits   Limits(max_bytes, max_entries, timeout, max_output_bytes, rate="10/min", concurrency=2,
                  cpu_seconds, memory, processes)   sizes "10MB" "10MiB"; durations "90s" "5m";
           effective limit = the minimum of everything that applies.
  principals=["id:grader", "role:viewer", "*"]   "*" = any AUTHENTICATED caller
  env      system.env.set only changes a server overlay and refuses PATH/LD_*/EBX_*; it is never
           in a preset or group.  If an allowed command runs a file, do not let callers write it.
  hook     @policy.authorize
           def f(ctx): return None | True | False | Deny("why", code="policy.x") | Narrow(limits=..)
           ctx is read-only (ctx.op, ctx.principal, ctx.paths, ctx.argv, ctx.args). Any other
           return value or an exception denies.

  presets (one keyword root=; paths= and workspace= are aliases; there is no default root):
    minimal()  files_readonly(root)  readonly(root)  download_only(root, deny=, max_bytes=)
    commands_only(root, allow=)  workspace_jail(root, readonly=False, commands=None)
    ci_runner(root, commands=(), timeout=600, writable=False)   # read-only workspace by default
    agent_host(root, agents=("codex",), permissions="read-only")
    full_access(root, commands, unsafe=False)   legacy_compat()  # migration only; loud lints
    combine with +.  presets.legacy_compat + legacy_diff(server) = what a v1 server exposed.

  @op("grader.run", effects="exec", paths=("submission",), http="POST /grade", summary="...")
  def run(ctx, submission: str, timeout: int = 60) -> dict:   # annotations become the schema
      path = ctx.paths["submission"]                  # ALWAYS ctx.paths, never the raw argument
      r = ctx.run(["python3", "/workspace/grade.py", path], timeout=timeout)   # no shell
      return {"exit_code": r.exit_code}
  Reserved namespaces: core files commands process terminal system devtools browser agents ext.

AUTH
  Tokens come from SandboxServer(tokens={secret: Principal(id, roles)}) or server.json
  auth.tokens [{id, roles, token_env: NAME}]. A token_env that is unset/empty, a secret shorter
  than 16 chars, an inline "token" value, or the id "anonymous" is a startup ERROR.
  No auth at all = open mode: refused on a non-loopback host and when exec/admin ops are mounted
  (start(..., allow_open=True) overrides; do not).
  Custom: authenticate(headers) -> Principal | None   headers = lower-cased dict; None -> 401.
  Credentials: Authorization: Bearer <t> (preferred) or X-Access-Token (legacy alias). Both with
  different values -> 401 auth.conflicting_credentials. Tokens in URLs are never accepted.

AGENTS  official openai SDK: OpenAI(base_url="http://HOST:9000/v1", api_key=TOKEN)
  client.beta.agents.create / .sessions.create / .sessions.events.create (202) / .stream ...
  Adapter selection: path /agents/<a>/v1 | header X-EBX-Adapter | model == adapter name |
  config agents.default | the only mounted adapter | else 400 agents.adapter_required.
  Real model names (gpt-5-codex, codex-mini) are passed to the CLI as the LLM model.
  Two gates: generic agents.sessions.create AND agents.<a>.sessions.create must both be allowed.
  ops per adapter: agents.<a>.run | .install | .sessions.create | .sessions.send_event
  adapters: codex claude_code (stable)  qwen_code cursor qoder (experimental, flagged in list)
  Allow one adapter:  Policy().allow("agents.codex.run", "agents.codex.sessions.create",
        "agents.codex.sessions.send_event", agents=AgentScope(workdir=PathScope("/workspace")))
  LLM key: llm: {base_url_env: X, api_key_env: Y} (names only). The agent CLI holds the key.
  Install: nothing until used (a slow install answers 202 + Retry-After); FC/base image: set
  install: {mode: build} and run `easy-sandbox-server prepare` in the image build.

YAML / template.yaml  server:   (same names as Python; unknown keys are errors)
  version: 1   preset: name | [names]   root: dir   enable: [selectors]   disable: [selectors]
  rules: [{allow|deny: [selectors], principals: [...], paths: {roots: [], deny: [], readonly: false,
           max_bytes: 10MB}, commands: {allow: [], deny: [], cwd: /workspace, timeout: 60s},
           limits: {rate: 60/min}, reason: "..."}]
  custom: {name: {argv: ["prog","{param}"], params: {param: {type: path|int|word|string|enum,
           root: /dir}}, cwd, timeout, effects: [exec]}}
  auth: {tokens: [{id, roles: [], token_env: NAME}]}   audit: {sink: stderr}
  install: {mode: lazy|build|offline|off}   agents: [codex]   load: [my_pkg.ops]

CLIENT  from easy_sandbox import ServerClient, ops   # same IDs, same tree, generated
  srv = sandbox.server ; await srv.files.list("/tmp") ; await srv.commands.run("ls")
  await srv.agents.codex.sessions.create(...) ; await srv.custom.grade(...)
  await srv.call(id, **kw)
  Errors E3100-E3111 (ServerAPIError, PolicyDeniedError, EndpointNotAvailableError, ...).

MIGRATING v1: SandboxServer(presets.legacy_compat()) keeps v1 exposure (system.env.set only with
  EBX_SERVER_LEGACY_ENV_SET=1). Any other policy unmounts custom.*/ext.* unless you allow them;
  `check-config --legacy-diff` lists what a policy drops.

CLI  easy-sandbox-server  serve | init | describe [--effective] | check-config [--strict] |
     explain --op ID --arg k=v [--principal ID] | prepare | doctor | gen-client | healthcheck
HTTP every op: POST /ops/<id> with a JSON body (Content-Type: application/json). GET /ops = what
     YOU may call. GET /capabilities = same + limits.
ERRORS JSON {error, type, code, op, request_id}. 404 op.not_enabled = not allowed for you / does not
     exist. 403 policy.* = allowed op, forbidden arguments. 401 auth.*  400 args.*  413/429 limit.*
     424/503/502 install.* (202 = install running). Messages say what to change.

DO   start from a preset; run check() / `check-config --strict`; test denials with explain/call.
DON'T allow "*"; use "/" as a root; enable shell; allow interpreters with "..."; read raw path
     args in handlers; put secrets in config files; run `npm -g` in Dockerfiles.
```

## 4. Error message catalog with fix hints (excerpt; implemented as data in `core/errors.py`)

| Code | Message template |
|------|------------------|
| `op.not_enabled` (also unknown ids) | `operation '{id}' is not enabled for this caller` (one body for both, D4; with `verbose=True` / `serve --explain-denials` and only among ops mounted for the caller: `did you mean {suggestions}?`; the *config* tooling says `allow it with Policy().allow(ops.x.y) or preset ...`) |
| `policy.scope_required` | `allow rule {n} mounts '{id}' without a {PathScope\|CommandScope\|UrlScope\|AgentScope}; add one (for example paths=PathScope("/data"))` |
| `auth.conflicting_credentials` | `Authorization and X-Access-Token differ; send one credential` |
| config: `config.auth_secret_missing` | `auth.tokens[{i}].token_env '{NAME}' is not set or empty; refusing to start` |
| config: unknown selector | `selector '{s}' matches no operation (rule {n}); did you mean '{x}'? list ids: easy-sandbox-server describe --ids` |
| config: allow root `/` | `PathScope('/') is refused (ValueError); use a narrower root, or PathScope.anywhere(unsafe=True) (a lint error) if intended` |
| config: escape-capable | `allow rule {n}: '{exe}' can execute arbitrary code with pattern '{p}'; pin all arguments or use server.custom / @op` |
| config: literal secret | `{path}: secrets must be environment references; use {key}_env: NAME` |
| `policy.path_not_allowed` / `policy.path_denied` | `path is not permitted by the policy (param '{p}')`; with `details.hint="allowed roots are listed in GET /capabilities"` for authenticated callers |
| `args.unknown` | `unknown argument(s) {names} for '{id}'; accepted: {accepted}` |
| `install.required` | `'{tool}' is not installed and installs are disabled (mode=build); run: easy-sandbox-server prepare --only {tool}` |

## 5. Anti-patterns detected by tooling (checklist for `check-config`)

`allow("*")` outside `full_access`; selectors matching nothing; shadowed statements; writable-script pairs; root `/`; `symlinks="follow"`; `shell=True`; escape-capable allow patterns; `{path}`
without cwd; undeclared path-like params in custom ops (static check at registration); effects omitted on custom ops (default `{"admin"}`, explicit-only, warns); open mode (refused on a non-loopback
listener and when exec ops are mounted); `config.scope_required`; principal selectors no token can produce; registered-but-unmounted custom ops; literal secrets; agents allowed together with file scopes without `permissions`; hooks doing blocking network calls (cannot detect, documented).

## 6. Documentation artifacts for AI consumers

* `server-sdk/llms.txt` and `SKILL.md`: the card (section 3) + links to `operations.json`, `openapi.json`.
* `AGENTS.md` (server-sdk): "do not add routes; add `@op`; declare `paths=`; add a contract case; regenerate with `make gen`".
* `docs/en/guide/server-policy.md` (+ zh): task-oriented recipes: download-only, readonly, per-principal limits, grader, agent host, hooks, audit, reload.
* `docs/en/reference/server-operations.md` (+ zh): generated op catalog (the tables of [04](04-builtin-modules.md)).
* Error-code reference gains E3100-E3111 and the server `code` strings (E9xxx is not used, 07 section 4).
* **Python entry points, stated once (v2.1, B-11, B-12).** `start(policy=None, *, config=None, port=9000, host="127.0.0.1", ...)`: `config` is a dict, a path to JSON (or YAML when PyYAML is importable) or a mapping produced by
  `from_config`; `policy=` is added to the config's policy (union; restrict-only layers still apply). Auth tokens, `llm:`, install mode and audit are reachable from Python via `SandboxServer(tokens=..., authenticate=...)` and
  `from_config`. `authenticate(headers: Mapping[str, str]) -> Principal | None`: header names are lower-cased, the callable never sees the body, `None` or an exception means 401, a returned `Principal` has `authenticated=True`.
  (The spike's `start()` returns `(server, httpd)` instead of blocking so tests can drive it; the shipped function blocks and `start(..., block=False)` returns the same pair.)
* **Spellings (B-13, N-5, N-7).** Preset names are accepted in both spellings (`download_only`, `download-only`); new code uses the underscore form and the dotted op id (underscore *aliases* such as `files_download_stream`
  exist for old configs only; `check-config` rewrites them). Environment variables for server settings use the `EBX_SERVER_*` prefix (`EBX_SERVER_INSTALL_MODE`, `EBX_SERVER_STATE_DIR`, ...); LLM endpoints are named in `llm:`
  by `*_env` names, whatever the template calls them.

## 7. AI-consumer simulation protocol

The simulation is run in every review round that touches the surface. Rules:

1. The consumer reads **only** the reference card (section 3) as it stands in that round - no other doc, no source.
2. It receives a task statement and writes the artefact (Python, YAML, or both) plus the *attack tests* it believes prove the requirement.
3. The artefact is executed against the reference harness ([spikes/](spikes/)) - the registry/policy/guards code that the design was validated with.
4. A scenario **passes** if (a) the artefact loads without edits, (b) permitted calls work, (c) every denied call is denied with the expected status/code,
   (d) `check-config`-equivalent lint reports no errors. A *finding* is logged for every edit the consumer would have needed, every misreading of the card,
   and every place the card was silent.
5. Scenarios (S1-S8): download-only `/tmp`; restricted shell for grading code; codex endpoint with custom auth; multi-agent host with per-principal access;
   per-caller limits on one op; custom op with path param and hook; read-only observer with audit; template.yaml equivalent of S1/S2.
   **(v2.1) Sample template files T1-T8** (from the UX review, `spikes/templates/`): T1 download-only, T2 git+pytest CI runner (YAML), T3 codex host with the `openai` SDK, T4 claude_code + qoder, T5 custom op with a hook,
   T6 read-only browser, T7 multi-tenant `{principal.id}` with `authenticate(headers)`, T8 v1 migration with `legacy_diff`. Run: `python3 spikes/templates/run_all.py`.
   The independent AI run (a model that reads only the card) stays a **periodic** non-blocking job in 0.3.0 (cut list, [10](10-implementation-plan.md) section 3.2); the scripts above are its oracle.
6. Because no independent AI subagents were available when this design was produced, the simulation was performed by the lead author **in a separate pass that
   deliberately re-read only the card**. This is weaker than an independent model run and is recorded as a known limitation; the scenario scripts are kept under
   `spikes/ai_consumer/` so an independent run can repeat them (work package WP-11).
