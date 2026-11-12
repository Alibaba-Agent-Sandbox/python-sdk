# Verification: managed Session public projection

Date: 2026-11-12. Status: PARTIAL; local projection checks below do not replace final-head remote
CI, final Server image reconstruction or required cloud acceptance. Extends committed source
`c550cf53a9eb0c3c9899d0336b924633eb9b0988`; no package release or cloud/model invocation.
Part of [delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309),
not a claim that [input PR163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/163)
provides complete official SDK compatibility.

## Regression and actual behavior

Two new real HTTP regressions use temporary SQLite/PostgreSQL: before the fix both fail because
Session timestamps are fractional floats; after the fix both pass. Creation, retrieval and list
return integer seconds and empty action/Vault arrays. Observation preserves exact fractional
stored timestamps and a private deadline. Unsupported action/Vault request fields remain400;
no Sandbox is created. No official executor URL or effective model settings are fabricated.

The targeted saved-Agent/typed-input/projection group passes6 tests. The independent official
SDK3.49.0 probe uses the actual SDK distribution, a real authenticated loopback Managed HTTP
listener and SQLite. Default create/retrieve/list still decode; all three strict methods still
raise `APIResponseValidationError` on remaining agent/environment fields. Fractional timestamp
and absent-list errors disappear. The actual accepted typed prompt is checked in the store.
The isolated probe adds no project dependency and starts no Worker/model/cloud connection.

## Gate scope and failures retained

The initial Managed group runner used an incorrect relative path because its capture helper
fixes repository cwd; two invocations returned4 with no tests run. Corrected paths are recorded
separately. The initial static run found formatting of a pending, untracked reader regression;
that file was formatted and is not part of this scoped API commit. These harness failures are
not converted to product passes.

The earlier full local suite and CI remain bound to product1079841 / producer5cf448, as recorded
in [final local gates](2026-11-12-template-v1-runtime-final-local.md). They are not relabeled as
verification of this increment. The previously built c550 Server image is likewise historical;
this API change requires a new final Server source pin/build. The Guest image is unaffected.

The namespace-isolated Managed runtime/entrypoint group passes95 tests. Repository lint,
typecheck (server58/client117 files), format-check and hygiene all exit0. Pytest emits the existing
unset asyncio fixture-loop-scope deprecation under the root capture helper. No test is suppressed
or weakened. Staged secret/diff checks and normal commit hooks are run for this scoped commit;
the optional pre-commit framework is absent as in the prior evidence.

The initial normal commit hook rejected the new literal local-fixture token label as a potential
secret. Its explicitly test-only name was corrected to match existing fixture conventions;
no real credential was involved. The rejection and subsequent successful checks are retained.
