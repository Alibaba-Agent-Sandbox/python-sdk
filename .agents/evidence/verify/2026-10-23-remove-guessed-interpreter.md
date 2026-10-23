# Remove unverified project interpreter mappings

Result: PARTIAL

Date: 2026-10-23. This supersedes the interpreter implementation assumption in the earlier same-day Provider workflow implementation run; that run remains historical evidence of mocked behavior, not a verified wire mapping.

## Finding and correction

The project shared interpreter class used inferred `/code.CodeInterpreter/*` Connect paths. Its own source marked these unverified. Historical real-cloud records report HTTP404 and shell substitution: see [2026-10-13 cloud examples](2026-10-13-cloud-examples.md) and [2026-10-18 provider isolation acceptance](2026-10-18-provider-isolation-acceptance.md). A mocked response to that guessed path cannot establish an implemented provider operation.

Remove the guessed wire implementation entirely. Express advertises no interpreter operations, and REST manifests reject all `code.*` declarations because this declarative bridge has no verified interpreter mapping. Both use an explicit unsupported protocol that performs no I/O. The E2B catalog plugin's identical assumption is removed in its owning repository. The platform's own SDK capabilities are a separate contract; this finding concerns the project adapter.

Keep the generic interpreter API, structural protocol and engine context routes for adapters that actually implement them. No old shell fallback, missing-context inference or buffered streaming substitute returns. Express new workflows accept only managed inputs with entrypoint/none startup; standalone exec does not promise source preparation or launch ownership.

## Verification

- PASS: `pytest client-sdk/tests/test_providers client-sdk/tests/test_protocol/test_code_interpreter.py -q --disable-warnings`: 491 passed, 22 existing optional-backend/checkout skips after removing the guessed implementation.
- Additional focused regressions verify explicit unsupported errors before any transport call, no Express interpreter discovery, and rejection of REST interpreter claims. Final scoped lint/type checks and consumer integration are recorded by the coordinating final acceptance run.
- Existing licensed standard E2B source/client behavior is preserved; no standard SDK source was modified.

No backend resources were created. Real OpenSandbox source/profile and prepared-image workflows remain a separate CI gate. This correction does not certify any native interpreter or claim the upstream platform lacks one.

[Owner Issue](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/88).
