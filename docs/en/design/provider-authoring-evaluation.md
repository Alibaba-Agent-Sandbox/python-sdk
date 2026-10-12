# Provider authoring evaluation — how hard is it to add a provider?

> **Status**: Evaluation (evidence-based) with a resolution pass applied (see §10) · **Subject**: the `opensandbox` exec-provider plugin (`examples/providers/opensandbox/`) written against only the in-repo docs, then driven against a real local OpenSandbox server · **Companion docs**: [providers-and-credentials.md](providers-and-credentials.md) (normative design), [provider-opensandbox-mapping.md](provider-opensandbox-mapping.md) (research that fed the plugin), `../guide/providers.md` (user/author guide) · **中文**: [../../zh/design/provider-authoring-evaluation.md](../../zh/design/provider-authoring-evaluation.md)
>
> **Method.** One author (an AI coding agent) started from the repository docs and the reference plugin, built the plugin, and recorded every place the docs, the host adapters or the tooling forced a detour. Claims are tagged **[ran]** (reproduced by running something; the command is in §9), **[read]** (read in source or docs) or **[est]** (estimate). "Time" figures are wall-clock estimates of the session, not instrumented measurements.

---

## 0. Verdict

Adding a provider is **feasible and mostly pleasant**: the wire protocol is small, the manifest does a lot of the boring work (config schema, env aliases, secrets, consent, integrity), and the installer/receipt machinery behaved correctly in every flow except two bugs (§5, both fixed since, §10). A complete plugin (lifecycle, pause/resume, streaming exec, 9 file operations, process control, port URLs; 1.7 k lines of dependency-free Node plus 1.3 k lines of tests) went from zero to a green contract run in roughly an hour, and to full live coverage in a few more.

The friction is concentrated in three places, none of them the protocol itself:

1. **The host side of the abstraction is thinner than the spec.** `Sandbox.create` hard-codes `secure=True`, has no per-create provider options, never calls `ports.url`, lazily starts `commands.start()`, and `run_code` has no fallback (§4).
2. **The author tooling is under-documented and partly broken.** The documented contract-test command collects zero tests; the kit has five tests; there is no scaffold, no mock host and no "EPP client" for plugin authors, so every author re-builds a JSON-RPC test client (§3, §6).
3. **Cross-component drift.** Parameter names and optional methods in the spec, the Python adapters, the reference plugin and the (future) CLI are not pinned by one machine-readable schema (§3.3).

---

## 1. What was built

| Item | Result |
|---|---|
| Runtime choice | Dependency-free Node ESM (Node >= 20, built-in `fetch`). The mapping doc *recommended* stdlib Python but did not mandate it. Node was chosen because the `ebx` CLI is a Node program (no extra runtime for CLI users), `fetch` + `ReadableStream` make SSE streaming simple, and the installer forbids dependencies anyway. Cost: Python-SDK-only users need `node` on `PATH`. A Python port would be a mechanical translation. |
| Capabilities | `sandbox.lifecycle` (create/connect/get/list/kill), `sandbox.timeout`, `sandbox.pause` (pause/resume), `exec.run`, `exec.stream`, `process.manage` (list/kill/signal; no stdin), `files.rw` (read incl. ranges, write incl. mode, list, stat, mkdir, remove, move; extensions search/chmod), `ports.url`, `sessions` (detached commands). Declared unsupported (E8004): `pty`, `code.interpret`, `templates.*`, `files.watch`, `files.transfer`, `process.stdin`. |
| Configuration | 13 manifest fields; canonical `EBX_OPENSANDBOX_*` plus native aliases (`OPEN_SANDBOX_API_KEY`, `OPEN_SANDBOX_DOMAIN`, ...). Secrets (`api_key`, `registry_password`) flagged `secret`. |
| Size | `provider.mjs` + `src/` 1 670 lines; tests 1 262 lines (24 unit, 21 mock-server, 2 live-EPP, 5 kit, 10 pytest SDK scenarios). |
| Quirks absorbed | execd upload needs the metadata part as a *file* part; `mode` is octal digits written as a decimal integer; DELETE `/files` vs `/directories` are type-specific; a second kill returns 404 (swallowed to keep `kill` idempotent); TTL minimum 60 s (clamped); metadata must follow Kubernetes label rules (validated up front, `-32006`); `renew-expiration` takes an absolute time (derived from the server `Date` header, so client clock skew does not matter); legacy execd v1.1.0 has no `argv` and strips line endings (detected and handled). |

---

## 2. Test results (local OpenSandbox server 1.1.1, Docker runtime)

| Tier | Command | Result [ran] |
|---|---|---|
| Node unit + mock server | `node tests/run.mjs` | 45/45 pass |
| Node live (EPP/1 direct) | `OPENSANDBOX_LIVE=1 node tests/run.mjs live` | 2/2 pass (full lifecycle/exec/files/ports/pause/error mapping, wrong key) |
| Shared contract kit | `pytest ... --provider-under-test opensandbox` (with the collection workaround, §6.1) | 5/5 pass (**now 18/18** with `python -m easy_sandbox.providers test opensandbox`, §10) |
| SDK scenarios (`Sandbox.create(provider="opensandbox")`) | `pytest tests/contract` | 10/10 pass (5 kit + 5 scenarios: streaming order and incrementality, exit codes, env/cwd, unicode files, `E4001` for missing files, `set_timeout`, pause/resume, process list, `E8004`, unknown id) |
| Config precedence | `provider_e2e.py --stages env` | 6/6: canonical beats native for base URL and API key; native alone suffices; wrong key is `E1001` |
| Installer flows | `provider_install_e2e.py` | 36/36 checks pass, plus 2 non-fatal findings (§5) (**now 39/39, no findings**, §10) |
| Everything | `provider_e2e.py` | 12/12 |

The installer flows covered: local-path install; `file://` bare-repo install pinned to a 40-hex commit (refused without `--allow-insecure-transport`; unpinned refused non-interactively); receipt `tree_sha256` equal to an independent digest of the installed tree and of the source tree (git and local installs hash identically); tamper detection (`doctor` integrity check fails, recovers when restored; `data/` excluded); update (`pinned` no-op, `--check`, refused without consent, applied with `--yes`, idempotent, rollback when the new version fails its handshake); uninstall keeps `data/`, `--purge` removes it; `--link` needs `--yes`.

---

## 3. Scorecard (1 = blocked, 3 = workable with detours, 5 = frictionless)

| Dimension | Score (original → after §10) | Why (original assessment) |
|---|---|---|
| Protocol clarity (EPP/1 spec) | 4 → **4.5** | One table lists every method, params, result and feature; conventions (seconds on the wire, ordering of `exec.output`/`exec.exit`, idempotent retry set, 8 MiB line limit) are stated. Misses: optional/extension methods, param names for `files.move`, chunking (see §6). |
| Manifest and config schema | 4.5 | Declarative fields, `secret`, `env` aliases, `choices`, `default`, `core.inherit`, `security` block; the host resolves precedence. The one trap: defaults are *delivered* to the plugin, so a manifest default on `base_url` would silently beat the `domain` alternative. Not documented. |
| Error model | 4 | JSON-RPC codes map to stable SDK codes, `retryable` flag, `sdk_code` hint. Gaps: no code for "connection refused" (surfaces as generic `E8000`); the set of `sdk_code` values a plugin may name is documented only by example (`E2001`, `E4001`), the full list is the `_SDK_CODE_CLASSES` table in `providers/epp.py`. |
| Installer, store, trust | 4 → **4.5** | Correct and strict in all flows; consent and receipt design is excellent. Two bugs (§5) and missing CLI flags. |
| Contract tests / author tooling | 2 → **4** | Kit exists but collects nothing as documented, has 5 tests, no streaming/pause/timeout/process/file-edge coverage, no mock host, no scaffold or `ebx provider init`. |
| Host adapters (completeness of the abstraction) | 3 → **4** | The exec adapters cover the core; but see §4: hard-coded `secure`, no per-create options, lazy start, no `ports.url` wiring, no `code` fallback. |
| Reference plugin | 3.5 | `local-process` is compact and readable; it is Python, covers no HTTP/streaming/auth, and shows none of the real-world problems (clock skew, retries, cancel). |
| Docs discoverability | 3 → **3.5** | Design doc is exhaustive but 700+ lines; the author path is spread over design + guide + code; the guide's *Writing a provider* section shows the manifest only; there is no walk-through of the first EPP exchange or of the methods a plugin must answer. |
| Debuggability | 3.5 | stderr is captured and shown on crash; `doctor` is great. No way to replay a request trace, no `--trace-epp`. |
| Offline testability | 3 → **3.5** | Authors must write their own mock server and EPP client (both done here; reusable). |
| **Overall** | **3.5 → 4.0 / 5** | See §10 for what moved each score. |

### 3.1 Time to first working plugin [est]

| Milestone | Time | Notes |
|---|---|---|
| Read design + mapping + reference plugin | ~15 min | The mapping doc did most of the thinking; without it this is the long pole (API reconnaissance of the target platform dominates, not EPP). |
| Skeleton: manifest + `initialize` + `doctor` green | ~10 min | `local-process` as a template is enough. |
| Lifecycle + exec + files, first green kit run | ~35 min | The kit failed once on a missing `sandbox.connect` (spec lists `connect` *or* `get`; the host calls `connect`). |
| Full capability set, error mapping, mock + live tests | a few hours | Almost all of it target-platform quirks (§1), not EPP. |

For a platform with a clean REST API and no execd-style quirks, a 150-line plugin should be a ~30 minute job given a scaffold; today the missing scaffold and mock host add roughly 20 minutes.

### 3.2 What went well

* The `initialize` handshake delivering resolved config means plugins contain no config loading code.
* Secrets stay out of argv/env and the plugin's error messages were easy to redact because the config schema marks them.
* `doctor` found real mistakes (bad manifest field, wrong entry path) before any sandbox was created.
* The `epp://<provider>/<id>` marker URL cleanly disables envd for exec providers.
* Receipt + digest verification on every spawn gave tamper detection for free.

### 3.3 Cross-component drift (the main long-term risk)

The same protocol surface is described in four places: the design table, the Python adapters, the reference plugin and (soon) the Node CLI. Examples seen: `files.move` params (`path…` in the table vs `source`/`destination` in the adapter; the plugin accepts both); `sandbox.connect` vs `sandbox.get`; string `process_id` for `exec.start` vs integer `pid` in `ProcessInfo`/`kill`; optional extensions (`files.search`, `files.chmod`, `exec.start{detached}`) that the plugin implements (they are needed by the mapping) but that neither the table nor any host adapter mentions, so nothing calls them yet. A single JSON Schema (or the existing conformance fixtures extended to per-method request/response schemas) would remove this class of bug.

---

## 4. Abstraction leaks (host-side behaviour an author cannot influence)

| # | Leak | Effect | Suggested fix |
|---|---|---|---|
| L1 | `Sandbox.create` always sends `secure: true` | A plugin cannot honour a user's `secure=False`; the plugin had to ignore the flag and add a `secure_access` config field (Kubernetes gateway only) | Send `secure` only when the user set it; document its meaning for non-envd providers |
| L2 | No per-create provider options | Image pull policy, network policy, registry auth, platform, GPU must be global config fields | Pass `provider_options` (already accepted by `Sandbox.create`) through to `sandbox.create` as `options` |
| L3 | `ports.url` is never called | `network.get_url` is computed client-side from the sandbox domain, so the plugin's `ports.url` is dead code in the SDK; works only when the CLI wires it | Route `network.get_url` through `ports.url` when the feature is declared |
| L4 | `commands.start()` is lazy for exec providers | `exec.start` is only sent when the returned `StreamReader` is iterated; "start in background and poll" silently does nothing | Eagerly send `exec.start` in the adapter and buffer into the queue |
| L5 | `ProcessInfo` carries only `pid`, `command` and `status` | Plugin-side data (user, start time, cpu) is dropped | Pass optional fields through |
| L6 | `Sandbox.run_code` raises `E8004` for exec providers without `code.interpret` | No portable "run Python in the sandbox" fallback even though `exec.run` could do it | Optional shell-based fallback (`python3 -c`) in the adapter, behind a feature flag |
| L7 | Capability resolution warns `Could not resolve capabilities for template 'base'` on every create | Log noise on every non-default provider | Skip resolution for non-built-in providers, or resolve to the provider's declared features |
| L8 | `process_id` is a string on exec streams but `pid: int` in `commands.kill(pid)` | Plugins that cannot expose numeric pids (execd command ids) cannot be killed via the SDK | Make `kill` accept `str | int` and pass through |
| L9 | No chunked `files.read/write` | 8 MiB line limit caps a file at ~6 MiB; the plugin caps reads at 4 MiB | Add `offset/length` to `files.read` (plugin already supports) and a chunked write (`append`) in the spec |
| L10 | An unreachable server surfaces as generic `E8000` | Users see "provider failure" for a typo in `base_url` | Add a connection-failure code (or `sdk_code`) that plugins can request |

---

## 5. Defects found in the installer (not in the plugin)

| # | Defect | Evidence | Fix |
|---|---|---|---|
| B1 | **`data/` is lost when an update is rolled back.** `_swap_in` moves the old `data/` into the staged tree before `verify` runs; on verify failure it deletes `final` (now holding `data/`) and restores the trash copy, which no longer has `data/`. | `provider_install_e2e.py` prints `[BUG ] data/ survives an update that was rolled back...` | Move `data/` back into the trash copy before `remove_tree(final)` (or copy instead of move until `verify` passes). |
| B2 | **`python -m easy_sandbox.providers update` has no `--allow-insecure-transport`.** Git sources installed with the flag cannot be updated from the command line (E8012); the receipt does not record that the flag was used. | `[GAP ] CLI 'update' cannot reach a file:// source` | Add the flag to `update`; consider recording `insecure_transport: true` in the receipt so `update` can reuse it after consent. |
| B3 | The documented contract-test command collects 0 tests (§6.1). | `--pyargs easy_sandbox.providers.testing` finds nothing because neither the module name (`testing.py`) nor the class name (`ProviderContractTests`) matches pytest's defaults | See §6.1. |

---

## 6. Documentation gaps

### 6.1 Contract kit instructions are wrong

`guide/providers.md` says `pytest -p easy_sandbox.providers.testing --pyargs easy_sandbox.providers.testing --provider-under-test my-cloud`. That collects **0 items** (pytest exits 5, which a lenient CI step can ignore). The subclass form shown just above it in the guide works. The command line form needs:

```bash
pytest -p easy_sandbox.providers.testing -o python_classes=ProviderContractTests \
       -o python_files=testing.py --pyargs easy_sandbox.providers.testing \
       --provider-under-test my-cloud
```

The subclass form (`class TestMine(ProviderContractTests): provider_id = "my-cloud"`) is what `examples/providers/opensandbox/tests/contract/test_contract.py` uses. Recommended: make the kit collectable by default (`__test__ = True`, rename the class `TestProviderContract`, or ship a `pytest11` entry point with `pytest_collect_file`), and make "collected zero tests" an error in the docs' example (`--strict`-style check).

### 6.2 Missing or hard-to-find information

| # | Gap | Where it should live |
|---|---|---|
| D1 | Defaults declared in the manifest are sent in `initialize.config`; a default on a field with alternatives (`base_url` vs `domain`) blocks the alternative | Manifest reference, config fields |
| D2 | The complete list of accepted `data.sdk_code` values (`E4001` for files, `E2001` for templates, ...); today only the code lists them, and a bare `-32002` for a missing file becomes "sandbox not found" (E8005) | EPP error table |
| D3 | The host calls `sandbox.connect`; `get` alone is not enough | EPP method table (mark required vs optional) |
| D4 | Which methods are required for each feature, and which optional extras a host may call (`exec.start{detached}`, `files.search`, `files.chmod`) | Feature table with a "methods" column |
| D5 | What `exec.start` does with a `$/cancel` for the *request* id of a running stream (the plugin must kill the process); the spec only says cancellation exists | EPP section |
| D6 | Update re-consent rules and that `update` of a pinned install is a no-op without `--ref` | `guide/providers.md` update section (the rule is there, the no-op is not) |
| D7 | `data/` excluded from the digest, `tests/` *included* (a plugin's tests bloat every install and change the digest) | Authoring checklist |
| D8 | `install --link --yes` as the development loop is documented under *Install* but not linked from *Writing a provider* | Author guide cross-link |
| D9 | The guide's *Testing a plugin* covers only the contract kit: no mock-host helper, no sample EPP client, no advice on offline tests | New "Testing your plugin" section; this plugin's `tests/epp-client.mjs` and `tests/mock/` are a starting point |
| D10 | Canonical env names for a provider id with a dash/underscore, and the precedence between `EBX_<ID>_*`, native aliases, `.env`, TOML | Environment variables guide (the table exists, the rule for aliases is implicit) |
| D11 | Repository `pytest` runs from a directory containing an unrelated `conftest.py` fail at collection; authors need `--noconftest`/`--confcutdir` | Contributing doc |
| D12 | `pip install -e client-sdk` fails when the workspace uses a `uv` source for `server-sdk` | Contributing doc / packaging |

### 6.3 Doc fixes applied vs deferred

Applied (docs I own): `examples/providers/opensandbox/README.md` / `README.zh-CN.md` (install, config, capability matrix, test tiers, known limits), `e2e/opensandbox/README.md` (how to run the provider E2E), `examples/providers/README.md` (third reference plugin). **Deferred** (files owned by other workstreams): everything in §6.1, D1-D12, and the corrections in §7.

---

## 7. Concrete fixes, in priority order

| Priority | Fix | Touches | Size |
|---|---|---|---|
| P0 | B1 data loss on failed update | `installer._swap_in` | ~5 lines + test |
| P0 | Correct the contract-test command and make the kit collectable (§6.1) | `providers/testing.py`, `guide/providers.md` (en/zh) | small |
| P1 | `provider update --allow-insecure-transport` (B2) and `ebx provider update` parity | `providers/__main__.py`, CLI | small |
| P1 | L1/L2: honour `secure`, pass `provider_options` into `sandbox.create` | `exec_provider.ExecSandboxProtocol.create`, spec table | small |
| P1 | L4: eager `exec.start` in `ExecProcessProtocol.start` | `exec_provider.py` | small |
| P1 | L3: route `network.get_url` through `ports.url` | `Sandbox`/network API | medium |
| P2 | Machine-readable method schemas (one JSON Schema per method, shared by SDK, CLI, kit) plus kit tests generated from them | `fixtures/`, `testing.py` | medium |
| P2 | Extend the kit: streaming order and exactly one exit, cancel, `set_timeout`, pause/resume, process list/kill, file edge cases (binary, missing -> `E4001`, overwrite), idempotent kill, `-32006` on bad params | `providers/testing.py` | medium |
| P2 | Author scaffold: `python -m easy_sandbox.providers init <id> --runtime node|python` generating manifest, entry, EPP test client | new module | medium |
| P2 | Mark required vs optional methods and extension methods in the EPP table (D3, D4) | `providers-and-credentials.md` | small |
| P3 | L5-L10 | `exec_provider.py`, models | small each |
| P3 | `--trace-epp` / `EBX_EPP_TRACE=1` to log requests/responses (redacted) | `providers/epp.py` | small |
| P3 | Exclude `tests/` from the digest or document it (D7) | `store._walk_regular`, docs | small |

---

## 8. Observations on the EPP/1 design itself

* **Good**: JSON-RPC over stdio is trivial to implement in any language (the Node EPP loop is 108 lines); notifications for streaming avoid any second channel; host-driven retries limited to idempotent methods are a clean rule.
* **Good**: the hybrid (envd URL) model means a platform that already speaks envd needs no data-plane code at all.
* **Weak**: no capability negotiation beyond the manifest `features` list: per-sandbox capabilities (e.g. "this image has the code interpreter") cannot be expressed (the mapping doc listed this as gap 4).
* **Weak**: no versioned way to add optional methods; plugins add extensions (`files.search`) that only a matching host would call.
* **Missing**: progress notifications for slow creates (image pulls take minutes); the spec lists a `progress` notification but the adapters do not surface it.

---

## 9. Reproducing this evaluation

```bash
cd e2e/opensandbox && ./local-up.sh up && eval "$(./local-up.sh env)"
python3 provider_e2e.py                 # 12 checks
python3 provider_install_e2e.py         # 39 checks (it used to print [GAP]/[BUG] findings; none remain)
cd ../../examples/providers/opensandbox && node tests/run.mjs
```

See `e2e/opensandbox/README.md` for the environment variables each script reads (no secrets are written anywhere; the local API key is a throwaway development value).

---

## 10. Resolution status

Everything below was fixed in the SDK and re-verified against the local OpenSandbox server (`provider_install_e2e.py`: 39/39 checks and no `[GAP]`/`[BUG]` line; `provider_e2e.py`: 12/12 including 18 contract tests and 23 SDK scenarios; Node plugin suite: 46/46).

| Item | Status | What changed |
|---|---|---|
| B1 `data/` lost on rollback | **Fixed** | `installer._swap_in` moves `data/` back before restoring the previous tree, on both failure paths (failed `verify`, failed swap). Regression tests inject each failure and compare file contents and modes. |
| B2 `update` lacks `--allow-insecure-transport` | **Fixed** | `python -m easy_sandbox.providers update` takes `--allow-insecure-transport` and `--no-verify`. The receipt deliberately does not remember the flag (see the guide). |
| B3 / §6.1 contract command collects 0 tests | **Fixed** | `python -m easy_sandbox.providers test <id>` (fails on 0 collected tests, isolates from the current directory's pytest config) and `pytest -p easy_sandbox.providers.testing --pyargs easy_sandbox.providers.contract --provider-under-test <id>`. Guide, design doc and zh copies corrected. |
| Kit has 5 tests (§3) | **Fixed** | 18 tests: exec stream order and single exit, exit code/stderr/env, timeout enforcement, binary and unicode files, directories and move, typed not-found, kill idempotence, `set_timeout`, pause/resume, process list, `ports.url`, E8004 for undeclared features, secret redaction; `--provider-option KEY=VALUE`. |
| L1 hard-coded `secure=True` | **Fixed** | `Sandbox.create(secure=None)`: sent to a plugin only when the caller set it; the built-in provider still behaves as `True`. |
| L2 no per-create options | **Fixed** | `provider_options` reach `sandbox.create` as `options` (secret fields removed). The OpenSandbox plugin accepts a whitelist per create (`network_policy`, `platform`, `default_image`, ...) and never lets `options` change the server address or key. |
| L3 `ports.url` never called | **Fixed** | `await sandbox.network.resolve(port)` / `resolve_url(port)` ask the plugin when `ports.url` is declared. `get_url()` stays synchronous and local (no API break). |
| L4 lazy `commands.start()` | **Documented, not changed** | Not a provider-layer bug: the built-in envd stream is lazy in exactly the same way, so an "eager exec adapter" would make providers differ. The guide says so and shows the `nohup ... &` / `sessions` alternatives. |
| L8 `process_id` string vs `pid` int | **Fixed** | `pid` is `int \| str` end to end (`ProcessInfo.pid`, `commands.kill/send_signal/send_input`, the exec adapter); the table says `string \| integer`. |
| §3.3 drift: `files.move` names, `connect` vs `get` | **Fixed** | One machine-readable table, `epp-methods.json` (mirrored byte-identically to the CLI repo, identity-tested). The adapters are tested against it in both directions. `files.move` is `source`/`destination`; `sandbox.get` is required and `sandbox.connect` optional with an automatic fallback to `get` on `-32601`. |
| Silent hang on a plugin that never ends a command | **Fixed** (found while extending the kit) | The streaming adapter raised a bare `asyncio.TimeoutError`; it now raises `CommandTimeoutError` (E3001). |
| D1, D2, D3, D4, D5, D6, D7, D8, D9, D11 | **Fixed (docs)** | Guide *Writing a provider* / *Testing a plugin* and the design doc's method table and conventions (en and zh). D7 is documented rather than changed (a plugin's `tests/` stays in the digest). D11 is covered by a note in the testing section. |
| D10, D12 | Open | Environment-variable rule for ids with dashes is in the configuration reference already; `uv` source packaging is a contributing-doc item outside the provider docs. |
| L5 extra `ProcessInfo` fields, L6 `run_code` fallback, L7 capability-resolution log noise, L9 chunked files, L10 connection-refused code | Open | Recorded for a later pass; the optional extension params (`files.read{offset,length}`, `files.write{mode,append}`) are in the method table so plugins can implement them ahead of the host. |
| Scaffold (`provider init`), `--trace-epp`, per-method result schemas | Open | Parameters are schema-checked; results are only described. |

**Scorecard movement.** Contract tests 2 → 4 (collectable, 18 tests, one command); host adapters 3 → 4 (L1-L4, L8); installer 4 → 4.5 (B1, B2); protocol clarity 4 → 4.5 (one table with required/optional/extension and exact names); docs discoverability and offline testability +0.5 each. Overall 3.5 → 4.0.
