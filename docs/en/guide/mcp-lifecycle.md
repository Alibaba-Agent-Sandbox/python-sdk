# MCP sandbox lifecycle tools

The Python MCP server exposes fifteen tools: the seven execution and file tools described in
[MCP Integration](mcp-integration.md), plus `list_sandboxes`, `get_sandbox`, and
`set_sandbox_timeout`, the three [background task tools](mcp-background-tasks.md), and two
[binary transfer tools](mcp-binary-files.md). They reuse existing SDK APIs; provider support and platform
permissions still apply. This page covers lifecycle management, not Team administration
or the complete MCP/Skills product roadmap.

## Discover and inspect

`list_sandboxes` lists sandboxes visible to the configured account and provider. It does
not create sandboxes, choose a default, or register listed sandboxes for session shutdown.
Optional arguments are `status` (a `SandboxStatus` value), `limit` (1–100, default 100),
`offset` (nonnegative integer, default 0), `provider`, and `region`. Increase `offset`
to request another page; the result does not promise a total count or next-page cursor.

```json
{"name":"list_sandboxes","arguments":{"status":"running","limit":10,"offset":0}}
```

`get_sandbox` calls `Sandbox.refresh_info()` for managed instances and
`Sandbox.get_info_by_id()` for external IDs to fetch current platform metadata. Supply
`sandbox_id` to inspect a particular sandbox, or omit it to inspect the existing session
default. With no default it returns a tool error; inspection never creates a sandbox or
extends its lifetime. Explicit IDs leave the default unchanged. Use the SDK's qualified
`provider:sandbox_id` syntax when selecting another provider. Inspecting an ID outside
the session uses temporary control-plane infrastructure closed in `finally`. It
dispatches directly to the provider metadata method, never to connect/resume, and
does not adopt that sandbox into session shutdown cleanup.

```json
{"name":"get_sandbox","arguments":{}}
```

Both metadata tools return only `sandbox_id`, `template`, `status`, `region`, `started_at`,
`end_at`, `cpu_count`, `memory_mb`, and `disk_size_mb`. Times are ISO 8601 strings or null;
missing resource values are null. They omit access tokens, environment variables, account
identifiers, user metadata, arbitrary lifecycle objects, and endpoint URLs. Listing wraps
these objects in `sandboxes`, alongside the requested `limit` and `offset`.

## Create and extend

`create_sandbox` accepts the existing `template`, `timeout`, and `envs` arguments, plus
`region`, `cpu` (positive integer cores), `memory` (positive integer MB), and `provider`
(a configured provider ID). Omitted options preserve SDK/provider defaults. The backend
enforces resource combinations; passing input validation does not guarantee availability.
Team selection is not exposed because the SDK has no corresponding parameter.

```json
{"name":"create_sandbox","arguments":{"template":"base","timeout":600,"cpu":2,"memory":2048}}
```

When `cpu` or `memory` is explicit, the current source verifies each requested value
against newly refreshed platform metadata before reporting success. This correction
is newer than public 0.4.0a6. Unknown or mismatched values return a tool error with
`category: "resource_configuration"`, `requested_resources`, `observed_resources`
and `cleanup_verified`. Both verification and rollback keep the exact newly created handle even if the session closes or its cache changes. Only that newly created sandbox is rolled back. Cleanup uses a fresh control plane with the created instance's resolved provider, endpoint, region and credentials; a different default region cannot confirm absence. A typed
not-found or HTTP404 readback confirms cleanup; an ambiguous response retains a
provider-qualified `recovery_sandbox_id` for explicit cleanup. This does not change
the direct SDK `Sandbox.create` contract. `region` still follows provider endpoint
configuration; it is not a verified CPU/memory override.

Creation makes that sandbox the default. Keep secrets in the MCP process's authorized
configuration; tool arguments and results may be visible to the connected model.

`set_sandbox_timeout` requires an integer `timeout` in 1–86400 seconds. It sets lifetime
from now, not HTTP request timeout. Optional `sandbox_id` resolves to the existing default;
it never implicitly creates a sandbox. Successful `Sandbox.set_timeout()` also updates the
session renewal policy: subsequent execution/file tools renew using this duration. A failed
platform update leaves the previous policy intact.
If the session closes while an update is in flight, its completion does not restore
renewal ownership or recreate a cleared session entry.
For an explicit ID outside the session, only the platform timeout is changed: the
`Sandbox.set_timeout_by_id()` call uses temporary control-plane infrastructure
closed in `finally`, without an additional connect/resume operation or shutdown ownership.

```json
{"name":"set_sandbox_timeout","arguments":{"timeout":600}}
```

Success returns `{"success":true,"sandbox_id":"...","timeout":600}`. Invalid integers
(including booleans), out-of-range limits/timeouts, empty explicit IDs, and unsupported
lifecycle arguments return a tool error before platform calls. Creation also validates
resource integers and string-valued `envs`. Provider/API failures return `isError: true`.

Lifecycle errors expose a fixed failure category, an HTTP status when available, or
an SDK error code with a static recovery suggestion. Raw provider messages, request
URLs, response-validation inputs, and exception tracebacks are omitted from both
tool results and the MCP lifecycle error log. Input validation names the invalid
field without echoing its value.

## Implementation and verification

Listing delegates to `Sandbox.list`. Managed inspection/renewal use `refresh_info`
and `set_timeout`; external IDs use direct `Sandbox.get_info_by_id` and
`Sandbox.set_timeout_by_id` methods, with no new platform endpoints. Their
`get_info_by_id_sync` / `set_timeout_by_id_sync` variants are available as well.
The new static methods accept the same credential, region and provider overrides
as `Sandbox.kill_by_id`; qualified `provider:id` references select the provider.
These lifecycle methods use the control-plane API URL without an envd client; they do not accept `sandbox_domain`. Schemas and handlers are shared by the
Python STDIO and Streamable HTTP servers. The Node.js CLI has its own MCP implementation;
availability there must be checked separately.

Unit coverage in `client-sdk/tests/test_agent/test_mcp_lifecycle.py` includes boundaries,
SDK delegation, default selection, renewal failures, and metadata disclosure checks.
Mocked tests do not establish real provider support; cloud results must be recorded
separately in repository evidence. See the
[official MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

## Borrowed connections and session shutdown

This source revision tracks creation ownership separately from cached connections.
Execution/file tools may connect to an explicit external ID with the configured
account authority. That connection is borrowed: deleting the borrowing HTTP
session, closing STDIO or reaching idle timeout closes only its client handle.
The manager deletes its own creations unless an explicit background task retained
them until platform TTL. Explicit authorized `kill_sandbox` remains destructive.

This correction is newer than public 0.4.0a6. Do not infer that sessions sharing
one account credential provide a tenant authorization boundary; use separate
credentials/Teams or application authorization for distinct users.

The manager keys cached ownership, TTL and retained tasks by the actual provider
and sandbox ID. If two providers return the same raw ID, explicit access must use
`provider:id`; an ambiguous bare ID is rejected. Aliases cannot replace an owned
handle. A session closed during creation/connection stays closed: a late created
sandbox is deleted and a late borrowed connection is closed.
