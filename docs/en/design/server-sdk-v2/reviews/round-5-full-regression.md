# Review round 5: full regression with the final documents

> Part of [Server SDK v2](../README.md).

**Target**: the final documents 01-10, README and spikes, exactly as committed.
**Lenses (all seven)**: feasibility, completeness, DX, AI-consumer, security, backward compatibility, client mirror.
**Method**: nothing was taken from memory of earlier rounds. Everything checkable was re-executed against the committed tree:

| Check | Command (from `spikes/`) | Result |
|---|---|---|
| Registry, policy algebra, guards, dispatch, discovery | `python3 tests_proto.py` | 36 / 36 |
| Catalog vs legacy source (41 routes equal), grammar of all IDs, explicit-only ops, 152 ops | `python3 tests_catalog.py` | ALL OK (non-agent 50, total 152) |
| Transport bounds, 401 before 404, config loader | `python3 tests_round4.py` | ALL OK |
| Exploit demos (TOCTOU intact, deny-list limits documented, deny beats allow, list-valued path, newline path) | `attack1.py`, `attack2.py`, `attack3.py` | outputs as documented in rounds 1-3 (demonstrations, see spikes README) |
| AI-consumer scenarios S1-S8 | `ai_consumer/s*.py` | 10, 11, 10, 8, 4, 6, 5, 5 = 59 / 59 |
| Every dotted ID quoted in backticks in docs 01-10 exists in the catalog or is a namespace prefix | script over the markdown | 0 unknown IDs; remaining hits are client method names, parameters, or error codes (`files.read`, `commands.start`, `files.archive.sources`, `agents.not_planned`, ...) |
| Cross-reference audit (`section N`, markdown links, file names) | grep and manual read | 1 stale reference fixed (below) |
| Leftover superseded terms (`env_allow`, `auto` mode, `E8xxx` as ours, `provider:` for models) | grep | only in "history/fixed" sentences |

## Findings

| ID | Sev | Lens | Finding | Resolution |
|----|-----|------|---------|------------|
| H5.1 | m (hygiene) | completeness | [04](../04-builtin-modules.md) pointed to "section 12" for explicit-only ops; that section is the golden group lists | Now points to [03](../03-policy-and-permissions.md) section 2 |
| H5.2 | m (hygiene) | completeness | [02](../02-operation-model.md) claimed the spike registry is 120 lines; it is about 170 | Corrected |
| H5.3 | m (hygiene) | DX | Spike scripts hard-coded `/tmp/ssd-proto` | Made path-independent; re-run from `docs/.../spikes/` (table above) |
| H5.4 | m (hygiene) | DX | Spike README did not say that the `attack*.py` output lines include deliberately unsafe outcomes of naive designs | Added "demonstrations, not tests" section; WP-3 converts them into asserting tests |
| H5.5 | m (scope) | AI-consumer | The card lists `start`, `AgentScope`, `UrlScope` that the spike facade does not implement | Recorded in the spikes README as not prototyped; they are covered by WP-1, WP-6, WP-4d with tests in [10](../10-implementation-plan.md) section 5 |

No material finding. No finding changes a normative statement.

## Lens verdicts

| Lens | Verdict | Basis |
|---|---|---|
| Feasibility | pass | stdlib-only core demonstrated for registry/router/policy/guards/config; WPs have disjoint file ownership and listed freezes ([10](../10-implementation-plan.md) sections 3, 4) |
| Completeness | pass | all seven product requirements mapped to a section ([README](../README.md) section 2); open questions are listed, none blocks WP start |
| DX | pass | one registry, one way to scope, `describe`/`explain`/`check-config` with "did you mean"; templates and Python share field names |
| AI-consumer | pass with limitation | 8 scenarios, 59 checks; same-author simulation, so an independent run is a release gate (WP-11) |
| Security | pass | bypass matrix defined ([10](../10-implementation-plan.md) section 5); documented residual limits: hardlinks, allowed programs' own privileges, agents not confined by path/command scopes ([03](../03-policy-and-permissions.md) section 12) |
| Backward compat | pass | 41 routes equal, 297 tests must pass unmodified (WP-5), legacy preset with the v1 jail and error shapes, rollback switch |
| Client mirror | pass | generated tree with the same IDs, no hidden traffic, E31xx table, Node CLI parity, root-level drift/contract tests |

## Exit status

A full round over the final documents produced **no unresolved material finding**; the review loop stops here.

## What this review did not and could not establish

* The reviews were **sequential lens passes by one author plus executable spikes**, not independent reviewers; no subagent facility was available.
* Real agent CLIs (codex, claude, qwen, cursor, qoder), the network install path, and a live `openai` SDK against an implementation were not exercised; they are covered by
  WP-6/7/8/11 gates. The `qoder` adapter is an experimental, unverified profile.
* Hardlink-based escapes and what an allowed program does with its own privileges are documented limits, not solved problems.
