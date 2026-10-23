# Provider exact workflow operations

Result: PARTIAL

Date: 2026-10-23. Scope: Provider and shared project wire adapters, protocol contract, current provider fixtures and examples on `feat/template-workflows-20261023`. Standard maintained E2B clients and their licensed sources are unchanged.

## Implemented behavior

Provider manifests require operation contract 1, explicit CLI/Python operation lists and workflow input/startup arrays. The retired coarse interpreter feature is rejected. Runtime EPP contracts must agree with the manifest. Install/update consent includes exact operations and workflow boundaries.

Public lifecycle/files/exec dispatch is guarded by exact declared operations. Interpreter execution, persistent default execution, context operations and streaming have separate permissions. The native unary wire adapter implements stateless execution using a temporary context with deletion in `finally`; the engine passes stateless mode to the CLI implementation without requiring public context APIs. Unary callbacks fail before I/O. Missing interpreter routes propagate their error and never invoke shell.

Application endpoint hooks preserve provider, sandbox, port, gateway audience, path mode and expiration. Native bindings explicitly select prefix semantics; engine/EPP bindings preserve the adapter descriptor. Application authentication is supplied separately by the application client.

Provider content identity hashes actual installed plugin source, or the complete shipped native package source/config. Same-version content replacement changes identity. Credential/state/cache files are excluded; symlinked source is rejected. External native providers must supply their own identity implementation rather than reusing a hash of this SDK.

## Executed verification

Environment: Node 22.22.2; isolated Python 3.11 development environment.

- PASS: `pytest client-sdk/tests/test_providers client-sdk/tests/test_protocol/test_code_interpreter.py -q --disable-warnings`: 496 passed, 22 skipped. Skips are existing optional CLI-checkout/backend requirements; none are live-backend acceptance.
- PASS after endpoint/consent follow-up: `pytest client-sdk/tests/test_providers/test_workflow_operations.py client-sdk/tests/test_providers/test_installer.py client-sdk/tests/test_protocol/test_code_interpreter.py -q`: 124 passed.
- PASS: scoped `ruff check` and `ruff format` for Provider sources, protocol contract and affected tests.
- PASS: from `client-sdk`, `mypy src/agent_sandbox/providers src/agent_sandbox/protocol/contracts.py --no-incremental`: 38 source files. The existing unused mypy override notice remains informational.
- Regression coverage includes code.execute-only adapters without public contexts, cleanup after execution failure, exact engine context routes and escaped identities, callback rejection before payload, consent on operation changes, preservation of operation-signed endpoint metadata, and same-version plugin replacement.

## Remaining gates and cleanup

Full package checks, real cloud E2E and final reviewed CLI/SDK/OpenSandbox integration are coordinated separately. The local runs created no cloud resources. Backend mocks and local process fixtures do not certify a real provider. The implementation is not described as merged or accepted until owner CI and required review pass.

[Owner Issue](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/88).
