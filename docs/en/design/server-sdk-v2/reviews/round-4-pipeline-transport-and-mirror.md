# Review round 4: pipeline order, transport bounds, backward compatibility, client mirror, numbers

> Part of [Server SDK v2](../README.md).

**Target**: docs 01-10 after rounds 1-3 (10 written in this round).
**Lenses**: security (end-to-end request path), backward compatibility (rollout and rollback), client mirror, completeness (numbers and cross-references), feasibility of
the work-package split.
**Method**: `tests_round4.py` (transport, auth ordering, config loader), a recount of the official API from the real `openai` 3.29.0 wheel, a re-derivation of
the 41 legacy routes from source, and a read of 07/10 against the client source.

## Findings

| ID | Sev | Lens | Finding | Evidence | Resolution | Where fixed |
|----|-----|------|---------|----------|------------|-------------|
| S4.1 | M | security | **Unbounded memory**: body size was only a per-op limit applied after reading; `threads x body size` was unbounded, so an unauthenticated caller could exhaust memory | `tests_round4.py` "oversized body rejected before read" | `Content-Length` cap checked **before** reading; `max_connections` (64, excess `503`); stream ops default `concurrency=8`; per-op `max_bytes` x 4/3 for base64 ops | [03](../03-policy-and-permissions.md) section 9 |
| F4.2 | M | security | **Alias resolution before authentication**: `/v1/...` and `POST /commands/{name}` aliases resolved (and could 404 differently) for unauthenticated callers, a route oracle | pipeline walk-through | Reordered: authenticate (step 3) precedes alias resolution (step 4) and every 404; alias resolvers may then peek at the size-capped body; resolved to a concrete op **before** authorization | [02](../02-operation-model.md) section 6 |
| F4.3 | M | completeness | Official-API count had been quoted as "18/7/6/16" in an earlier note; the tier table must sum to 47 and every op must be placed | recount from the wheel | **19 implemented / 7 later / 6 static refusals / 15 not planned = 47**; tier-3 and not-planned are static refusals (not ops) | [05](../05-agents-api.md) sections 1, 4 |
| F4.4 | M | compat | A dispatch rewrite with no rollback: if the new pipeline regresses a deployment, there is no way back without a downgrade | rollout review | `EBX_SERVER_LEGACY_DISPATCH=1` routes through the compat dispatcher with the v1 route table for one minor version; documented as an escape hatch, not a mode | [10](../10-implementation-plan.md) section 6 |
| F4.5 | M | compat | `SandboxServer`/`start` signatures: new parameters could have broken positional callers | signature diff against the pristine copy | `SandboxServer(host, registry, route_table, pty_port)` and `start(port, host, registry)` keep positional order; everything new is keyword-only; `auth_token` property kept | [10](../10-implementation-plan.md) section 2 |
| F4.6 | m | feasibility | Hot reload semantics were underspecified (mid-request policy swaps) | pipeline review | Off by default; opt-in SIGHUP; immutable **policy snapshot** captured at step 1 and an atomic swap with a `revision` hash for new requests only | [03](../03-policy-and-permissions.md) section 10; [02](../02-operation-model.md) section 6 notes |
| F4.7 | m | client mirror | `ServerCapabilities` could cause hidden requests (auto-discovery) | 07 read | Contract kept: no traffic unless the caller calls `discover()`; generated tree works without it; dynamic fallback from `GET /ops` only on explicit use | [07](../07-client-mirror.md) section 3 |
| F4.8 | m | client mirror | Drift between the server catalog, Python client, and Node CLI client had no owner | 07/10 read | Generated artefacts committed; drift tests at the repository root (`tests/contract/`, `tests/gen_check/`); WP-10 owns them | [07](../07-client-mirror.md) section 2; [10](../10-implementation-plan.md) WP-10 |
| F4.9 | m | feasibility | WP file ownership overlapped (`__init__.py`, `pyproject.toml` shared) | WP table | Shared files owned by WP-0 and changed through PRs to its owner; interface freezes listed | [10](../10-implementation-plan.md) sections 3, 4 |

## Lens notes (no finding)

* 41 legacy routes still equal the source (`tests_catalog.py`), 152 ops registered in the default registry with five adapters.
* `core.health` is anonymous by default and cannot leak anything but liveness.
* Read-only filesystems and the Alibaba Cloud base image: tools directory order and fallback to `/tmp` verified on paper in [06](../06-lazy-install.md) section 10; no
  code to run in a spike.

## Exit status

All M findings resolved. Material findings were found in this round, so round 5 is a **full regression round** across all lenses with the final documents.
