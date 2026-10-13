# 02 - Operation model

> Status: archive. Not the current specification.

> **Status: target design, not implemented.** The shipped server uses endpoint ids and one policy engine; see [README](README.md) section 1 for what exists and section 2 for what does not.

> Part of [Server SDK v2](README.md). Rule R1/R2/R5 of [01-principles.md](01-principles.md).
> **v2.1**: grammar widened to five segments, default effects `admin`, one 404 body, new pipeline order, `ops/` package renamed
> `builtin/`, legacy name mangling table. Changes are marked **(v2.1)**; see [README](README.md) section 4a.

## 1. Summary

Every capability of the server is an **operation** registered in one `Registry` under a dotted ID.
An operation is a Python callable plus metadata (`effects`, parameter schema derived from type
annotations, declared path/command parameters, limits, HTTP bindings, install requirements). The
registry is the single source for dispatch, policy, discovery, OpenAPI, generated clients and docs.

```python
from agent_sandbox.server import ops                  # attribute tree, IDs as attributes

ops.files.list              # -> files.list              (autocomplete via generated _ops.pyi)
ops.agents.codex.run        # -> agents.codex.run
ops.custom["format"]        # -> custom.format           (item access always works)
str(ops.files.list)         # 'files.list'
ops.files.list == "files.list"   # True; hashable; usable wherever a selector is expected
```

`ops` nodes are **not** `str` subclasses: a `str` subclass would shadow verbs that are `str` methods
(`ops.custom.format`, `.split`, `.index`, `.replace`, `.count` would return bound methods). The spike
found this bug in its first design (review round 1, F1.1); `OpRef` fixes it.

## 2. ID grammar and namespace rules

```
op_id   := segment ("." segment){1,4}      # (v2.1) was {1,3}; the official subagent routes need five segments
segment := [a-z][a-z0-9_]*          # lowercase, digits, underscore; no hyphen, no dot, no uppercase
```

* 2 to 5 segments **(v2.1)**: `agents.sessions.subagents.turns.list` is the longest ID. The **last segment is the verb** (`list`, `run`, `create`, `get`, `stream`), earlier
  segments are namespaces: `files.list`, `system.env.get`, `agents.codex.sessions.create`.
* An ID may **not** be a prefix of another ID (`system.env` cannot exist next to `system.env.get`):
  checked at registration, so `ops.system.env` is always a namespace and `ops.system.env.get` always a leaf.
* **The `ops` tree and the `ops/` package (v2.1, IF-03).** A package named `agent_sandbox.server.ops` next to the module attribute
  `ops` breaks the public tree as soon as `ops/files.py` is imported (the import system rebinds the attribute to the
  sub-module; demonstrated). Therefore the **built-in handler package is `agent_sandbox/server/builtin/`**
  (`builtin/files.py`, `builtin/commands.py`, ...). `agent_sandbox.server.ops` is **only** the `OpRef` tree defined in
  `core/refs.py` and re-exported by `__init__`; an import test (`tests/test_public_surface.py`) asserts
  `isinstance(agent_sandbox.server.ops, OpTree)` after importing every `builtin.*` module.
* Verbs are conventional: `list get create update delete run start stop stream read write download upload
  stat move search watch signal check describe install`. A lint warns about unknown verbs; it is not an error.
* **Reserved namespaces** (only the SDK registers here): `core files commands process terminal system
  devtools browser agents ext`. `custom` is the namespace for user-defined *commands* (legacy
  `CommandRegistry`); users may also create their own namespaces (`grader.run`) that are not reserved.
* Hyphenated or camel-case external names are *wire names*, never IDs: `claude-code` (CLI binary and OpenAI
  `model` string) is the adapter `claude_code`; `ops.agents.claude_code.run`.
* **Aliases.** An op may carry aliases (old IDs). The legacy underscore names used by the in-flight
  capability design (`files_list`, `shell`, `pty_create_session`) are aliases, resolved by
  `Registry.resolve(name)`; policy files written with an alias are rewritten to the canonical ID with a
  deprecation warning in `check-config`. Aliases are never shown as primary in discovery.
* **Typos (v2.1).** A call to an unknown id or to an op that is not mounted for the caller is **one** response:
  `404 op.not_enabled`, identical bytes (IS-A5, B-20, D4). Suggestions (`did you mean 'files.download'?`) are added **only** when
  the server runs with `verbose=True` (development; `serve --explain-denials`) and **only** among ops mounted for that principal.
  Policy selectors that match **no** registered op raise `PolicyError config.unknown_selector` with a did-you-mean **at
  construction** (`SandboxServer(..., strict=True)`, the default; B-2) and are a `check-config` error (a typo in `allow(...)`
  must not silently mount nothing, nor a typo in `deny(...)` silently deny nothing). `strict=False` downgrades this to a lint warning
  for tests that probe typos.
* **Name mangling for legacy commands (v2.1, IF-05).** `CommandRegistry` names may contain hyphens, dots, uppercase. The op id is
  `custom.` + the name lower-cased, every character outside `[a-z0-9_]` replaced by `_`, runs collapsed, a leading digit prefixed
  with `c_` (`Hello-World.v2` -> `custom.hello_world_v2`). Collisions get `_2`, `_3`. The original name is kept as the op's alias
  and `POST /commands/{name}` resolves by the **original** name through an alias table generated at registration, so the v1 route
  never changes. `GET /commands` lists the original names.

## 3. The `@op` decorator

```python
from agent_sandbox.server import op

@op("custom.grade",                       # id (required, validated)
    effects="exec",                       # str | tuple[str]; subset of read write delete exec net admin. OMITTED = admin (v2.1)
    summary="Grade a submission",         # default: first docstring line
    http="POST /grade",                   # str | list[str]; optional REST binding(s); RPC always exists
    paths=("workdir",),                   # params that are filesystem paths  -> path policy applies
    command=None,                         # the param that holds a command line/argv -> command policy
    limits=("timeout", "max_output_bytes"),   # limit keys this op honours (documented in catalog)
    group=None,                           # optional legacy group membership
    install=(),                           # install requirement names (manifests), see 06
    stream="none",                        # none | sse | ndjson | bytes | ws
    since="2.0",
    aliases=())
def grade(ctx, submission: str, workdir: str = "/workspace", timeout: int = 60) -> dict:
    """Grade a submission with the course grader."""
    ...
```

Rules:

* Handler signature is `(ctx, **params)`; `ctx` (first parameter named `ctx`) is optional. Handlers that do not
  declare `ctx` receive only their parameters (this is the legacy-extension shape).
* **Parameters** become the schema. Supported annotations: `str int float bool bytes`, `list[T]`,
  `dict[str, T]`, `T | None`, `Literal[...]`, `TypedDict`/dataclass (flattened to object schemas). No annotation
  means `str`. Defaults make a parameter optional. Unknown request keys are `400 args.unknown`
* **Declared path parameters** (`paths=`) are resolved and checked by the policy engine **before** the handler
  runs. `paths=` is a tuple of parameter names **or a dict `{param: root(s)}`** giving the parameter an *intrinsic* jail that always applies
  (intersected with the allow rule's own scope); declarative `server.custom:` commands compile to the dict form; the handler gets the canonical value in `ctx.paths[name]` and *must* use it (never the raw argument).
  **(v2.1, B-14, IS-P1b)** There is no "no scope, so no check" fallback: every allow statement that mounts an op with a declared path, command or
  url parameter must carry the matching scope, otherwise the call is `403 policy.scope_required` and `check-config` reports
  `error config.scope_required`. The only escapes are `PathScope.anywhere(unsafe=True)` and `CommandScope.unrestricted(unsafe=True)`
  (both lint errors, so `start()` refuses them unless `allow_lint_errors=True`). `ctx.paths[name]` is therefore always defined.
  The `cwd` parameter of command ops is covered by the `CommandScope`; an omitted `cwd` defaults to the scope root (else `/`), never the server cwd.
  Parameters that are lists of paths are supported (`files.archive.sources`). Per-parameter effect labels
  for multi-path ops: `paths={"src": "read+delete", "dst": "write"}` (`files.move`).
* **Declared command parameter** (`command=`) is parsed with `shlex` into `ctx.argv` and matched against the
  command scope; the handler must execute `ctx.argv`/`ctx.executable`/`ctx.env` (see 03 section 7).
* Other declarable parameter kinds: `urls=("url",)` (checked by a `UrlScope`: strict parser, canonical URL returned, 03 section 6.4), `languages=("language",)` (checked by a language allowlist). Both are used by `browser.navigate`/`devtools.code.run`.
* **Agent exec ops (v2.1, IS-G1).** `@op(..., agent_scope=True)` marks ops that start an agent CLI (`agents.<a>.run`,
  `agents.<a>.sessions.create`, `agents.<a>.sessions.send_event`, generic equivalents). They carry effects `exec` (plus `net`) and need an
  `AgentScope` in every allow statement (`policy.scope_required` otherwise).
* A custom op that has a parameter *named* like a path (`path file dir directory cwd root target dest src filename folder`; `cwd` is exempt when `command=` is declared) but does not
  declare it gets a lint warning: "parameter `file` looks like a path but is not declared in `paths=`;
  path scopes will not protect it".
* `effects` are declared by the op author and **not** guessed. They are what `effect:` selectors and
  presets use; wrong effects are a security bug (reviewed in [03](03-policy-and-permissions.md) section 11).
  **(v2.1, B-3)** An `@op` without `effects=` gets `("admin",)`, which makes it **explicit-only** (never matched by a wildcard, group
  or `effect:` selector on the allow side; see 03 section 3) and produces the lint `warn core.effects_undeclared`. This is the
  single default everywhere (the card, 04 section 10 and the spike agree: legacy custom commands are declared `exec`
  by the compatibility loader, which is an explicit declaration, not a default).
* Handlers return JSON-able values (dict/list/str/number/bool/None), a `Stream` (SSE/NDJSON generator wrapper), or
  `Bytes(data, content_type=..., filename=...)`; they raise `OpError(code, message, status=400, **details)` for
  expected failures. Any other exception is `500 server.internal` (message not leaked, logged with `request_id`).

### `ctx` (what a handler may rely on)

| Attribute | Meaning |
|-----------|---------|
| `ctx.op` | the `Operation`; it compares equal to its ID string (`ctx.op == "files.upload"`) and `str(ctx.op)` is the ID |
| `ctx.principal` | `Principal(id, roles, claims)` |
| `ctx.paths` | `{param: canonical_path}` for declared path params (policy-approved; always defined, see scope-required above) |
| `ctx.server`, `ctx.meta`, `ctx.env_overlay` | **(v2.1)** the server, request metadata (headers already normalised, `request_id`, peer) and the per-server environment overlay that `system.env.set` writes (never `os.environ`) |
| `ctx.scope` | the admitted `PathScope` (for `open_beneath`, `ctx.recheck(p)` on listings) |
| `ctx.argv`, `ctx.executable`, `ctx.env`, `ctx.cwd` | admitted command invocation (for command ops) |
| `ctx.limits` | effective `Limits` for this call (min over op default, rule, hook narrowing, operator layer) |
| `ctx.request_id`, `ctx.deadline` | tracing id; absolute deadline derived from `limits.timeout` |
| `ctx.open(path, mode)` | race-free open of an admitted path (no symlink following beneath the scope root) |
| `ctx.out` | stream writer for `stream != "none"` ops; enforces `max_bytes`/`max_output_bytes` |
| `ctx.log`, `ctx.audit(**extra)` | structured logging / extra audit fields |
| `ctx.run(argv, timeout=, cwd=)` | the sanctioned subprocess helper for custom ops: no shell, scrubbed env, rlimits and process-group handling from the same launcher as `commands.run`; returns `exit_code, stdout, stderr` |
| `ctx.host` | server-wide services (`kv`, `otel`, `installer`, `registry`) |

## 4. Registry

```python
class Registry:
    def op(...)                     # the decorator (same arguments as module-level `op`)
    def get(self, id) -> Operation
    def resolve(self, name) -> Operation | None      # id or alias
    def all(self) -> dict[str, Operation]
    def namespaces(self) -> dict[str, list[str]]
    def describe(self, *selectors, principal=None, policy=None) -> list[dict]
    def freeze(self)                # after start: registration raises RegistryFrozen
    def catalog(self) -> dict       # the operations.json document
    def openapi(self) -> dict
```

* `agent_sandbox.server.default_registry` holds the built-ins (registered by importing
  `agent_sandbox.server.builtin.*`; each module registers on import, exactly as today's `routes_*.py` do, but
  *lazily per namespace*: importing `ops.browser` happens only when the browser group is enabled, so
  Playwright is never imported otherwise).
* `server.call(op_id, principal=None, **args)` invokes an op in-process through the **same pipeline** (policy, limits, audit) and returns `(status, body)`; it is the supported way to unit-test
  a policy or a custom op without HTTP (the AI-consumer simulations use it). **(v2.1)** `server.explain(op, args, principal)` returns the
  dry-run decision trace (matched statements, scope verdicts, deny hits) without running the handler; the CLI form is
  `agent-sandbox-server explain --op OP --arg k=v [--principal ID]` (one spelling everywhere, N-4).
* The registry is **frozen when the server is constructed**: `@op` registrations made afterwards raise `RegistryFrozen` ("register ops before constructing the server"); the spike showed that
  silently ignoring late registrations looks like "my op is not mounted".
* `SandboxServer(registry=...)` accepts a custom registry; a copy-on-write child registry is created per
  server so tests and multiple servers in one process do not share custom ops.
* Third-party op packages are discovered through the entry-point group `agent_sandbox.server.ops` **only for
  modules named in the config** (`load: ["my_pkg.ops"]`); installed packages never register themselves
  into a running server just by being installed.

## 5. Bindings: how HTTP method and path are derived

An operation has **zero or more REST bindings** and always has the **RPC binding**:

| Binding | Shape | Source |
|---------|-------|--------|
| RPC (always) | `POST /ops/{id}`; JSON body = arguments; result = JSON (or the op's stream/bytes) | derived: nothing to configure |
| REST (optional) | `GET /files/list?path=...` etc. | `@op(http=...)`; every built-in lists its legacy binding in the table of [04](04-builtin-modules.md) |
| Wire alias (agents) | `/v1/agents/sessions/{id}/events` etc. | resolver functions in `agents/wire_*.py`, see [05](05-agents-api.md) |

Rules:

1. **Method/path is derived from the registry, never typed twice.** The only place a REST path is written is
   the `http=` of the `@op` that owns it. The route table, OpenAPI, the generated clients' `http` metadata and
   the tables in [04](04-builtin-modules.md) are generated. A CI drift test regenerates
   `catalog/operations.json`, `catalog/openapi.json`, `catalog/_ops.pyi` and `04-builtin-modules.md` tables
   and fails on diff.
2. **Argument placement for REST bindings** is mechanical: `{name}` path variables first; then for `GET`,
   `DELETE` all other parameters come from the query string (typed by the schema: `?recursive=true`,
   `?max_entries=100`, repeated keys for arrays); for `POST`, `PUT`, `PATCH` they come from a JSON body (the
   few binary-upload ops declare `stream="bytes"` and put non-body parameters in the query string).
3. **Conflict detection.** Registration builds a trie router. Two bindings that can match the same request
   (`GET /process/{pid}` vs `GET /process/list`) are resolved by *literal-before-variable* specificity;
   two bindings that are equally specific are a registration error. This replaces the registration-order
   linear scan (and its "register the literal route first" hazard) of the legacy `RouteTable`.
4. **Method not allowed** is `405` with an `Allow` header; unknown path `404 op.unknown_route`.
5. **Aliases at the routing layer (v2.1, C-3).** The agents wire formats route the generic OpenAI paths (`POST /v1/agents/sessions`, ...) to
   the generic ops (`agents.sessions.create`, ...), which then **also** require the adapter op `agents.<a>.sessions.create` (two-level gate, 05 section 4).
   The adapter `<a>` is chosen **explicitly**, in this order: (1) path prefix `/agents/<a>/v1/...` (unknown adapter: 404);
   (2) header `X-ABX-Adapter`; (3) a `model` string that **equals** an adapter name (`codex`, `claude_code`, `claude-code`);
   (4) config `agents.default`; (5) the only adapter mounted for the principal; (6) otherwise `400 agents.adapter_required`
   (or 404 `op.not_enabled` when none is mounted). Real model names (`gpt-5-codex`, `codex-mini`) never select an adapter and never 404: they pass
   through as the upstream LLM model. The resolver runs **after authentication** (never on unauthenticated bytes), so authorization
   always happens on concrete op IDs. A selected but unmounted adapter is `404 op.not_enabled` (adapters cannot be enumerated).
6. **Streaming and binary** are properties of the op: `stream` in `none | sse | ndjson | bytes | ws`.
   SSE frames use `event:`/`data:` with JSON data and `id:` for resumable streams. `ws` ops (terminal) are
   bound to the PTY WebSocket listener (port 9001) with the same authentication and the same pipeline
   (the *upgrade* is the policed call; the policy decision is cached for the socket's lifetime).

## 6. The request pipeline

The only code path from bytes to handler (`core/dispatch.py`). Steps 0-10 are normative (reordered in review round 4: authentication precedes alias resolution and every 404;
**v2.1** adds step 0 and the transport order from the independent security review); each has a test in [README](README.md).

```
 0  transport    (HTTP listener, before the pipeline; order is fixed)
                 a. socket header/body read timeout 3 s per read, bounded pre-auth connection pool (503 request.busy; core.health has a reserved slot)  [IS-A3, IF-19]
                 b. request target taken from the raw request line: any of `//`, `/./`, `/../`, `%2f`, `%2e`, `%5c`, backslash, NUL, control chars -> 400 request.bad_target  [IS-A8]
                 c. Host must be loopback or in allowed_hosts; Origin (when present) must be in allowed_origins -> 403 request.host_denied / request.origin_denied  [IS-A2]
 1  parse        method, path, query, headers; size cap via Content-Length BEFORE reading (413 limit.request_too_large); a body needs
                 `Content-Type: application/json` (415 request.bad_content_type) so a cross-origin "simple" POST cannot reach a handler;  body read
 2  route        trie lookup on method+path only -> candidate (op_id, args_from_path) | alias family | "no route"
 3  authenticate credentials -> Principal. `Authorization: Bearer` wins, `X-Access-Token` is the legacy alias; both present and different -> 401
                 auth.conflicting_credentials; failed attempts are rate limited per credential fingerprint (429 auth.rate_limited). 401 comes BEFORE any
                 404/405 so unauthenticated callers cannot probe routes (exception: core.health is anonymous by default)
 4  resolve      alias resolvers may now peek at the (size-capped) body; select the adapter (rule 5 above); "no route" or unknown id -> 404 op.not_enabled
 5  mounted?     any allow rule matching (principal, op)?  else 404 op.not_enabled   [no oracle: the same bytes as for an unknown id; the call is audited]
 6  args         JSON decode, validate against schema, coerce query types, `limit`-style args must be int >= 1   (400 args.*; `command` xor `argv` -> args.invalid)
 7  policy       deny rules (every selector, incl. explicit-only ops, canonical paths, relative args checked against every anchor) -> allow statements
                 (scope required; paths/commands/urls/agent scopes; limits) -> hooks (veto/narrow only)      (403 policy.* / 413 / 429)
 8  admit        concurrency/rate tokens, effective limits, deadline; lazy-install `ensure` for declared requirements (06) under the install policy
 9  run          handler(ctx, **args)    # ctx.paths/ctx.argv are the *canonical, admitted* values
10  audit+render audit record (always, including unmounted and denied calls), wire renderer (legacy | openai) -> response
```

Notes that matter:

* **Policy runs before any filesystem or process access** and *before* existence checks. A path outside the allowed roots answers
  `403 policy.path_not_allowed` (a deny-rule or system-area hit answers `policy.path_denied`) whether or not it exists (no existence oracle). Spike check: `files.stat` of a
  non-existent path outside the jail is 403, inside the jail `{"exists": false}`.
* Step 5 uses the *principal-filtered* view: an op that no rule grants to this principal is `404 op.not_enabled`
  for them, even if it is mounted for another principal. Authorization failures after a rule *matched* but its
  scope rejected the call are `403`.
* Policy decisions are made on an immutable **policy snapshot** captured at step 1; reload (03 section 10) swaps
  the snapshot atomically for *new* requests.
* Handler exceptions never skip step 10.

## 7. Discovery (all generated from the registry)

| Surface | Content |
|---------|---------|
| `GET /capabilities` | **(v2.1, IF-26)** v2 keys `api`, `catalog_version`, `revision` (policy hash), `principal`, `ops` (the ops *effective for the caller* with limits/scopes), `policy` (preset names, lint messages if the caller is admin) **plus a compat projection** for two minors: the in-flight keys `api_version`, `endpoints{}`, `identity`, `groups`, `warnings`, generated from the same data (no second source). The client detects, in order: `ops` -> `endpoints` -> `groups` (07 section 3) |
| `GET /ops` and `POST /ops/core.describe` | the full catalog for the caller (`?all=1` includes unmounted ops with the reason; admin only); each entry as in 7.1 |
| `GET /openapi.json` | OpenAPI 3.1; one path item per REST binding; `operationId` = op ID; `x-abx-effects`, `x-abx-limits`; plus the RPC paths `POST /ops/{id}` |
| `python -m agent_sandbox.server describe [--json|--markdown|--ids]` / `server.describe()` | same data offline, no server needed (introspection mode, see 06) |
| `agent_sandbox/server/catalog/_ops.pyi` | `ops` attribute tree with every built-in ID, so editors autocomplete `ops.files.<TAB>` |
| `POST /ops/core.check` | "would this call be allowed?" without running it: `{"op": "files.download", "args": {"path": "/etc/passwd"}}` -> `{"allowed": false, "code": "policy.path_not_allowed"}` (never reveals rule contents to non-admins; replaces `POST /capabilities/check`) |

### 7.1 Catalog entry (`operations.json`)

```json
{
  "id": "files.download",
  "summary": "Download a file.",
  "effects": ["read"],
  "group": "file_ops",
  "http": [{"method": "GET", "path": "/files/download-stream", "legacy": true},
           {"method": "GET", "path": "/download", "legacy": true}],
  "rpc": "/ops/files.download",
  "params": [{"name": "path", "type": "string", "required": true, "kind": "path", "doc": "File to read"}],
  "result": {"kind": "bytes", "content_type": "application/octet-stream"},
  "limits": ["max_bytes", "rate", "concurrency"],
  "stream": "bytes",
  "install": [],
  "since": "1.0",
  "aliases": ["files_download_stream", "download"],
  "deprecated": null
}
```

`operations.json` is committed under `server-sdk/src/agent_sandbox/server/catalog/`, shipped in the wheel, and
copied (generated) into the client wheel and the Node CLI (see [07](07-client-mirror.md)).

## 8. Custom operations: the full answer

1. **Python decorator** (above). Registered into the server's registry; visible in `/capabilities`, OpenAPI,
   `describe`, and addressable by policy exactly like built-ins (`allow(ops.custom.grade, ...)` or
   `allow("grader.*", principals=["role:grader"])`).
2. **Schema** comes from annotations; return annotation (TypedDict/dataclass) becomes `result` schema.
3. **Policy** for a custom op is the same engine. Because the engine cannot see inside a handler, the author
   declares `paths=`/`command=`/`effects=`; the handler then receives admitted values. For anything the engine
   cannot express, write an `authorize` hook (03 section 8) or check inside the handler and raise `OpError`.
4. **Client stub generation.**
   * Zero-step: `ServerClient` builds its attribute tree dynamically from `GET /ops` (`client.custom.grade(...)`,
     `client.call("custom.grade", submission=...)`), with type checking *at call time* against the fetched schema.
   * One step: `agent-sandbox-server gen-client --lang python --module my_template_ops` writes a typed module
     (`TypedDict` results, keyword-only parameters, docstrings) importable by the application;
     `--lang ts` writes a TypeScript module for the Node CLI/JS apps; `--lang openapi` writes the OpenAPI file.
     Generation reads the *registry offline* (introspection mode), so it works in CI without a running sandbox.
5. **Legacy extension forms keep working** and are mapped to operations:

   | Legacy | New identity | Notes |
   |--------|--------------|-------|
   | `registry.command("name", ...)` / `CommandRegistry` | `custom.<name>`; `POST /commands/{name}` resolves to it; `GET /commands` = `custom.list` | command names `list` and `describe` are reserved |
   | `table.route(method, path, group=...)` | `ext.<handler_name>` (de-duplicated with `_2`), binding = the given method/path | group becomes `group:` membership; effects default to `{"admin"}` unless `effects=` is passed (fail-closed default for unknown code) |
   | `CapabilityGroup.X` | `group:x` selector | golden list in [04](04-builtin-modules.md) |

6. **Third-party packages** can ship ops (`load:`), including *their own lazy-install requirements*
   (`install=("my-tool",)` referencing a manifest file shipped by the package).

## 9. Versioning and compatibility of the identity space

* `catalog_version` (integer) increments only on a breaking change: removing an ID or changing its argument
  semantics incompatibly. `sdk_version` is the wheel version. Both appear in `/capabilities`, `operations.json`,
  and `X-ABX-Server` response headers.
* IDs are append-only. **A renamed ID keeps the old one as an alias for at least two minor releases**
  (`since`/`deprecated` fields in the catalog); removal requires a `catalog_version` bump.
* New *optional* parameters and new result keys are non-breaking. Result keys are never removed within a
  `catalog_version`.
* The client sends `X-ABX-Client: agent-sandbox-py/<ver> catalog=<n>`; the server may log it; a client whose
  generated catalog is newer than the server's catalog sees `ContractMismatchError` (E3111) only when it calls an op
  the server does not list; older clients keep working because IDs never disappear.
* `api` in `/capabilities` is the wire family string `agent-sandbox/2`; the `/v1` agents wire family tracks the OpenAI
  `agents=v1` beta header separately ([05](05-agents-api.md)).

## 10. Implementation notes

* **Thread model unchanged** (listener hardening in step 0 aside): `ThreadingHTTPServer`, one thread per request; handlers are synchronous; blocking ops
  (commands) honour `ctx.deadline`. The registry and policy snapshot are immutable after start, so no locks on the
  hot path. Per-op `concurrency` uses a `BoundedSemaphore` created at admit time.
* **Import cost**: `import agent_sandbox.server` imports `core` + `policy` + `guards` only (stdlib). `ops.<ns>`
  modules and `agents` import on first mount. Budget: `python -X importtime -c "import agent_sandbox.server"` below
  40 ms on the reference runner; guarded by a benchmark test.
* **Schema generation** is deliberately small (no pydantic). The supported-annotation list above is closed;
  anything else is a registration error naming the parameter.
  suggestions, `describe`, `openapi`; the production version adds aliases, bindings, trie router, catalog output.
