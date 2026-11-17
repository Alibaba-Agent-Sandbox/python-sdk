# Managed Agent API — independent post-implementation runtime review, round 2

Date:2026-11-17. Scope: corrected six-Harness template/SDK source, not released artifacts.
Result: **PARTIAL. Source changes are reasonable within declared limits; the complete user delivery is not finished and release acceptance is not approved.**

## Re-examined after round-1 corrections

- Read all three new native adapters (`qoder.py`, `opencode.py`, `deepseek_harness.py`), existing Claude adapter, credential descriptors, actual invocation/resume arguments, parsers and `AgentRuntime` terminal handling; checked their interaction with guest ProcessDomain and receipt handling.
- Read six template profiles, Docker/package pins, per-role bootstrap/credential forwarding, generated standalone project checks and release constraints. Qoder's canonical executable now matches `qoder`; the exact upstream npm package supports both qoder/qodercli.
- Read final Turn projections and worker-created/in-progress/terminal events. Saved Agent snapshots retain original IDs and instructions after definition changes/deletion. Inline snapshot identities are stable per Session; legacy unknown starts are null and no private state is silently rewritten.
- Read actual native OpenCode/official DSH deterministic loopback capture results: two subprocess turns each exit0, retain the same native Session ID and send prior marker history on continuation. These are native CLI/protocol/resume evidence using synthetic model responses, not vendor/model business tasks.

## Closed or correctly bounded findings

1. **Bootstrap allowlist chain:** the real Session settings now carry the selected native env names. Independently reran `python -m unittest discover -s scripts -p test_agents_api_family.py -v`:2 tests pass with six adapter subcases, including standalone downloaded project/no registry.yaml, actual ManagedService Session creation and entry to the mocked native infrastructure boundary. Gateway/Dispatcher contain no selected model credential in their generated configuration.
2. **OpenCode completed-only tools:** parser now emits `tool_complete` for actual completed/error records; `_TurnBuilder` creates an already-terminal item and the tool watchdog admits only genuinely in-progress items. No instantaneous fake start is emitted to claim real-time per-tool measurement. Adapter metadata declares completed-only observations and project capability metadata/user documentation distinguish per-tool timing from whole-Turn deadline/cancel/process cleanup. The independent server regression asserts the builder emits terminal statuses and no active-tool start clock.
3. **Native terminal results:** Qoder requires a terminal native result; OpenCode requires a terminal stop/end_turn/length or an explicit error; DSH requires final.reason.kind=completed. The shared runtime still checks process exit status and fatal errors after parser.finish; a successful record cannot turn nonzero process exit into success. ProcessDomain remains the source of cooperative residual-process confirmation, and provider destruction remains the fallback when stop is uncertain.
4. **Native authentication and endpoint routing:** Qoder uses its PAT without an invented model endpoint; OpenCode receives explicit env-referenced provider JSON; official DSH uses its native profile overlay and DEEPSEEK variables. Root/Harness reviewer verified DSH's endpoint against an actual loopback Messages listener. Only the selected native credential map enters the Sandbox.
5. **Wire projections:** independently reran client wire/harness tests:17 pass. Official OpenAI3.52 typed Turn/event parsing and actual authenticated local SDK/SSE consumption are present in the focused regressions, while legacy/saved snapshot cases keep a stable host identity. No broad SDK-equivalence claim is made.
6. **Independent server suite:** `pytest tests/test_server/test_harness_adapters.py -q`:20 pass in0.37s. This includes native-capture parser cases and completed-only builder semantics. It does not execute real vendor/model tasks.

## Remaining gates: completion is not established

- Paired runtime a8 is still unpublished. Six Guest/Server recipes deliberately require that version and say builds/deployment must wait; installing a7 is not a valid substitute.
- The exact candidate Guest/Server images have not been built here. There is no final PostgreSQL-backed FC release, candidate-to-stable alias proof, timer delivery, retained old-Session upgrade, six authenticated real-model/tool/file tasks or independent owned-cloud cleanup for these changes. Prior version/local Qwen results and deterministic native loopback responses do not replace those gates.
- SDK public YAML/discovery still packages the earlier singular contract. Independently reproduced current named-template rejection through `parse_template_data` in round1; the new owner boundary record now states this accurately. Managed explicit create/start does not consume this YAML. This remains a real SDK consumer gap; source contract byte replacement alone would damage private managed-instance validation and is not an approved shortcut.
- Eight existing raw socket regressions remain failed. A stdlib-only listener reproduces raw GET501/header-only POST timeout while http.client/urllib-no-proxy return200; this isolates a project-independent environment distinction without proving its underlying mechanism or waiving checks.
- Independent topic/website publication still needs the normal reviewed source/CI/deployment path. Local article/layout checks establish no Agent runtime acceptance.

## Additional truthfulness check sent for cross-review

The managed `/v1/agents/runtimes` response historically reports `installed:true` from configured model mappings, while only guest `/capabilities` checks actual binaries. A Gateway has no installed-binary observation before Sandbox creation. Cross-review accepted a focused correction: configured=true, installed=null until actual guest observation, with matching documentation and a regression. Independently reran the focused capabilities regression:1 pass. Gateway capability metadata retains explicit OpenCode timing limits. Configuration is no longer presented as an actual installed-binary observation.

## Verdict

The architecture, focused wire correction and per-Harness adaptation are coherent and avoid generic run-command HTTP wrapping. The same public protocol can expose honestly different native capabilities. Required missing real-component/publication evidence and the public Python YAML consumer gap prevent calling the full requested outcome complete. Keep relevant source PRs Draft until their actual gates are satisfied; do not publish a claimed fully validated six-Harness release from these local results.
