# Reconciliation: fine-grained-capabilities implementation -> server-sdk v2 work packages

Author: capabilities / client-alignment worker. Status: input to WP-0 .. WP-13 owners. Nothing here edits v2 docs.
`v2.1-disposition.md` did not exist when this was written; re-check the mapping against it once it lands.

Sources: [10-implementation-plan.md](../10-implementation-plan.md) (layout, WP table, section 9),
[independent-feasibility.md](independent-feasibility.md) (sections 4-5), and the flat implementation committed on
`cursor/fine-grained-capabilities-5e91` (`fea9a3c`, `550c7ef`, `6932ef1`, client `f2153d7`) plus the uncommitted
working-tree doc/export edits.

Rule for everyone: `policy.py`, `guard.py`, `runtime.py` are **frozen** (stabilising fixes only). They are the
donor code for WP-1/2/3; they are not extended. Legend: **KEEP** = reusable as-is (move/import), **PORT** = reusable
logic, rename or re-home, **REPLACE** = superseded, delete after WP-5 passes.

Current baseline (verified this turn, local virtualenv): server `-m "not integration"` = 581 passed + 1 env-only
failure (`TestPackages::test_pip_returns_structure`, venv has no pip). `server/__init__` imports; `app.py` imports
`routes_agents` so the Agents HTTP routes register, and `server/agents/` is present. One race fix is uncommitted in
`routes_process.py` (`process_output` waits while `capture.readers > 0`); keep it when WP-4b rewrites the handler.

## 1. Server source

| File / class | v2 WP | Disposition | Notes |
|---|---|---|---|
| `policy.py` `ServerPolicy`, `EndpointRule`, `PathRules`, `Limits` (dataclasses) | WP-2 `policy/model.py` | PORT | Field names `enabled/scopes/paths/limits/params/audit` map to v2 rule keys; ids become dotted (`files.read`), legacy ids kept as aliases. |
| `policy.py` strict loader (`from_mapping`, unknown-key rejection, `SERVER_POLICY_TOP_KEYS`) | WP-2 `policy/loader.py` | KEEP logic | Reuse the fail-closed validation. Client mirror `validate_server_block` shares the key sets; keep both in lock-step (IF-31: block is `extra="forbid"`). |
| `policy.py` presets `default/transfer-only/read-only/hardened/locked` | WP-2 `policy/presets.py` | PORT + rename | Snapshot into `tests/golden/presets.json`; `transfer-only` becomes `transfer_only` (accept both). Scopes stay as sugar over ids. |
| `policy.py` `PolicyDenied` (exported from `server/__init__`) | WP-1 `core/errors.py` | PORT | Becomes the v2 denial type; keep the export through `compat/`. |
| `policy.py` `PolicyEngine.admit` (enabled, scopes, rate, concurrency) | WP-2 `policy/engine.py` + WP-1 `core/limits.py` | PORT, split | Decision logic -> engine (add deny-overrides, principals, Narrow). Token buckets and concurrency caps -> `limits.py`. |
| `guard.py` `PathGuard` (+ `open_checked`) | WP-3 `guards/paths.py` (`resolve_path`, `open_beneath`) | PORT | Keep the no-existence-oracle behaviour and the full bypass cases. **Audit before porting**: any `open(..., O_TRUNC)` before the containment check must become `open_beneath` + truncate after verify; re-run spikes attack1-3. |
| `guard.py` child-env scrub | WP-3 `guards/launcher.py` / WP-4b | PORT | Extend to env masking per WP-4c; current version only drops the server's own secrets. |
| `runtime.py` `EndpointContext`, audit writer, discovery payload | WP-1 `core/{context,audit,dispatch}.py` | PORT, rename | `EndpointContext` -> `OpContext`; discovery (`/capabilities`) becomes `core.describe` + legacy renderer in `compat/`. |
| `contract.py` constants (env var names, `POLICY_FILE`, ports) | WP-0 / WP-9 | PORT | `POLICY_FILE` -> `server.json` (read old name as fallback); keep `EBX_SERVER_POLICY*` as aliases of the `EBX_SERVER_CONFIG` family. |
| `__main__.py` (serve / healthcheck / check-policy / version) | WP-9 `cli/` | PORT | Keep the 4 subcommands and exit codes; add describe/prepare/doctor; `--commands` becomes a `--load` alias. |
| `router.py` (`RouteTable.copy()`, duplicate-query / TE rejection hooks) | WP-1 `core/router.py` | PORT | `copy()` per-server group state is the property to preserve in the trie router; hardening tests pin it. |
| `registry.py` (`CommandRegistry`) | WP-5 `compat/` -> `custom.*` | REPLACE via shim | Unchanged API through `compat`; scheduled behaviour in 02/04. |
| `app.py` pipeline (match, auth Bearer then `X-Access-Token`, group gate, admit, body cap, handler, audit) | WP-1 `core/{dispatch,http}.py` | PORT order, rewrite code | Order is already v2's (401 before 404, size cap before read). Legacy renderer stays in WP-5 for response shapes. |
| `routes_files.py` edits (policy hooks, search/list re-check, archive symlink hardening, `files.watch`, `files.check`) | WP-4a `ops/files.py` | PORT | Hardening fixes (Content-Length, archive symlinks) are regression-tested; carry the tests. `watch` is the new `files.watch`. |
| `routes_process.py` edits (`process.stdin`, `process.output` with `since`, ownership) | WP-4b `ops/process.py` | PORT | Includes the uncommitted `readers > 0` fix. |
| `routes_pty.py` edits (`terminal.list/get/resize`, policed upgrade) | WP-4b `ops/terminal.py` | PORT | Policy check before WebSocket upgrade is already tested (`test_policy_pty.py`). |
| `routes_system.py`, `routes_devtools.py`, `routes_browser.py` edits (policy hooks only) | WP-4c / WP-4d | PORT | Mechanical; `guards/urls.py` is new in WP-4d (no donor). |
| `server/__init__.py` (+ `PolicyDenied`, `ServerPolicy` exports) | WP-0 / WP-5 | KEEP via compat | WP-0 owns `__init__`; re-export from `compat/` so both old and new imports work. |
| `server-sdk/pyproject.toml` console script `easy-sandbox-server` | WP-0 | KEEP | `[project.scripts]` entry is referenced by the base-image start/ready commands. |

## 2. Server tests (`server-sdk/tests/test_server/`)

| File (count) | v2 WP | Disposition |
|---|---|---|
| `test_policy_config.py` (54) | WP-2 `tests/test_policy/` | PORT; rename ids/codes (`policy.path_not_allowed`, `op.not_enabled`); add golden preset snapshot. |
| `test_path_guard.py` (34) | WP-3 `tests/test_guards/` | KEEP as the seed of the bypass matrix; add property/fuzz and `open_beneath` race tests. |
| `test_policy_pipeline.py` (38) | WP-1 `tests/test_dispatch/` + WP-2 | PORT; pipeline-order assertions are directly reusable. |
| `test_policy_paths.py` (30), `test_policy_exec.py` (16) | WP-3 / WP-11 `tests/bypass/` | KEEP as bypass cases; each gets an attack/expected-code/regression note. |
| `test_http_hardening.py` (18) | WP-1 + WP-11 | KEEP (smuggling basics, duplicate headers, TE, size cap). |
| `test_new_endpoints.py` (15) | WP-4a/4b/4c | KEEP behaviour; move beside `ops/*` tests. |
| `test_policy_pty.py` (7) | WP-4b | KEEP. |
| `test_policy_compat.py` (5) | WP-5 | KEEP: asserts default behaviour is unchanged (legacy preset). |
| `test_cli_main.py` (8) | WP-9 `tests/test_cli/` | PORT with new subcommands. |
| `_live.py`, `conftest.py` (in-process `SandboxServer` helpers) | WP-11 `tests/fakes` | KEEP; the real-server fixture is what the client mirror tests also use. |
| Legacy tests (297/308, other owners) | WP-5 | Not mine; they must pass **unmodified**. My tests that exercise the legacy preset belong beside them. |

## 3. Client SDK (`client-sdk/src/easy_sandbox/`, WP-10 + WP-12 + WP-8)

| File / class | v2 WP | Disposition | Notes |
|---|---|---|---|
| `api/server_client.py` `ServerClient` + sub-APIs (`ENDPOINT_METHODS`: 48 ids -> 59 methods, all with `*_sync`) | WP-10 `api/server/*` (generated) | PORT as the hand-written reference | Generator output must keep the public method names/sync twins; `ENDPOINT_METHODS` becomes generated from `catalog/operations.json`. `commands` sub-API maps to `custom.*` / `commands.run`. Parity guard: `server_e2e/test_server_client_matrix.py`. |
| `api/server_capabilities.py` `ServerCapabilities` (`can/denial/require/info/limit/param/paths/endpoints_for/available/check_path`) | WP-10 `ops.py` / `core.describe` client | PORT | No-hidden-traffic contract kept (explicit `discover()`, server authoritative). `check_path` -> `check` (keep alias); denial strings `endpoint_disabled/group_disabled/unknown_endpoint/missing_scope` map to `op.not_enabled`, `group.disabled`, `op.unknown`, `scope.missing`. |
| `models/server.py` (response models) | WP-10 | KEEP | Regenerate from catalog schemas; legacy field names preserved. |
| `models/errors.py` E9000-E9005 | WP-10 error mapping | KEEP, reconcile | One table: E9000 API, E9001 auth, E9002 policy denied, E9003 not available, E9004 too large, E9005 rate limited. E8xxx (providers) and any E31xx proposal must not collide; update table tests. |
| `models/template.py` `SandboxTemplate.server` + `validate_server_block` and key sets | WP-10 `models/_server_config.py` | PORT | Move key sets into the shared generated config model; keep `extra="forbid"` and the preset names. |
| `api/sandbox.py` `server` / `server_at` / `start_server` | WP-10 | KEEP | |
| `api/base_image.py`, `Image.official_base`, `_lint_dockerfile` B001-B005 | WP-12 (docs/templates) + WP-8 (install) | KEEP | Independent of v2 layout; `Image()` default stays `ubuntu:22.04`. |

Client tests (`tests/test_api/server_e2e/`: e2e 33, policy 18, models 23, matrix 4, helpers 12; `test_base_image.py` 52;
`tests/test_models/test_template_server_block.py` 18) -> WP-10. Keep them; they run against a real in-process
`SandboxServer`. Add to the repo-root `tests/contract/` the per-op ledger (`client_parity.json`: op id -> client
method or documented asymmetry) once WP-0's catalog exists. Rows the feasibility review lists as "NO CLIENT" are
already covered by `ServerClient`; the genuine gaps are `core.describe`, `core.openapi`, `core.reload`, `ext.*`
(v2-only ops with no legacy route) and the agents ops (agents worker).

## 4. Docs I produced (WP-12)

`docs/{en,zh}/design/{fine-grained-capabilities,fine-grained-capabilities-review}.md`, `client-server-alignment.md`,
`base-image-and-server-sdk.md`, `cli-followups.md`; `docs/{en,zh}/reference/{error-codes,api-reference,template-yaml-spec}.md`
sections; `docs/{en,zh}/guide/sdk-usage.md`; `docs/{en,zh}/design/server-api.md` section 10; CHANGELOG "Unreleased".
Disposition: add a "Superseded in part by server-sdk-v2" banner to the fine-grained design docs when WP-12 starts
(plan 9a); leave `cli-followups.md` as the CLI contract, to be re-expressed over the `cli/src/server/*` mirror in WP-10.

## 5. Recommended order

1. **WP-0** freezes `Operation`/ids/catalog; no donor code needed. Stabilise only: keep the three flat modules as they are.
2. **WP-3** first (no dependency): port `guard.py` + `test_path_guard/test_policy_paths/test_policy_exec` into `guards/`; do the `O_TRUNC` audit; re-run attack1-3.
3. **WP-2**: port `policy.py` + `test_policy_config`; add golden presets and deny-overrides/principals.
4. **WP-1**: port `runtime.py`/`app.py` pipeline + `test_policy_pipeline/test_http_hardening`; legacy renderer stays.
5. **WP-4a/b/c/d**: re-home route edits one group at a time, each green against the unmodified legacy tests.
6. **WP-5**: move the 297 legacy tests unchanged plus `test_policy_compat`; delete the flat modules only after green.
7. **WP-9** (CLI) then **WP-10** (generator + client mirror; my client tests are the oracle), **WP-11** (bypass matrix CI), **WP-12** docs, **WP-13** gate.

## 6. Risks specific to this donor code

- Flat `ServerPolicy` rule keys are strict; v2 ids are dotted. Accept both in the loader for one release, or existing `server:` template blocks break (default behaviour must stay backward compatible).
- `/capabilities` is `auth_required=True`; v2 `core.describe` must not silently become unauthenticated.
- The in-process server fixtures start real servers; keep ports ephemeral and the `routes_process` race fix when moving handlers.
- Role-played review disclosure: the two "review rounds" in `fine-grained-capabilities-review.md` were performed by the same worker; the v2 independent reviews supersede them and a third truly independent pass is still needed before GA.
