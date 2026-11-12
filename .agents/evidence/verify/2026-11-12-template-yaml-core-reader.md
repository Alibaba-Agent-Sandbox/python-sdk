# Verification: shared YAML1.2 Core file admission

Date: 2026-11-12. Result: PARTIAL — relevant local checks pass as detailed below; actual final-head
remote CI and required cloud acceptance remain separate. Extends Session projection source
`bd1db5215070917619dcce6593c48f432339df3f`. Reader producer:
[ef695803cb78bf82b8473195fcb37b3e6357a363](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/ef695803cb78bf82b8473195fcb37b3e6357a363).
Source lock and copied normalizer/schema/contract/object vectors/raw text vectors match exact
Git object bytes. Part of [delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

## Actual parser and file behavior

Six independent before-regressions fail with the original PyYAML reader: plain on/date values
are changed at registry loading, cache discovery and prepared launch; duplicate keys, aliases
and UTF16 are accepted. The shared Core reader plus bounded byte I/O fixes all three public file
entries. A separate oversized-file regression confirms rejection before Sandbox/journal I/O.
A valid literal file actually forwards unchanged environment strings to the prepared launch
creation call. No CLI/parser expression evaluator or cloud connection is introduced.

The packaged owner's13 positive and25 negative raw YAML text cases run through the installed
actual `yamlcore==0.1.1` loader. Valid cases also test byte input. Error strings omit source
canaries. An independent regression proves the shared Core loader does not globally change
PyYAML's existing YAML1.1 behavior for unrelated callers.

## Local gates

- Relevant raw-file, source-schema, instance, launch, discovery, registry/model and launch-contract
  group:290 passed, no skips. Existing root capture emits the unset asyncio fixture-loop-scope
  deprecation; no assertion is suppressed.
- Repository lint, typecheck (server58/client117 files), format-check and hygiene:exit0.
- Both sdists/wheels build, twine, py.typed, fresh client-only install/real HTTP, local server-extra
  registration and pipcheck (`make build dist-check`):exit0.
- A second fresh client-wheel install outside the checkout verifies yamlcore0.1.1, all13/25 raw
  text vectors, actual public file loading and every bundled source hash; pipcheck:exit0.
- Immutable producer byte comparison:exit0.

The first health check ran while this evidence file had not yet been written and returned1 for
its two unresolved local record links. Its corrected result is recorded separately; the existing
recommended maintainer release-guide warning is not a new product failure.

## Scope retained

The earlier full local suite/CI remains tied to product1079841 / producer5cf448; see
[exact historical scope](2026-11-12-template-v1-runtime-final-local.md). It is not relabeled as
full-suite validation of this reader increment or the later Session projection. Current
final-head CI must run on the actual committed head. No package release, model task, cloud
resource creation, Guest reconstruction or new cloud acceptance matrix occurred. Managed Server
consumes compiled JSON; its final source pin/rebuild is needed for the preceding Session
projection change, while the c550 image evidence remains historical.
