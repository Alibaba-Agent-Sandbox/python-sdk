# Decision: one endpoint table, one policy engine, one dispatch pipeline

Status: implemented

## Problem
The server had three overlapping mechanisms: the route table plus a capability-group gate, a per-endpoint policy engine on top of it, and an operation layer (`core/`, `POST /ops/{id}`) that wrapped both with a second id space. Capability switches existed at two layers (group gate and endpoint rule), handlers had an unscoped branch for "no policy", and the same decision was written three times.

## Decision
* `server/endpoints.py` holds the only declaration: `ENDPOINTS` (id, method, path, group, scopes, limits). `RouteTable.mount(name, handler)` binds handlers to it. Policy, audit, `/capabilities` and the client use endpoint ids.
* One engine (`PolicyEngine`). Layers: default < code (`enable_group`/`disable_group`) < preset < policy < env (`ABX_SERVER_ENABLED_GROUPS`, enable only). A group is an alias that expands to endpoint ids; the most specific selector wins; every denial names the rule.
* One pipeline (`SandboxRequestHandler._pipeline`): match, authenticate, admit, duplicate-query check, body limit, handler, audit. The engine is always present (no policy means an empty policy) and handlers always receive an `EndpointContext`.
* Deleted: `core/` and `POST /ops/{id}`, `enable_builtin`/`disable_builtin`, `ABX_SERVER_DISABLED_GROUPS`, the unscoped handler mode, `legacy_codes`.

## Alternatives considered
* Keep `/ops` with dotted ids as bindings over the table. Rejected: a second id space needs a mapping layer and nothing used it.
* Keep group switches as a separate layer. Rejected: two places to look when a call is denied.

## Test Strategy
`tests/test_server/test_single_layer.py`, `test_policy_pipeline.py`, `test_policy_config.py`, `test_routes_agents_local.py::TestEveryRoute` (every agents route).
