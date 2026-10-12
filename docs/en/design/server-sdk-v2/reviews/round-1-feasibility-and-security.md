# Review round 1: feasibility and first security pass

> Part of [Server SDK v2](../README.md). Process notes and honesty statement: [README](../README.md) section 6.

**Target**: first complete draft of 01-06 plus the executable spike (`spikes/ebxp/`, first 36 checks).
**Lenses applied (sequentially, by the lead author)**: feasibility (can it be built with stdlib only and shipped by independent WPs?), security (can the guard
design be bypassed?). Completeness, DX, compat, AI-consumer and client-mirror lenses ran in later rounds.
**Method**: every claim that sounded like "this will work" was turned into a check in the spike or an exploit in `attack1.py`; findings below are those
that failed the check.

Severity: **M** material (blocks sign-off until resolved), **m** minor.

## Findings

| ID | Sev | Lens | Finding | Evidence | Resolution | Where fixed |
|----|-----|------|---------|----------|------------|-------------|
| F1.1 | M | feasibility | `ops.custom.format` / `.split` / `.index` / `.replace` / `.count` returned bound `str` methods because the op reference type subclassed `str` | `tests_proto.py` "ops tree" checks | Op references are **not** `str` subclasses: `OpRef` with attribute traversal, `==` against strings, `str(op)` is the ID, `ops["x"]` for odd names | [02](../02-operation-model.md) section 2 |
| F1.2 | m | feasibility | `@op(http="POST /grade")` (a `str`) was iterated character by character | spike registry | `@op` normalises "str or sequence" for `http`, `paths`, `effects`, `aliases`; registration error names the offending parameter | [02](../02-operation-model.md) section 3 |
| F1.3 | M | security | **Write-side TOCTOU**: opening with `O_TRUNC` after canonicalising truncated a victim file when a symlink was swapped in between check and open | `attack1.py` (1): the victim stayed intact only with the verified open | `open_beneath`: component-wise `O_NOFOLLOW` walk from a root fd; `O_TRUNC` never passed to `open()`; `ftruncate` after `fstat` proves a regular file | [03](../03-policy-and-permissions.md) 6.2 |
| F1.4 | M | security | **Glob/relative path arguments** in command scopes: `ls pub/../outside` matched an allow pattern with a glob-like path argument and escaped the root | `attack1.py` (2), `attack2.py` | Typed tokens: `{path}` arguments are canonicalised against a `PathScope` and the canonical value is what is executed; free glob tokens may not stand for paths | [03](../03-policy-and-permissions.md) 7.1 |
| F1.5 | M | feasibility | The draft violated its **own ID grammar**: `agents.<a>.sessions.turns.items.list` has 6 segments (grammar allows 2-4) | `tests_catalog.py` (grammar over the full catalog) | Flatten session children to `turns`, `turn_items`, `artifacts`, `traces`; subagents and not-planned routes become static refusals, not ops | [05](../05-agents-api.md) section 3 |
| F1.6 | M | security | **Deny-list flag bypass**: denying `ls -R` did not stop `ls -lR` or `ls --recursive` | `attack1.py` (3), `attack2.py` (3, 3b) | Command scopes are **allowlist-first** (documented as a rule, with short-flag expansion for denies as a convenience only); escape-capable executables are linted; the safest option is a named custom op | [03](../03-policy-and-permissions.md) 7.1, 7.3 |
| F1.7 | m | feasibility | Registry could be mutated after the server was built, so the catalog and the mounted set could diverge | design review | Registry freezes at server construction (`RegistryFrozen`); drift test | [02](../02-operation-model.md) section 4 |
| F1.8 | m | feasibility | `preexec_fn` for rlimits is unsafe with threads | design review (Python docs) | Launcher helper (rlimit + `execv`) instead | [03](../03-policy-and-permissions.md) 7.2 |

## Lens notes (no finding)

* Feasibility of stdlib-only core: confirmed for registry, router, policy, guards, JSON config (the spike is ~1,300 lines). YAML is compiled by the CLI
  only (the runtime reads JSON), which keeps the stdlib-only promise.
* Not verified in this round: anything involving real agent CLIs, the network, or the official `openai` wheel.

## Exit status

All M findings resolved in the docs and re-checked in the spike (36/36 at the end of the round). Because material findings were found, a new round was required.
