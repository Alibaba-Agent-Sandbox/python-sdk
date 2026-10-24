# Verification: active Provider guide accuracy

- Date: 2026-10-24
- Result: PASS for the scoped local documentation checks; current-head repository CI and review remain merge gates.
- Change: [Issue #104](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/104), based on `7fe329b422c59c9b9854dad4f8399f6c7572eb22`.
- Scope: bilingual `docs/*/guide/providers.md`, records and changelog. No runtime/package-version changes.

## What was verified

The installed public CLI 0.4.16 rejects `abx sandbox url placeholder` with exit 1 and `unknown command 'url'`. Its actual sandbox help has no standalone URL or timeout command. The public Python a5 environment exports ProviderSandbox with create, connect, kill, close and application_client, and network.resolve is asynchronous. The installer CLI passes verify_handshake by default after consent; low-level installer tests without that callback do not prove execution-free CLI installation.

## Commands and results

- `python -m pytest client-sdk/tests/test_providers/test_node_doctor.py client-sdk/tests/test_providers/test_manifest.py client-sdk/tests/test_api/test_network.py -q`: 86 passed in 1.00 seconds.
- Parsed both guides' Python blocks with ast.parse and checked 40 relative link targets: passed after correcting an initially mistyped reference filename during editing.
- `make hygiene`: passed.
- `git diff --check`: passed; repository health: 106 PASS, 1 existing warning, 0 failures.
- Independent cross-review: actual entries, both languages, four Python blocks per guide and all relative links checked with no blocking finding. The review caught and corrected an accidental product-name substitution before commit.

## Observable behavior and existing real evidence

[Public package pilot 40115231628](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/actions/runs/40115231628) passed on Express and OpenSandbox with CLI 0.4.16 and Python client/server 0.3.1a5. It exercised source launch, named commands through CLI/Python/HTTP, wrong-token rejection, runtime source identity, process/file operations and confirmed removal of owned sandboxes/prepared artifacts. That run validates the unchanged runtime, not every command in the older speculative table.

This change deletes inaccurate mappings and links existing detailed guides. It does not add cloud behavior, rerun the 92-case matrix, or claim model/PTY/interpreter coverage. Previously merged evidence and historical design records remain intact.

## Cleanup and limitations

These document, parser and SDK introspection checks created no cloud resources. The illustrative creation example now cleans up its single owned sandbox; the connect example closes its client and directs the user to the launch guide for sandbox/build-artifact cleanup. Full cloud execution of every prose example is not claimed.
