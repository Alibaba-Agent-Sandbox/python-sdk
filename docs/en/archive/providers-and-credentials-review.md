# Providers and Credentials — adversarial review log

> Status: archive. Not the current specification.

Reviewed document: [`providers-and-credentials.md`](../design/providers-and-credentials.md) (the normative design) and its CLI counterpart `cli/docs/design/providers-and-credentials-cli.md`.

> **Process note (honest disclosure).** The brief asked for two *independent* review rounds by fresh reviewers. The authoring environment offered no way to spawn independent reviewers, so both rounds were performed by the author in a deliberately separated "attacker" mode: each round used a different lens, started from the document text only (not from the author's intent), and every claim was checked against the real code (`transport/config.py`, `api/sandbox.py`, `models/*`, the original CLI) with concrete probes, not by re-reading prose. The findings below were all real defects of the first draft that were fixed in the design before any code was written. Treat this log as a self-review; a human/independent third pass is still recommended before the CLI worker starts (see "Residual risks").

Severity: **B** blocker (design cannot work / security hole), **H** high, **M** medium, **L** low.

## Round 1 — lens: functional completeness, missed keys/aliases, provider-contract gaps, migration/back-compat

| # | Sev | Finding | Resolution (where) |
|---|---|---|---|
| 1.1 | H | Inventory missed surfaces that read config: `SANDBOX_LOG_LEVEL`, `SANDBOX_TEMPLATE`/`ABX_TEMPLATE`, the server SDK's `SANDBOX_*` variables, MCP `ABX_MCP_*`, `TEAM_ID`/`E2B_TEAM_ID`, `ACREE_INSTANCE_ID` (note the double E), `--acree-instance-id`. | Added to §1.1–1.7 and to the alias tables; `acree_instance_id` flag alias; server-side variables explicitly listed as *out of scope but unchanged*. |
| 1.2 | H | `api_key` is accepted as a `config set` name *and* as a TOML key, `api_base_url` exists in `load_config` kwargs, `domain`/`api_url` live both flat and under `[transport]`. The first alias table only covered env names. | §5 now has separate env / config-file / SDK-kwarg / CLI-flag alias tables; flat-TOML legacy keys are honoured **only when `[transport]` is absent** (as today). |
| 1.3 | H | Renaming `api_url`→`sandbox_base_url` while "no stdout change" is contradictory for `config list`. | Policy §6: the rename in `config list` is the requested change and is called out; everything else is silent; `--legacy-names`/`ABX_CONFIG_LEGACY_NAMES=1` keep the old listing one more release. |
| 1.4 | H | Existing tests monkeypatch `agent_sandbox.transport.config._ENV_FILE_CANDIDATES/_CONFIG_FILE/_PROJECT_ENV_FILE` and `agent_sandbox.api.sandbox.{load_config,create_auth_provider,HttpClient,SandboxProtocol}`; tests build `TransportConfig(api_key=…)`. A registry/rewrite could break them. | §11 implementation map: seams are preserved; `TransportConfig` keeps `api_key`, `api_url`, `domain` as constructor aliases and properties (read+write); the default (built-in) path in `Sandbox` keeps using module-level names. Tests for it. |
| 1.5 | M | Storage names must be the one environment variable for each key. | `abx config set` writes that one name. There is no second storage name. |
| 1.6 | M | Precedence quirk: today dotenv candidates are consulted per *name*, so a lower-priority file can win through an earlier-listed alias. Undocumented, untestable. | Normalised to **layer-first, then name order**; called out in CHANGELOG and CLI §0. No existing test pins the old behaviour. |
| 1.7 | M | `region`-derived defaults (`sandbox_base_url`, `sandbox_domain`) have a quirk: an explicit URL by env disables domain derivation. | Preserved and specified (§4.5); generalised as `[endpoint.derive]` so plugins can declare it. |
| 1.8 | H | Provider contract lacked features that existing SDK surface needs: `sandbox.pause`, `sandbox.timeout`, `exec.stream`, PTY, `templates.*`, metrics, code interpreter, `files.watch`. Without them "typed error for unsupported" is unfalsifiable. | Capability registry (§7.2) with 18 named features, mapped 1:1 to SDK calls; unsupported → `E8004` `ProviderFeatureNotSupportedError` raised *before* any side effect. |
| 1.9 | H | Sandbox ids are provider-local; sessions (`models/session.py`), `sandbox.yaml`, `@sandbox` have no provider field → resuming a session against the wrong provider. | Sessions remember `provider`; `sandbox.yaml` gets `provider:`; qualified refs `provider:id`; conflict → `E8030`. |
| 1.10 | M | Plugin error semantics undefined → CLI exit codes 0–6 can't be derived. | §9 error table E8000–E8030 + `epp-error-mapping.json` (EPP code → SDK exception → CLI exit code) shared by both languages. |
| 1.11 | M | No story for *Windows* and for plugins that cannot be started (missing interpreter). | `E8021` (`ProviderProcessError`) with stderr tail; `.bat/.cmd/.ps1` rejected; `--link` POSIX-only. |
| 1.12 | L | LLM keys (`qwen_code_*`) already removed in the original; the table must say they are *not* resurrected. | Listed as removed; `ABX_QWEN_CODE_API_KEY` stays a legacy env alias only. |

## Round 2 — lens: UX, security/supply chain of git plugins, testability, multi-provider edge cases

| # | Sev | Finding | Resolution |
|---|---|---|---|
| 2.1 | **B** | **Credential leakage between providers.** If generic `sandbox_api_key` (`ABX_SANDBOX_API_KEY`) is passed to whatever provider is default, `abx provider default evil` (or a plugin update) exfiltrates the Alibaba key; the reverse sends a plugin's key to the Alibaba endpoint. | §4.6 isolation rule: generic sandbox keys belong to the built-in provider. Non-builtin providers get them only via manifest `[core] inherit` ∩ the consented list stored in the install receipt; consent screen prints a warning line; `provider doctor` warns about double use. |
| 2.2 | **B** | **Install must not execute code, and git itself can.** `git clone`+checkout can run hooks/filters/LFS smudge, follow symlinks, and write outside the target. | §8.2: `--no-checkout --filter=blob:limit`, isolated git config (no system/global, `protocol.allow` allow-list, no redirects, no credential helper from env), `ls-tree -z -l` validation of *every* entry (no symlinks/submodules/oversize/case-collisions/traversal) **before** blobs are written with `cat-file --batch`; no working-tree checkout at all. |
| 2.3 | H | Tag/branch installs are mutable; a "pinned" claim based on a tag is false. | Only a 40-hex commit or `--sha256` tree digest pins; tags/branches are `unpinned`, refused non-interactively without `--allow-unpinned`; `update` of a pinned install needs an explicit new `--ref`. |
| 2.4 | H | Post-install tampering (edit a file in `~/.abx/providers/<id>`). | Tree digest recorded in the receipt `.abx-install.json`; re-verified before **every** spawn (`E8011`); language-neutral `tree-digest-vectors.json`. |
| 2.5 | H | Secrets in argv/env/logs: `--opt token=…` is visible in `ps`; plugin env inherits everything; plugin stderr echoes secrets; `initialize` could be logged. | `--opt` refuses secret fields; spawn env scrubbed (allow-list + manifest `env_passthrough`, which may not name `ABX_*`/`E2B_*`/`ALICLOUD_*`); secrets delivered only in the `initialize` request over stdin; stderr redacted and ANSI-sanitised; `initialize` never logged. |
| 2.6 | H | The manifest `[security]` block looks like a sandbox but is not. Users will over-trust it. | Documented as **advisory/self-declared** everywhere (consent screen label "declared by the plugin (not enforced)", §8.5 caveats); OS-level confinement listed as future work. |
| 2.7 | H | Output ambiguity: `abx list` prints bare ids; after switching the default a user pastes an id into the wrong provider. But changing output for existing users is forbidden. | Legacy format only if **ambient and effective** provider are both `alicloud-express`; otherwise qualified `provider:id` and JSON `provider` key. |
| 2.8 | M | `--link` is a hole for unpinned code. | Requires `--yes`; trust level `link`; POSIX only; manifest and integrity re-read each spawn. |
| 2.9 | M | `[auth]` model could not express "(a AND b) OR c" (e.g. AK+SK or a token) → wrong "missing credentials" errors. | `[auth] any_of = [["a","b"],["c"]]`; drives `E1003`/doctor. |
| 2.10 | M | Testability: no plugin to test with; installer tests would need network. | Reference plugins `examples/providers/{e2b-compatible,local-process}`; temp bare git repo + `--allow-insecure-transport` (`file://`) for installer tests; **canary test** (plugin writes a file if executed — must not exist after install); `providers.testing` contract kit that any plugin can run. |
| 2.11 | M | Two implementations (Python + Node) will drift. | Conformance fixtures (`config-keys.json`, `config-resolution-vectors.json`, `tree-digest-vectors.json`, `epp-error-mapping.json`, `migration-vectors.json`) generated by Python, mirrored byte-identically in the CLI repo, with an identity test. |
| 2.12 | M | Multi-provider: `list --all-providers` with one broken provider; a sandbox record from provider A given to provider B; `--provider` + `Q:id` mismatch. | Partial-failure semantics (warn + continue; exit by best result); `E8030` for conflicts; sessions remember provider. |
| 2.13 | L | UX gaps: no typo hint on `--provider`, `abx --help` doesn't mention providers, `abx info` doesn't say which provider answered. | Added (CLI spec §0, §4.1). |
| 2.14 | L | Windows `.bat` launchers need a shell → shell-injection surface. | Rejected by manifest validation; spawn is always `shell:false`/argv list. |
| 2.15 | L | Plugin names/ids may collide with config table names or Windows reserved names. | Reserved id list (`core`, `transport`, `providers`, `shortcuts*`, `con`, `nul`, …) shipped in the JSON export. |

## Residual risks (accepted, documented)

* Plugins are ordinary programs: pinning + consent + env scrubbing reduce, but do not eliminate, supply-chain risk. No OS sandbox in this release.
* `exec` providers cost one process per CLI invocation (startup latency); long-lived daemons (EPP/2) are future work.
* The self-review limitation above: no independent reviewer saw the document.

## Implementation-phase addendum

Findings discovered while implementing the Python side (round 3):

| # | Finding | Resolution |
|---|---|---|
| I1 | EPP `-32002` mapped to `SandboxCreationError` (E2000, exit 1), contradicting the documented exit code 4 for "not found". | Added **E8005 `ProviderResourceNotFoundError`**. `-32002` maps to the class named by `data.sdk_code`, else E8005; `exit_code_for` and `epp-error-mapping.json` updated (§7.4, §9). |
| I2 | The contract-test kit failed against a plugin whose `sandbox.kill` raised for an unknown id (kill was not idempotent). | The reference plugin's `kill` is idempotent, the host adapter swallows E8005 on kill, and the kit checks idempotence. |
| I3 | `Sandbox.list_commands` raised `TokenExpiredError` for sandboxes of providers without envd. | Marker URL `epp://<provider>/<id>`; envd auth/listing are skipped for it. |
| I4 | A plugin that exited cleanly could leave grandchildren running. | `EppClient.close` reaps the process group after exit as well as on timeout/crash. |
| I5 | Running a Python plugin wrote `__pycache__` into the digest-verified directory, so the second spawn failed integrity. | `PYTHONDONTWRITEBYTECODE=1` joins the scrubbed environment (§8.3); `data/` is reserved for plugin state and excluded from the digest. |
| I6 | No API to release the plugin process owned by a `Sandbox`. | `Sandbox.close()` / `close_sync()`. |
| I7 | `apply_migration` left an empty `[transport]` table after moving all keys. | Dropped when emptied; covered by `migration-vectors.json`. |
| I8 | The design said "effective capabilities = template ∩ provider". Implementing the intersection up front adds a second source of truth that can disagree with the provider. | §7.2 now states that template capabilities are unchanged and a missing provider feature raises E8004 at call time. |
| I9 | `sandbox.yaml provider:` and `@sandbox(provider=...)` touch the declarative layer, which another workstream edits concurrently. | Deferred and marked "planned" in §7.8; listed as a follow-up. |
| I10 | The manifest example used `command = ["python3", "provider.py"]`; a bare name is resolved via `PATH`/CWD, only `./x` is anchored in the plugin directory. | Examples use `./provider.py`. |
| I11 | Documentation said dotenv layering was "unchanged"; one corner (different names for one key in the two `.env` files) does change. | Called out in `reference/configuration.md` and the CHANGELOG as the single behaviour change. |

Verification at the end of the implementation phase: the new and affected modules pass (`tests/test_utils/test_config_keys.py` 144, `tests/test_transport/` incl. `test_config_names.py` 92, `tests/test_providers/` manifest 51, installer 87, EPP 33, sandbox-provider 15, registry scoping 33, conformance 106; 738 in total with the pre-existing transport tests); the rest of the client-sdk suite passes (1846 tests) except modules that import the server package while another workstream's `routes_agents` module is mid-change (circular import, unrelated to providers); ruff and mypy are clean for every new file.
