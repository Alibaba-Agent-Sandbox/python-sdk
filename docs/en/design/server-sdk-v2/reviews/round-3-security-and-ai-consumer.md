# Review round 3: security (second pass) and AI-consumer simulation

> Part of [Server SDK v2](../README.md).

**Target**: docs 01-09 after rounds 1-2; spike extended with the policy engine, declarative custom ops, config loader, limits.
**Lenses**: security (policy semantics, environment, agents), AI-consumer simulation on eight scenarios (S1-S8), DX.
**Method**: the author re-read **only** the reference card ([09](../09-ai-codegen-usability.md) section 3) and wrote the artefact plus attack tests for each
scenario (protocol in 09 section 7), then executed them against the spike (`spikes/ai_consumer/s1..s8`). Limitation: same author, separate pass (README section 6).

## AI-consumer scenarios

| # | Task (given to the "consumer") | Checks | Result at end of round |
|---|---|---|---|
| S1 | Only download, limited to `/tmp` (the mandatory example), plus preset-equivalent form | 10 | pass |
| S2 | Restricted shell for a grader: `ls {path}`, `pytest -q ...`, `python3 /workspace/grade.py`, no env override | 11 | pass |
| S3 | Codex endpoint with custom auth; literal secret must be rejected; typo'd preset must be rejected with a hint | 10 | pass |
| S4 | Multi-agent host (codex + claude_code), observers read-only; typo'd selector flagged with suggestion | 8 | pass |
| S5 | Different per-caller limits on one op (guest rate limit, staff larger size) | 4 | pass |
| S6 | Custom op `custom.checksum(path)` under one root, hook denies `*.exe`, everything else off | 6 | pass |
| S7 | Read-only observer with audit; unmounted calls logged; no content in audit | 5 | pass |
| S8 | `template.yaml` `server:` equivalent of S1/S2 incl. unknown-key suggestion | 5 | pass |

Total 59 checks, all passing after the fixes below; several were red on first execution.

## Findings

| ID | Sev | Lens | Finding | Evidence | Resolution | Where fixed |
|----|-----|------|---------|----------|------------|-------------|
| S3.1 | M | security | Caller-supplied `env` could replace `PATH` (single `env_allow` list): `commands.run` with `env={"PATH": "/tmp/evil"}` ran an attacker binary in an otherwise allowlisted command | `attack3.py` / S2 | Split into `env_pass` (names passed from the server env) and `env_set` (fixed values); the caller can set **nothing** by default; `env_deny` blocks `LD_*`, `DYLD_*`, `PYTHON*`, `NODE_OPTIONS` | [03](../03-policy-and-permissions.md) 7.2 |
| S3.2 | M | security | Script-write plus run pair: an allow rule that can write `/workspace/x.py` and an allowed command `python3 /workspace/x.py` is arbitrary code execution | S2 | `Policy.lint` flags an absolute-path command token under any root where an allow rule can write | [03](../03-policy-and-permissions.md) 7.3 |
| S3.3 | M | security | `allow(ops.agents.codex.**)` mounted `agents.codex.install` (a network+exec admin op); `group:`/`effect:`/`*` had the same hole | S4 | **Explicit-only ops**: ops declared `explicit=True` (`agents.<a>.install`, `core.reload`) are never matched by wildcards/groups/effects, only by their exact ID | [03](../03-policy-and-permissions.md) section 2 |
| S3.4 | M | security | `Idempotency-Key` entries were global: principal B could replay or read principal A's response by guessing the key | design review | Keys are namespaced by principal; session ownership per principal (`share_sessions` opt-in) | [05](../05-agents-api.md) section 10 |
| S3.5 | M | feasibility | Declarative `custom:` ops (YAML) had no way to declare a jail for path parameters (`KeyError` in the spike) | S6/S8 | `@op(paths={param: root})` intrinsic jail intersected with rule scopes; declarative ops compile to it | [02](../02-operation-model.md) section 3, [08](../08-template-building-ux.md) section 2 |
| S3.6 | m | DX | Lint "undeclared path-like parameter" fired on `cwd` of command ops | S6 | `cwd` is exempt when `command=` is declared | [02](../02-operation-model.md) section 3 |
| S3.7 | m | test quality | The S6 lint assertion was hard-coded `True` (the consumer's test proved nothing); the op was also registered after server construction | self-review of the scenario | Replaced with a real assertion; registration moved before construction (and `RegistryFrozen` now tells you so) | `spikes/ai_consumer/s6_custom_op_hook.py` |
| S3.8 | m | feasibility | `explicit` landed in the wrong dataclass slot through positional construction | S4 | Keyword-only construction for `Operation`; the field list is frozen at WP-0 | [10](../10-implementation-plan.md) section 4 |
| A3.1 | M | AI-consumer | The card was **silent** on: compat signatures, `server.call()`, explicit-only ops, `env_pass`/`env_set`, the writable-script lint, the `paths` dict form | scenarios needed edits to compile | Card updated; every addition is test-backed in the spike | [09](../09-ai-codegen-usability.md) section 3 |
| A3.2 | m | AI-consumer | Typo'd presets/selectors were accepted silently in YAML | S3/S4 | `check-config` rejects unknown keys, presets and selectors with "did you mean"; literal secrets rejected with the `*_env` fix hint | [03](../03-policy-and-permissions.md) section 10; [09](../09-ai-codegen-usability.md) section 4 |

## Lens notes (no finding)

* Deny precedence, OR-of-allows by specificity, hook veto-only semantics, exception-in-hook fails closed: asserted in `tests_proto.py` and `attack3.py` (7).
* Audit records contain no body content (S7).

## Exit status

All M findings resolved. Because the pipeline and transport had not yet been reviewed end to end, and because the compat and mirror lenses had only a first pass, round 4 was required.
