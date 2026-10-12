# Review round 2: backward compatibility, completeness, developer experience

> Part of [Server SDK v2](../README.md).

**Target**: docs 01-09 after round-1 fixes, compared against the **pristine legacy source** (a checkout of the pre-redesign server source, `EBX_LEGACY_SRC`) and the real client
(`/workspace/python-sdk/client-sdk`).
**Lenses**: backward compatibility, completeness (against the seven product requirements), DX, client mirror (first pass).
**Method**: `tests_catalog.py` extracts the legacy routes from the source and compares them to the design catalog; the client method names were checked
against the client source line by line.

## Findings

| ID | Sev | Lens | Finding | Evidence | Resolution | Where fixed |
|----|-----|------|---------|----------|------------|-------------|
| F2.1 | M | compat | The legacy server **already jails** file paths to `EBX_SERVER_BASE_DIR` (`_resolve_safe_path`); the draft's `legacy` preset had no jail, which would have been a silent privilege **widening** for every existing deployment | source read | `presets.legacy()` carries `PathScope(roots=BASE_DIRS)` on every `files.*` op and on `cwd` of command ops; documented as non-optional | [04](../04-builtin-modules.md) section 1; [03](../03-policy-and-permissions.md) section 4 |
| F2.2 | M | compat | Existing tests (297) and deployed clients assert the **v1 error shape** (`400 ValueError ... traversal`); a new `403 PolicyDenied` would break them | source and tests read | Compat renderer under the `legacy` preset: v1 status and message plus the new `code` key; explicit policy renders new statuses; RPC always new | [03](../03-policy-and-permissions.md) section 11 |
| F2.3 | M | security / compat | A 403 for an op the principal is not granted leaks that the op exists (oracle); the draft returned 403 | pipeline review, `tests_proto.py` | Mounted check is **principal-filtered**: not granted means `404 op.not_enabled` with a byte-identical body for "never existed" and "not granted"; the old test expectation was updated | [02](../02-operation-model.md) section 6; [03](../03-policy-and-permissions.md) section 3 |
| F2.4 | M | completeness | `limit.*` violations were rendered as 403, which clients read as "not allowed" instead of "too big / slow down" | design review | `limit.*` renders **413** (size, entries, output) and **429** (rate, concurrency) with `Retry-After` | [03](../03-policy-and-permissions.md) sections 9, 11 |
| F2.5 | M | cross-worker | Worker (a) proposed client exceptions `E8000-E8005`; worker (c) owns `E8000-E8030` | doc comparison | Server-plane family is `E3100-E3111` (next to the existing execution errors) | [07](../07-client-mirror.md) section 4; [10](../10-implementation-plan.md) 9a item 6 |
| F2.6 | M | client mirror | The parity table used method names that do not exist in the client (`mkdir`, `info`, `move`, `stdin`, ...) | client source read | Rewritten against real names (`make_dir`, `get_info`, `rename`, `send_stdin`, `get_terminal`, ...) | [07](../07-client-mirror.md) section 6 |
| F2.7 | m | completeness | The agents examples used invented `openai` SDK parameter names | official wheel inspected | Examples use `agents.create(model=...)`, `sessions.create(agent_id=..., environment={"type": "self_hosted", "workspace_directory": ...}, input=...)` | [05](../05-agents-api.md) section 12 |
| F2.8 | M | cross-worker | Name clash: worker (a) used `server.commands.*` for custom commands; the shell op is also called `commands` | doc comparison | Custom commands are `custom.<name>`; `commands.run` is the shell op; reconciliation item for worker (a) | [04](../04-builtin-modules.md) section 10; [10](../10-implementation-plan.md) 9a item 2 |
| F2.9 | m | completeness | The brief called the `KEEP = {("GET", "/health"), ...}` pattern unreasonable; it does **not exist** in the repo's source | full-text search of the pristine copy | Recorded as an anti-pattern (hand-kept route sets that drift from the registry); the registry generates the legacy bindings and a test equals them to the source | [01](../01-principles.md) rule R1 |
| F2.10 | m | compat | Needed an exact, verified count of legacy routes | `tests_catalog.py` | **41** legacy routes, all mapped to an op ID with `http=` bindings that preserve method and path | [04](../04-builtin-modules.md) sections 3-10 |
| F2.11 | m | DX | Only experts could tell which ops a preset enables | design review | `describe`/`explain` and golden group lists (no privilege creep when new ops arrive) | [04](../04-builtin-modules.md) section 12 |

## Lens notes (no finding)

* Positional order of `SandboxServer(host, registry, route_table, pty_port)` and `start(port, host, registry)` is preserved; new parameters are keyword-only
  ([10](../10-implementation-plan.md) section 2).
* `from easy_sandbox.server import SandboxServer, start, enable_builtin, CapabilityGroup` keeps working through shims (WP-5).

## Exit status

Seven material findings (F2.1-F2.6, F2.8) resolved in the docs; spike tests updated (principal-filtered 404). A further round was required.
