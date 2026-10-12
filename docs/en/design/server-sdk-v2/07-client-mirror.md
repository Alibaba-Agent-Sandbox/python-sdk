# 07 - Client mirror: Python `ServerClient` and the Node CLI

> Part of [Server SDK v2](README.md). Rule R5. Supersedes `client-server-alignment.md` sections on naming/errors
> (its gap analysis of envd vs server remains valid input).
> **v2.1**: ONE client error range (E3100-E3111, `E9xxx` is dropped, in-flight class names kept), a wire-code -> exception table, `Authorization` vs
> `X-Access-Token` precedence, a machine-checkable parity ledger covering **every** op (including the 18 ops, `browser.*` and `ext.*` the feasibility review found missing),
> `Sandbox.server` versus the declarative `sandbox.server.start` namespace. Findings: IF-07, IF-10, IF-11, IF-17, IF-26, IF-27, IF-28, N-3, N-8.

## 1. Principle

The client does not hand-write a method per endpoint. Both clients are **generated from the server catalog**
(`operations.json`, [02](02-operation-model.md) section 7.1), have **the same namespace tree as the server**, and are
checked by contract tests that replay every catalog operation against a real server.

```python
sb = await Sandbox.connect(sandbox_id)          # existing
srv = sb.server                                  # ServerClient bound to the sandbox's port 9000 (gateway headers added)

await srv.files.list("/tmp")                     # op files.list
data = await srv.files.download("/tmp/a.txt")    # bytes (decoded); op files.download
await srv.commands.run("ls /tmp")                # op commands.run -> CommandResult-like
await srv.agents.codex.run("fix the failing test")           # op agents.codex.run
sess = await srv.agents.codex.sessions.create(environment={"type": "self_hosted", "id": "env_local", "remote_url": srv.base_url},
                                              input="fix the failing test")      # same shape as the official SDK (05 section 5); no `workspace=` shorthand
await srv.custom.grade(submission="...")         # user-defined op, dynamic tree from GET /ops
await srv.call("custom.grade", submission="...") # generic escape hatch (also takes ops.* nodes)
```

* Method name = last ID segment; namespace attributes mirror the ID: `srv.system.env.get()`, `srv.agents.claude_code.run(...)`.
* Sync twins: `srv.files.list_sync("/tmp")` for every method (library convention).
* IDs are importable: `from easy_sandbox import ops` returns the **same** `OpRef` tree as the server's (`ops.files.list`), so policy code,
  client calls and docs share spelling. (`easy_sandbox.ops` is generated from the catalog; the server's `easy_sandbox.server.ops` is the same
  declaration; the contract test asserts equality of the two trees.)
* `srv.describe()`, `srv.ops` (tree), `srv.capabilities()` for discovery.
* Parameters are keyword-friendly and typed; results are `TypedDict`s (dict at runtime) **(v2.1, IF-11)**: the generated `ServerClient` may emit the existing
  pydantic result models of `models/server.py` (the working tree already uses them for 48 endpoints) instead of `TypedDict`s; the generator has one switch
  (`--result-style typeddict|pydantic`, default `pydantic` for the client wheel because pydantic is already a client dependency; the **server** package stays stdlib-only).
  Both are dict-compatible at the boundary. The base exception class is the existing `SandboxError` (there is no `EasySandboxError`).
* **Compat aliases of the in-flight client (v2.1).** The working tree's hand-written `ServerClient` (`api/server_client.py`) keeps its method names as **deprecated aliases**
  of the generated tree for two minors: `srv.process.shell` = `srv.commands.run`, `shell_stream` = `commands.stream`, `srv.files.upload_legacy/download_legacy`
  stay, `srv.system.env()`/`set_env()` = `system.env.get/set`, `srv.devtools.run_code` = `devtools.code.run`, `srv.pty.*` = `srv.terminal.*`. A test asserts each alias resolves to the same op id.

## 2. Generation and drift control

```
server registry --(easy-sandbox-server gen-client --lang python)--> client-sdk/src/easy_sandbox/api/server/_generated.py
                --(--lang ts)------------------------------------> cli/src/server/generated/catalog.ts, client.ts
                --(--lang openapi)-------------------------------> catalog/openapi.json (shipped, also a release asset)
                --(describe --markdown)--------------------------> tables in 04-builtin-modules.md
```

* Generated files carry a header with `catalog_version`, the registry digest, and "DO NOT EDIT". They are **committed**, so the client wheel
  has no build-time dependency on the server package and no runtime import of it (`AGENTS.md` layering stays).
* **Drift test** (monorepo CI, needs both packages installed from source): regenerate in memory, compare with committed files -> fail on diff.
  Separate **contract test** starts a server with `full_access`, plus fake agent binaries, and for each catalog op calls the generated client
  method with schema-derived minimal arguments from `tests/contract/cases.py` (hand-written *argument fixtures only*; one per op), asserting
  status class, result keys, and client/server error mapping. A new op without a case fails the suite (case coverage test).
* **Dynamic fallback** for ops the generated client does not know (custom ops, newer server): `ServerClient` fetches `GET /ops` lazily on first
  unknown attribute access and builds callables from the schema; arguments are validated client-side; results are returned as dicts. This is also
  how `srv.custom.<name>` works without codegen. One `GET /ops` per client instance, cached for the session.

## 3. Capability awareness (no hidden traffic)

```python
caps = await srv.discover()                 # explicit GET /capabilities (never implicit)
caps.can(ops.files.download)                # bool, for this principal
caps.limit(ops.files.download, "max_bytes") # effective limit or None
caps.paths(ops.files.download)              # PathScope summary (roots, readonly) if the server exposes scopes
caps.require(ops.files.upload)              # raises OperationNotEnabledError (E3103) before any network call
await caps.check(ops.files.download, path="/etc/passwd")   # server-side dry-run: core.check
caps.legacy                                 # True for pre-v2 servers (no `ops` key): groups mapped through the golden lists in 04
```

* Methods consult a populated cache and **fail fast** with `OperationNotEnabledError` / `PolicyDeniedError`-typed errors only when `discover()` was
  called; server responses stay authoritative and produce the same exceptions. No request is made on the user's behalf except the call itself.
* `ServerClient(strict=True)` makes `discover()` mandatory before calls (useful in agents that must not probe).
* **Discovery body detection (v2.1, IF-26).** The server serves a union body (02 section 7). The client detects in this order: `ops` (v2.1 server) -> `endpoints` (in-flight
  v1.x capability server) -> `groups` (v1 server; golden lists in 04). `ServerCapabilities.legacy` is true only for the last. The compat keys stay for two minors, then are removed in a `catalog_version` bump.
* **Credentials (v2.1, IF-17).** The client sends **one** credential: `Authorization: Bearer <token>`. `X-Access-Token` is sent only when `ServerClient(legacy_auth=True)`
  (needed for pre-v2.1 servers; the discovery of a v1 server switches it on automatically). Both headers are never sent together. The server rule (03 section 5): Bearer wins, the legacy header
  is an alias, both present and different -> `401 auth.conflicting_credentials` (client class `ServerAuthError`, message names the conflict), both equal -> accepted. The gateway's own
  header (`X-Access-Token` for the Alibaba gateway) is added **by the transport** and never forwarded as the server credential; when a deployment sits behind such a gateway,
  set `gateway_token=` (transport header) and `token=` (server Bearer) separately.

## 4. Errors: ONE range, E3100-E3111 (v2.1, IF-10)

The repository has three schemes today: the working tree uses `E9000-E9005` (`models/errors.py`, header "E9xxx = In-sandbox server API errors"), the in-flight capability design
proposed `E8xxx`, and v2.0 proposed `E3100-E3111`. **Decision (D29): the server plane uses `E3100-E3111` only**, next to the execution family (`E3000-E3006`);
`E8000-E8030` stays exclusively with the providers package (`providers/`), `E9xxx` is removed from every plan and document.

| Code | Class (existing in-flight name kept) | Wire `code` / status | Also subclasses (compat) | Replaces |
|------|--------------------------------------|----------------------|--------------------------|----------|
| E3100 | `ServerAPIError` (base), `ServerArgumentError(ServerAPIError, ValueError)` | any unmapped, `args.*` 400 | `SandboxError` | E9000 |
| E3101 | `ServerAuthError` | `auth.*` 401, 429 `auth.rate_limited`, `auth.conflicting_credentials` | `AuthenticationError` | E9001 |
| E3102 | `PolicyDeniedError`, `FilePolicyDeniedError` | `policy.*` 403 (incl. `policy.scope_required`, `policy.path_*`, `policy.command_*`, `policy.url_*`), `request.host_denied`, `request.origin_denied` | `PermissionDeniedError` (file variant) | E9002 |
| E3103 | `EndpointNotAvailableError` (alias `OperationNotEnabledError`) | `op.not_enabled` 404, `op.unknown_route`, `agents.not_found` on unmounted adapters | `CapabilityNotSupportedError` (E3004) | E9003 |
| E3104 | `PayloadTooLargeError` | `limit.max_bytes`, `limit.request_too_large` 413 | | E9004 |
| E3105 | `RateLimitedError` | `limit.rate`, `limit.concurrency` 429 (`retry_after`) | | E9005 |
| E3106 | `ServerInstallError` | `install.*` (`phase`, `retry_after`, `job_id`; 202 is a result, not an error) | | new |
| E3107 | `ServerAgentError` | `agents.*` | | new |
| E3108 | `ServerUnavailableError` | `server.unavailable`, `request.busy`, connection errors, 502/503 without code | `ConnectionError_` | new |
| E3109 | `ServerInternalError` | `server.internal` 500 | | new |
| E3110 | `ContractMismatchError` | raised client-side: op unknown to the server's catalog while the generated client has it | | new |
| E3111 | `ServerConfigError` | raised client-side: strict-mode misuse, ambiguous credentials configured locally, bad `ServerClient(...)` arguments | `ValueError` | new |

**Attributes (kept + extended).** The working tree's `ServerAPIError(status_code, error_type, error_code, endpoint)` is kept **unchanged** (existing user code reads them); v2.1 adds
`op` (the op id; equals `endpoint` for in-flight servers), `request_id`, `details` (dict), `status` (alias of `status_code`). The attribute `.code` **remains the E-code**
(`"E3102"`), never the wire code; the wire code is `.error_code`. This removes the v2.0 clash of `.code` meaning two things.

**Wire code -> exception (N-8).** Most specific first:

| Wire `code` (03 section 11) | HTTP | Exception | E-code |
|---|---|---|---|
| `auth.required`, `auth.invalid`, `auth.conflicting_credentials` | 401 | `ServerAuthError` | E3101 |
| `auth.rate_limited`, `limit.rate`, `limit.concurrency` | 429 | `RateLimitedError` (`retry_after`) | E3105 / E3101 for `auth.rate_limited` |
| `op.not_enabled`, `op.unknown_route` | 404 | `EndpointNotAvailableError` | E3103 |
| `args.*` | 400 | `ServerArgumentError` | E3100 |
| `policy.scope_required`, `policy.denied_by_rule`, `policy.denied_by_hook`, `policy.hook_error`, `policy.hook_bad_return`, `policy.not_permitted` | 403 | `PolicyDeniedError` | E3102 |
| `policy.path_*`, `policy.symlink_denied`, `policy.hardlink_denied`, `policy.not_regular_file`, `policy.read_only` | 403 | `FilePolicyDeniedError` | E3102 |
| `policy.command_*`, `policy.executable_not_allowed`, `policy.shell_not_allowed`, `policy.env_var_denied`, `policy.url_*` | 403 | `PolicyDeniedError` | E3102 |
| `request.host_denied`, `request.origin_denied`, `request.bad_target`, `request.bad_content_type` | 403 / 400 / 415 | `PolicyDeniedError` (403) / `ServerArgumentError` | E3102 / E3100 |
| `limit.max_bytes`, `limit.request_too_large` | 413 | `PayloadTooLargeError` (`limit`) | E3104 |
| `install.*` (non-202) | 424 / 502 / 503 | `ServerInstallError` | E3106 |
| `agents.*`, OpenAI-wire `error.type` | 4xx/5xx | `ServerAgentError` | E3107 |
| `request.busy`, `server.unavailable`, `server.shutting_down`, transport failure | 503 | `ServerUnavailableError` | E3108 |
| `server.internal` | 500 | `ServerInternalError` | E3109 |
| legacy v1 body without `code` | any | by status: 401 auth, 403 policy, 404 `endpoint_disabled` -> E3103, 413, 429, else base | by status |

**What in-flight code must change (hand-over list, also section 9 of [10](10-implementation-plan.md)):**
1. `client-sdk/src/easy_sandbox/models/errors.py`: header comment `E9xxx` -> `E31xx`; `code = "E9000..E9005"` -> `"E3100..E3105"`; add `ServerInstallError`, `ServerAgentError`,
   `ServerUnavailableError`, `ServerInternalError`, `ContractMismatchError`, `ServerConfigError`, `ServerArgumentError`; add `op`, `request_id`, `details`, `status`; export in `models/__init__.py`.
2. `client-sdk/src/easy_sandbox/api/server_client.py` (`error_from_response`): map by the table above (prefers the wire `code`, falls back to the legacy `type`/status rules).
3. Tests: `tests/test_api/server_e2e/test_server_client_models.py` (2 hits), `test_server_client_policy.py` (1 hit): E9xxx -> E31xx.
4. Docs (en and zh pairs): `reference/error-codes.md` (9), `reference/api-reference.md` (4), `design/fine-grained-capabilities.md` (E8xxx text, 5), `design/client-server-alignment.md`, `design/cli-followups.md`, root `CHANGELOG.md` entry.
5. CLI (`/workspace/cli`): exit-code mapping uses the **wire** family, not E-codes; nothing to rename.
6. `fine-grained-capabilities.md` section 7 proposes `E8000-E8005`: superseded banner; the providers keep `E8000-E8030` untouched. A repository test (`tests/test_error_codes_unique.py`) asserts that no two classes share an E-code except documented subclass pairs and that no class outside `providers/` uses E8xxx and none uses E9xxx.

Specific legacy mappings are preserved: `files.*` 404 -> `FileNotFoundError_`; `commands.run` timeout -> `CommandTimeoutError` (E3001); unknown named command ->
`CommandNotFoundError` (E3005, also `EndpointNotAvailableError`); non-zero exit remains a *result*, not an exception (as in `ProcessError` only when the caller asks `check=True`).
`202 install.job` is a result: the generated client polls it with `srv.agents.<a>.install.wait(job)` or surfaces `InstallPending(job_id, retry_after)` when `wait=False`.

## 5. Sandbox integration

* **`Sandbox.server` versus the declarative namespace (v2.1, IF-07).** Today the declarative layer has `sandbox.server.start(...)` / `sandbox.server.register.*`. The attribute
  `Sandbox.server` is **one object** (`ServerNamespace`): it forwards attribute access to the generated `ServerClient` tree (`sb.server.files.list(...)`) **and** keeps the declarative
  methods `start`, `register`, `enable_builtin`, `restart` as members (names that are not op namespaces; the generator refuses to emit a namespace named `start`, `register`, `restart`, `enable_builtin`).
  A test pins both uses. Owner: WP-10c.
* `Sandbox.server` -> `ServerClient` for port 9000 using the sandbox's port URL and gateway headers; `Sandbox.server_at(port, token=...)` for other ports/tokens;
  the Bearer token comes from `server_token=` / `EBX_SERVER_TOKEN`. Both `X-Access-Token` and `Authorization: Bearer` are sent per transport (server accepts either).
* `Sandbox.start_server(...)` (remote start + readiness via `healthcheck`) as in the base-image design.
* `Sandbox.custom(name, **kw)` and `list_commands()` remain unchanged (template mechanism A, server mechanism B) and are re-implemented over `srv.custom.*` when the
  server reports v2; for v1 servers they use the old routes.
* Official OpenAI SDK helper: `srv.agents.openai_client()` returns `openai.OpenAI(base_url=<port-url>/v1, api_key=<token>)` when `openai` is installed (lazy import).

## 6. Parity: client counterpart of every server op (v2.1, IF-27)

Rule: **every op has a counterpart on the generated `ServerClient` tree** (same dotted path; R5). Where the experience differs (stream, raw bytes, admin guard, dynamic, reserved,
refused) the row says so in `Kind` and, where it matters, carries an asymmetry id (A1..A7, listed below). The ledger is `spikes/parity_ledger.py`; `spikes/tests_parity.py` fails when a registry
op has no row or a row names no op; in the implementation it becomes `tests/contract/client_parity.json` generated by `make gen` and checked by the drift test (WP-10).
The 18 ops the feasibility review found without a client (`files.search`, `files.upload_stream`, `files.download_stream`, `files.archive`, `process.get`, `process.output`, `terminal.list`,
`terminal.get`, `system.info`, `system.env.get`, `system.env.set`, `system.ports`, `system.packages`, `devtools.git.status`, `devtools.git.diff`, `core.openapi`, `core.reload`, `core.describe`),
all of `browser.*` and `ext.*` are rows below.

### 6.1 Documented asymmetries

| ID | Asymmetry | Reason |
|----|-----------|--------|
| A1 | `core.openapi` returns raw JSON, not a typed result | documentation asset |
| A2 | `core.reload`, `system.env.set`, `process.signal`, `terminal.create`, `agents.<a>.install`, `agents.<a>.sessions.create` are explicit-only on the server; the client exposes them but a call to an unmounted one is the normal `EndpointNotAvailableError` | policy, not client, decides |
| A3 | `system.*` has no envd twin; envd `metrics` is the platform plane | planes stay separate (no hidden fallback) |
| A4 | `devtools.code.run` is a different engine than `code.run` on port 49999 (no contexts) | documented in 04 |
| A5 | `agents.environments.files.*` reserved ids: no client method in 0.3.0 | reserved for policy addressing only (T-4) |
| A6 | official `subagents.{retrieve,list_items,turns.*}`: the client method raises `NotSupportedError` locally, the server answers 404 `not_found_error` | tier 3 refusal (05 section 4) |
| A7 | `custom.<name>`, `ext.<handler>`: no generated method; reached through the dynamic tree from `GET /ops` or `srv.call(id, **args)` | ids are decided by the template author |

### 6.2 Plane map (envd vs server)

The two planes keep their own method names (`sandbox.files.make_dir` on envd, `sandbox.server.files.mkdir` on the server plane, the latter always equal to the op ID verb); the `envd twin` column is the map.
Applications choose the plane explicitly; there is no transparent fallback between planes (hidden fallbacks would make "was this call policy-checked?" unanswerable). Not mirrored on the server by design:
`network`, `pause/resume`, `timeout`, `templates` (platform plane), envd signed file URLs (envd only).

### 6.3 Ledger (generated; do not edit by hand)

| Op id | Client call (generated, same tree) | envd twin | Kind | Note / asymmetry |
|---|---|---|---|---|
| `agents.codex.install` | `srv.agents.codex.install()` | - | admin | explicit-only; 202 + job |
| `agents.codex.run` | `srv.agents.codex.run(prompt, ...)` | - | typed | AgentScope required |
| `agents.codex.sessions.create` | `srv.agents.codex.sessions.create(...)` | - | typed | exec-effect op; AgentScope required |
| `agents.codex.sessions.send_event` | `srv.agents.codex.sessions.send_event(id, event)` | - | typed | exec-effect op |
| `agents.definitions.create` | `srv.agents.definitions.create(...)` | - | typed | official `agents.create` |
| `agents.definitions.delete` | `srv.agents.definitions.delete(id)` | - | typed |  |
| `agents.definitions.get` | `srv.agents.definitions.get(id)` | - | typed |  |
| `agents.definitions.list` | `srv.agents.definitions.list(**page)` | - | typed | list envelope; auto-paging iterator |
| `agents.definitions.update` | `srv.agents.definitions.update(id, ...)` | - | typed |  |
| `agents.environments.create` | `srv.agents.environments.create(...)` | - | typed |  |
| `agents.environments.files.create` | `-` | - | reserved | reserved id (T-4); not implemented in 0.3.0 (asymmetry A5) |
| `agents.environments.files.list` | `-` | - | reserved | reserved id (T-4); not implemented in 0.3.0 (asymmetry A5) |
| `agents.environments.get` | `srv.agents.environments.get(id)` | - | typed |  |
| `agents.environments.list` | `srv.agents.environments.list(**page)` | - | typed |  |
| `agents.models.list` | `srv.agents.models.list()` | - | typed |  |
| `agents.runtimes.doctor` | `srv.agents.runtimes.doctor()` | - | typed |  |
| `agents.runtimes.list` | `srv.agents.runtimes.list()` | - | typed | was `agents.list` (N-1); flags experimental adapters |
| `agents.sessions.artifacts.content` | `srv.agents.sessions.artifacts.content(id, aid)` | - | raw | bytes |
| `agents.sessions.artifacts.delete` | `srv.agents.sessions.artifacts.delete(id, aid)` | - | typed |  |
| `agents.sessions.artifacts.get` | `srv.agents.sessions.artifacts.get(id, aid)` | - | typed |  |
| `agents.sessions.artifacts.list` | `srv.agents.sessions.artifacts.list(id)` | - | typed |  |
| `agents.sessions.create` | `srv.agents.sessions.create(...)` | - | typed | two-level gate with agents.<a>.sessions.create |
| `agents.sessions.delete` | `srv.agents.sessions.delete(id)` | - | typed |  |
| `agents.sessions.get` | `srv.agents.sessions.get(id)` | - | typed |  |
| `agents.sessions.list` | `srv.agents.sessions.list(**page)` | - | typed |  |
| `agents.sessions.list_items` | `srv.agents.sessions.list_items(id, **page)` | - | typed |  |
| `agents.sessions.send_event` | `srv.agents.sessions.send_event(id, event)` | - | typed | official `events.create` (202, N-2) |
| `agents.sessions.stream_events` | `srv.agents.sessions.stream_events(id)` | - | stream | SSE; idle-open |
| `agents.sessions.subagents.get` | `raises NotSupportedError` | - | refused | server 404 not_found_error (asymmetry A6) |
| `agents.sessions.subagents.list` | `srv.agents.sessions.subagents.list(id)` | - | typed | empty list envelope |
| `agents.sessions.subagents.list_items` | `raises NotSupportedError` | - | refused | asymmetry A6 |
| `agents.sessions.subagents.turns.get` | `raises NotSupportedError` | - | refused | asymmetry A6 |
| `agents.sessions.subagents.turns.list` | `raises NotSupportedError` | - | refused | asymmetry A6 |
| `agents.sessions.subagents.turns.list_items` | `raises NotSupportedError` | - | refused | asymmetry A6 |
| `agents.sessions.traces.list` | `srv.agents.sessions.traces.list(id)` | - | typed | empty list envelope in 0.3.0 |
| `agents.sessions.turns.get` | `srv.agents.sessions.turns.get(id, turn_id)` | - | typed |  |
| `agents.sessions.turns.list` | `srv.agents.sessions.turns.list(id)` | - | typed |  |
| `agents.sessions.turns.list_items` | `srv.agents.sessions.turns.list_items(id, turn_id)` | - | typed |  |
| `agents.sessions.update` | `srv.agents.sessions.update(id, ...)` | - | typed |  |
| `browser.click` | `srv.browser.click(selector)` | - | typed |  |
| `browser.console` | `srv.browser.console()` | - | typed |  |
| `browser.content` | `srv.browser.content(type)` | - | typed |  |
| `browser.evaluate` | `srv.browser.evaluate(script)` | - | typed |  |
| `browser.navigate` | `srv.browser.navigate(url)` | - | typed | UrlScope-checked |
| `browser.pdf` | `srv.browser.pdf()` | - | raw | bytes |
| `browser.screenshot` | `srv.browser.screenshot()` | - | raw | bytes |
| `browser.type` | `srv.browser.type(selector, text)` | - | typed |  |
| `commands.run` | `srv.commands.run(command|argv)` | commands.run | typed | in-flight alias srv.process.shell is a deprecated alias |
| `commands.stream` | `srv.commands.stream(command|argv)` | commands.stream | stream | in-flight alias srv.process.shell_stream |
| `core.capabilities` | `srv.discover() / srv.capabilities()` | - | typed | never implicit (07 section 3) |
| `core.check` | `caps.check(op, **args)` | - | typed | dry-run; `explain` is the offline CLI twin |
| `core.describe` | `srv.describe(), srv.ops` | - | typed |  |
| `core.health` | `srv.core.health()` | - | typed | anonymous; used by readiness |
| `core.openapi` | `srv.core.openapi()` | - | raw | documentation asset; no typed result (asymmetry A1) |
| `core.reload` | `srv.core.reload()` | - | admin | explicit-only admin op; exposed but never in a convenience group (asymmetry A2) |
| `custom.list` | `srv.custom.list()` | list_commands() | typed |  |
| `devtools.code.run` | `srv.devtools.code.run(language, code)` | code.run | typed | different engine than port 49999 (asymmetry A4) |
| `devtools.git.diff` | `srv.devtools.git.diff(path)` | - | typed |  |
| `devtools.git.status` | `srv.devtools.git.status(path)` | - | typed |  |
| `files.archive` | `srv.files.archive(paths)` | - | typed | server-only |
| `files.delete` | `srv.files.delete(path)` | files.remove | typed |  |
| `files.download` | `srv.files.download(path)` | files.read_bytes | typed |  |
| `files.download_stream` | `srv.files.download_file(remote, local)` | files.download_url (signed) | stream | chunked body |
| `files.list` | `srv.files.list(path)` | files.list | typed |  |
| `files.mkdir` | `srv.files.mkdir(path)` | files.make_dir | typed |  |
| `files.move` | `srv.files.move(source, destination)` | files.rename | typed |  |
| `files.search` | `srv.files.search(root, pattern)` | - | typed | server-only convenience; envd has no search |
| `files.stat` | `srv.files.stat(path), exists()` | files.get_info/exists | typed |  |
| `files.upload` | `srv.files.upload(path, data)` | files.write | typed | base64-JSON; large files are better on envd |
| `files.upload_stream` | `srv.files.upload_file(local, remote)` | files.upload_url (signed) | stream | chunked body; envd uses signed URLs |
| `files.watch` | `srv.files.watch(path)` | files.watch | stream | SSE |
| `process.get` | `srv.process.get(pid)` | - | typed | server-only; envd uses a handle |
| `process.list` | `srv.process.list()` | commands.list | typed |  |
| `process.output` | `srv.process.output(pid, since)` | - | stream | long-poll; follow() helper |
| `process.signal` | `srv.process.signal(pid, sig)` | commands.kill | typed | explicit-only op |
| `process.start` | `srv.process.start(...)` | commands.start | typed |  |
| `process.stdin` | `srv.process.stdin(pid, data)` | commands.send_stdin | typed |  |
| `system.env.get` | `srv.system.env.get(names)` | - | typed |  |
| `system.env.set` | `srv.system.env.set(vars)` | - | admin | explicit-only; writes the server overlay only |
| `system.info` | `srv.system.info()` | - | typed | envd metrics are platform plane (asymmetry A3) |
| `system.metrics` | `srv.system.metrics()` | metrics (platform) | typed |  |
| `system.packages` | `srv.system.packages(manager)` | - | typed |  |
| `system.ports` | `srv.system.ports()` | - | typed |  |
| `terminal.connect` | `srv.terminal.connect(id) -> PtyConnection` | terminal handle | stream | WebSocket on 9001; policed on upgrade |
| `terminal.create` | `srv.terminal.create()` | get_terminal | typed | explicit-only op |
| `terminal.delete` | `srv.terminal.delete(id)` | terminal handle | typed |  |
| `terminal.get` | `srv.terminal.get(id)` | - | typed | server-only |
| `terminal.list` | `srv.terminal.list()` | - | typed | server-only |
| `terminal.resize` | `srv.terminal.resize(id, cols, rows)` | terminal handle | typed |  |
| `custom.<name>` | `srv.custom.<name>(**kw) / srv.call('custom.<name>')` | Sandbox.custom(name) | dynamic | tree built from GET /ops (asymmetry A7) |
| `ext.<handler>` | `srv.call('ext.<handler>')` | - | dynamic | arbitrary legacy RouteTable routes; dynamic tree only (asymmetry A7) |


Per-adapter rows are identical for `codex`, `claude_code`, `qwen_code`, `cursor`, `qoder` (the table shows `codex`; the ledger test expands all five).

## 7. Node CLI (`ebx`) mirror

The CLI (`/workspace/cli`, TypeScript, ESM) is a first-class consumer:

* **Downstream consumer, separate release train (v2.1, IF-28).** The CLI is a separate package (`/workspace/cli`, its own `package.json`, vitest, release train). It is **fed**, not generated in-tree:
  the SDK release publishes `operations.json` (+ `openapi.json`) as a release asset `easy-sandbox-server-catalog-<version>.json`; the CLI repo's `scripts/sync-catalog` downloads the pinned
  version, writes `catalog.ts`/`client.ts` and records the digest. The SDK CI does not build the CLI; the CLI CI fails on digest drift. Owner: WP-10d (cross-repo; may land after 0.3.0, see the cut list).
* **Generated** `cli/src/server/generated/catalog.ts` (const catalog + types) and `client.ts` (`ServerClient` with the same namespace tree, `fetch`-based) from
  `operations.json` through `easy-sandbox-server gen-client --lang ts` (run by a script in the CLI repo against the pinned wheel, or fed the catalog file
  published as a release asset `easy-sandbox-server-catalog-<version>.json`). `scripts/sync-catalog` records the catalog digest; CI fails on drift.
* **Spelling parity**: the TypeScript client uses the op IDs and parameter names *exactly as spelled on the wire* (snake_case: `client.agents.claude_code.run({prompt})`,
  `max_entries`), no camelCase renaming, so docs, policies and logs read identically in both languages.
* Commands (all generic, so new ops need no CLI release): `ebx server ops [--json]` (list effective ops), `ebx server describe <op>`, `ebx server call <op>
  [--arg k=v ...|--json '{...}']`, `ebx server check <op> [--arg ...]` (dry-run policy), `ebx server doctor` (remote `core.capabilities` + health).
  Friendly wrappers for common namespaces (`ebx files ls --plane server`, `ebx agents ...` per the agents CLI follow-ups) are thin and generated from the catalog
  where possible.
* Error mapping: the CLI exit codes follow the existing table; server error families map as: `auth.*` -> auth exit code, `policy.*`/`op.not_enabled` -> permission
  exit code, `limit.*`/`install.*` -> retryable code, others -> 1.
* The same catalog/OpenAPI makes **other languages** (Go, Java, ...) a generator invocation away (`operationId` = op ID). No hand-maintained clients beyond Python and
  TypeScript are promised.

## 8. Versioning and compatibility

* Client sends `X-EBX-Client` with its catalog version; the server never rejects on it.
* Older client / newer server: works (IDs append-only). Newer client / older server: calls to ops the server does not list raise `ContractMismatchError`
  naming the server `sdk_version`, **or** transparently use the legacy REST binding when the catalog says the op existed in v1 under another route.
* v1 servers (no `ops` in `/capabilities`): `ServerCapabilities.legacy = True`, group-level gating only via golden lists.
