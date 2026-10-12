# Decision: Server SDK v2 strangler stages S1 and S2 (operations beside the v1 dispatcher)

Status: proposed

## Problem
[Server SDK v2](../../../../docs/en/design/server-sdk-v2/README.md) makes every capability an operation (`files.download`, `commands.run`) with one policy decision, and keeps the v1 dispatcher until the v2 pipeline passes the v1 fixtures (D25, plan section 1.1). Stages S1 and S2 add the operation model and `POST /ops/{id}` without changing a status code or body of any v1 route.

## Decision
New package `easy_sandbox/server/core/` (stdlib only), nothing renamed or deleted:

| Module | Content |
|---|---|
| `ids.py`, `refs.py`, `errors.py` | ID grammar (2 to 5 segments), `mangle_custom_name`, `OpRef`/`OpTree`/`ops` (not `str` subclasses), `OpError`, `RegistryFrozen` |
| `registry.py` | `Operation`, `Param`, `HttpBinding`, `Registry` (`op` decorator, prefix rule, aliases, `child`, `freeze`, `describe`, `catalog`); omitted `effects` means `admin`, explicit-only |
| `legacy.py` | `build_registry(route_table, command_registry)`: one operation per v1 route (IDs, effects, summaries from design 04); wrappers, not copies |
| `policy.py` | `Policy` with `Policy.from_engine(engine)` and `Policy.open(table)`; `authenticate`, `peek`, `admit`, `audit` |
| `dispatch.py` | `Pipeline` (authenticate, resolve, mounted, args, admit, run, audit); in-process `Pipeline.call` |
| `discovery.py`, `http.py` | `core.describe` document; `serve_ops` glue that `app.py` calls |

Behaviour:

* **Wrappers.** A v1-route operation has no handler of its own. `Pipeline` builds a `ServerRequest` from the arguments (`{name}` path variables first; the rest go to the query string for GET/DELETE and to the JSON body for POST/PUT, as in 02 section 5) and calls the route's existing handler from the serving `RouteTable`. Status, headers and body are therefore what the legacy route returns (legacy renderer).
* **One decision source.** `Policy.from_engine` wraps the in-flight `PolicyEngine`. `admit` runs the same gate the v1 dispatcher runs for the operation's route (group gate, rule enabled, scopes, rate bucket, concurrency slot, path rules through the same `EndpointContext`), so a rate bucket is shared between `GET /system/info` and `POST /ops/system.info`. Without an engine, `Policy.open` reproduces v1: legacy token plus group gate.
* **Pipeline order.** 401 before any 404 (`core.health` is anonymous); unknown, disabled and not-granted operations are one `404 op.not_enabled`; a missing scope is the engine's 403 body; limits are 429 with `Retry-After`. `Authorization: Bearer` and `X-Access-Token` are both accepted on `/ops` (D16); duplicate or conflicting credentials are refused.
* **Mounting.** `app.py` gained one hook inside the existing "no route matched" branch: `core.http.serve_ops` handles `POST /ops/{id}` and `GET /ops` and otherwise returns `False`, so a v1 route (even one a user registered under `/ops/...`) always wins and every other 404 is unchanged. The route table is not touched: `test_policy_config` requires every default-table route to have an `ENDPOINT_CATALOG` entry, and a `/ops` route in the table would be governed as a v1 endpoint.
* **Discovery.** `GET /ops` and `POST /ops/core.describe` return the operations effective for the caller (`api`, `catalog_version`, `revision`, `principal`, `policy`, `ops[]` with effects, bindings, params, aliases, and the rule's limits and scopes). Unmounted operations are not listed (no oracle). `GET /capabilities` is a v1 route and keeps its v1 body.
* **Native operations stay closed.** Operations without a v1 route are mounted only when listed in `NATIVE_OPEN_IDS` (`core.describe`): the legacy engine has no rule for them, so mounting an `@op` handler now would bypass policy. They open with the v2 rule model (WP-2).
* **Route coverage today: 59 operations** (58 default-table routes minus the `POST /commands/{name}` alias family, plus `core.describe` and the WebSocket-only `terminal.connect`; `custom.<name>` operations are added per `CommandRegistry` entry). Routes the mapping does not know become `ext.<name>` (admin, explicit-only); unknown `agents_*` routes get `agents.<a>.<b>`. IDs for the 11 agents routes present at the start follow 04 section 11 (`agents.sessions.send_event`, `agents.sessions.stream_events`, `agents.sessions.list_items`, `agents.runtimes.list`, ...). The agents owner has since added about 60 routes (definitions, environments, vaults, webhooks, responses, ...): they are picked up automatically with mechanical IDs and `admin` effects (fail closed, explicit-only, `effects_declared=False`), 118 operations in total at the time of writing. Mapping them to the final 05 IDs and effects is a follow-up that needs the agents owner (several mechanical IDs such as `agents.cannot.*` and `agents.webhook.event.types` are placeholders).

## Alternatives considered
- Register `/ops` as a route in the default table. Rejected: breaks the catalog completeness test and makes the discovery call subject to a v1 endpoint rule.
- Convert `policy.py`/`guard.py`/`runtime.py` to `policy/`, `guards/` packages now. Rejected for this pass: the plan says they cannot coexist and re-export every imported name; `Policy.from_engine` needs none of that.
- Module-level `@op` that registers into the served registry. Rejected until WP-2 (see "Native operations stay closed").

## Dependencies
Design 02, 03, 04, 10 (stages S1 and S2). Owners of `routes_agents.py` and `agents/**` are unaffected: operation IDs are derived from the route table at call time.

## Test Strategy
`tests/test_server/test_ops_registry.py` (grammar, tree, registry rules), `test_ops_legacy.py` (every route covered, pinned IDs, `ext.*`, mangling, wrappers), `test_ops_policy.py` (`peek` equals `admit` for every operation and several policies, shared buckets and slots, native closure, argument validation), `test_ops_http.py` (status/body parity with the legacy route for files, shell, SSE stream, custom commands, path rules, 401 before 404, one `op.not_enabled` shape, discovery, audit, route precedence, shared rate limit). The existing `tests/` suite is unchanged and green.

## Not done in this pass
- Allow/deny rule model, selectors, scopes, presets, hooks (WP-2); `guards/` (WP-3); `builtin/<ns>.py` handler modules (WP-4*; wrappers live in `core/legacy.py` because `builtin/` is outside this pass's ownership); `core.openapi`, `core.reload`, `core.check` v2 body, `GET /ops?all=1`; `/capabilities` union body (IF-26); step-0 transport order of 02 section 6.
- Public re-exports (`ops`, `op`, `Policy`, ... in `easy_sandbox.server.__all__`) are integrator-owned; `from easy_sandbox.server.core import ops, Policy, Registry` works today. `default_registry` keeps its v1 meaning (`CommandRegistry`); the operation registry is `core.default_op_registry()`.
- E-codes are unchanged (the client-side `E9000-E9005` to `E3100-E3111` rename is not part of S1/S2 and no existing test expects `E3100`).
- Op parameter names are the v1 wire names (`files.move` takes `source`/`destination`, not the design's `src`/`dst`); renaming belongs to the S3 handler move with a compat renderer.
- Baseline: the design quotes 308 collected tests; the tree at the start of this pass collected 584 (578 passed, 5 failed, 1 skipped). The 5 failures are `test_routes_pty.py::TestPtyWebSocket` (`pytest-asyncio` is not installed here). The `tests/BASELINE.json` and v1 replay fixtures of WP-A do not exist yet.
- Real-component gate: exercised with a real listener and `http.client` (and a raw socket for header cases); the real `ServerClient` was not run. Record under `.agents/evidence/verify/` when WP-1 closes.

## Acceptance criteria
- `pytest server-sdk/tests` shows no new failure; the new `test_ops_*.py` pass.
- Every route in the default `RouteTable` is an operation or a documented alias family; adding a route to a table adds an `ext.*` operation without code changes.
- For every tested operation, `POST /ops/{id}` returns the same status and body as the legacy route, under no policy and under a token policy.
