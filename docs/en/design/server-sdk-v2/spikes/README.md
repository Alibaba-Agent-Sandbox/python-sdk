# Spikes: executable evidence for the design

Throw-away reference code (stdlib only, about 1,300 lines in `ebxp/`) written to **falsify** the design before it was
frozen. It is not the implementation and must not be imported by it. Work packages WP-0..WP-3 port the ideas and
the checks, not the files.

Run everything (v2.1 self-regression; rc 0 = all green):

```bash
python3 -m virtualenv -q "${OAI_VENV:-$TMPDIR/oai-venv}" && "${OAI_VENV:-$TMPDIR/oai-venv}/bin/pip" install -q openai   # once; python3 -m venv is not available everywhere
OAI_PY="${OAI_VENV:-$TMPDIR/oai-venv}/bin/python" bash run_everything.sh
```

Individual suites (Python 3.10+; stdlib only except `agents_sdk_check.py`, which needs the real `openai` package):

```bash
python3 independent-security/run_all.py --strict   # the 41 independent-security PoCs: every one must be HELD (the gate)
python3 tests_proto.py            # 36 checks: registry, ops tree, policy algebra, guards, dispatch, describe/openapi
python3 tests_catalog.py [SRC]    # catalog vs the legacy server source (EBX_LEGACY_SRC or the repo checkout): 41 legacy routes equal; 105 ops; explicit-only; 47-route tiering 25/2/5/15
python3 tests_round4.py           # transport bounds, 401-before-404, size cap before read, config loader errors
python3 tests_v21.py              # 53 checks: fail-closed auth, scope-required, explicit-only, deny parity, transport, UrlScope, hooks, presets
python3 tests_install.py          # 11 checks: lock-free fast path, writable-dir lock, 202 job, atomic publish, read-only, modes
python3 tests_parity.py           # client/server parity ledger covers every op (07 section 6)
python3 attack1.py; python3 attack2.py; python3 attack3.py   # exploit demos (see below); prints, does not assert
for f in ai_consumer/s*.py; do python3 $f; done    # scenarios S1-S8, written from the reference card only
python3 templates/run_all.py      # the eight sample template files T1-T8 + card_imports.py (card names exist, 100 columns)
"$OAI_PY" agents_sdk_check.py     # 38 checks: the real `openai` SDK drives the /v1 Agents wire (list envelope, 202, idle-open stream, ...)
```

## The attack scripts are demonstrations, not tests

`attack1.py`..`attack3.py` print what happened for each probe. Some lines intentionally show an **unsafe outcome of a
naive design** (for example `ls -lR -> 200 (200 => deny-list bypassed)`); that output is the evidence for the rule
"command scopes are allowlist-first" ([03](../03-policy-and-permissions.md) section 7). The guarded behaviours are
asserted in `tests_proto.py` and `tests_round4.py`. WP-3 turns every probe into an asserting test (`tests/bypass/`).

## What the spike does not prove

* Nothing here speaks to real agents CLIs, the network, `openai` SDK wire details, or installs.
* `catalog.py` registers **stubs** for the 105 ops of the default registry (50 non-agent + 55 agents: 3 generic + 32 official + 5 adapters x 4); real handlers exist only for what the checks call. The agents wire (`agents_wire.py`) drives an echo adapter, not a real CLI.
* The facade `ebxp.api` mirrors the reference card ([09](../09-ai-codegen-usability.md) section 3; `templates/card_imports.py` checks it). Differences: the spike's `SandboxServer` takes `policy` first and `start()` returns `(server, httpd)` instead of blocking;
  real CLI agents, network installs and the Node CLI are not exercised (the install protocol is spiked with fake installers).
* The AI-consumer scenarios were written by the same author who wrote the card ([09](../09-ai-codegen-usability.md)
  section 7); an independent model run is a periodic, non-blocking job in 0.3.0 (WP-11).

## Spike vs final differences

| Topic | Spike | Final design |
|---|---|---|
| Race-free open | `open_beneath` (component-wise `O_NOFOLLOW` walk from a root fd) and `open_verified` (verify after open); never `O_TRUNC` at open | `open_beneath` only, plus `ftruncate` after `fstat` ([03](../03-policy-and-permissions.md) 6.2) |
| Command execution | `subprocess` with filtered env | launcher helper (rlimit + `execv`), not `preexec_fn` |
| Router | dict of (method, path) | trie router with conflict detection |
| Schemas | hand-written | generated from handler annotations (closed annotation list) |
| Audit | pluggable callables (`Policy.audit(sink)`) | JSONL sink plus OTel-friendly fields ([03](../03-policy-and-permissions.md) section 14) |
| Agents | catalog stubs only | full runtime ([05](../05-agents-api.md)) |
| Install | not covered | [06](../06-lazy-install.md) |
