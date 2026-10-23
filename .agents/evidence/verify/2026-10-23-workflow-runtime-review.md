# Verification: workflow runtime implementation and adversarial corrections

- Date: 2026-10-23
- Result: PARTIAL
- Change: strict template specification 4 / operation contract 1 implementation, proposed template-workflow-contract ADR; refs https://github.com/alibaba-agent-sandbox/python-sdk/issues/88.
- Environment: Python 3.11.15, editable local client/server 0.3.0, lockstep distributions; no package publication.
- Credentials: supplied only in environment for separately recorded cloud runs; no values recorded here.

## Behavior under review

Prepared-image and explicit external-service workflow launch validates the manifest and actual provider operations before mutation. Image references require a SHA256 identity; source preparation and unresolved managed references fail before create. Application deployment topology remains explicit and is refused by the standalone launcher. Intent precedes create, on_created records a known ID before transport preparation, uncertain creation is never replayed, and cleanup preserves residual IDs. Public exec/interpreter APIs gate their exact operations. No guessed Connect interpreter routes or shell fallback remain in project adapters. Standard pinned clients retain their independent contract.

Application HTTP is resolved separately from internal envd transport. The descriptor binds provider/sandbox/port/audience and expiry. Requests preserve sandbox path prefixes and opaque signed query values. Application and gateway authentication are separate; redirects, recursive encoded path traversal, ambiguous query keys and authority headers are rejected. Discovery requires exact integer protocol 2 before named-command payload.

## Independent adversarial review

Two rounds were performed by a separate agent against runtime counterexamples, not only implementation assertions.

Round 1 reproduced and corrected six findings: HTTP-client close could prevent owned deletion; mutable image references lacked immutable identity; recursive path/header/query confusion; endpoint failure could leave a startup drain; protocol version coercion; and an ID known before transport preparation was not journaled through cancellation/failure. Rechecks confirmed each corrected case. An additional claimed tuple-gate problem was withdrawn because the gate intentionally uses any(); it was not a defect.

Round 2 independently rechecked those six corrections, then found two further defects: journal I/O failure could prevent cleanup, and recursively equivalent duplicate query keys could be accepted. Both were corrected and independently confirmed; see [second-round confirmation](2026-10-23-workflow-round2-independent.md). This review does not establish platform-native interpreter support, real provider acceptance or CI completion.

## Executed checks

- PASS: final pre-metadata-follow-up client suite `pytest tests/ -m 'not integration' -q`: 2165 passed, 23 skipped, 10 deselected. Skips retain optional backend/checkout requirements; they are not live acceptance.
- PASS: `pytest client-sdk/tests/test_api/test_application_binding.py client-sdk/tests/test_api/test_workflow_launch.py -q`: 50 passed after round-2 fixes.
- PASS: final application metadata preservation regression and capability discovery file: 17 passed. Fractional application resource metadata is retained without coercing it into sandbox CPU/memory fields.
- PASS: `make lint format-check typecheck`: both packages lint/format passed, server 56 and client 98 mypy source files passed.
- PASS: `make build dist-check`: both distributions build, all four twine artifacts pass, both py.typed markers present, combined wheel install/import works.
- PASS: repository health: 106 passed, 1 warning, 0 failed. The warning is the existing missing maintainer release runbook recommendation.
- FAIL/PARTIAL: `make ci` stopped in unchanged server tests: 872 passed, 1 skipped, 3 failed. Missing pip in the initial uv-created environment explained the package-list failure; pip was installed. Focused rerun of those three yielded 2 passed and 1 failed: the raw WebSocket handshake received HTTP 501 instead of expected 400 in this environment. The raw transfer-encoding test then passed. Assertions and server security behavior were not weakened. Latest full server rerun and remote Python 3.10/3.11/3.12 CI remain separate gates.

## Reviewed source identities

- `client-sdk/src/agent_sandbox/api/workflow.py`: `2c54ea2aca38a8e44c14528ec971abc431b7003eaf7d21d8b19a0a81a2300c75`.
- `client-sdk/src/agent_sandbox/api/server_client.py`: `8f91f66b57184baad33bfef7e7ced66743eb69c7e01b3ecdc02bcebc581945c5`.
- `client-sdk/src/agent_sandbox/api/sandbox.py`: `cc9c5d689f8b0d1e28bf49f7d7ea55d94bf27b7ba9ab47fbeb52254316463f85`.
- `client-sdk/src/agent_sandbox/api/code.py`: `39648e10ab8a21999b8d00dbb89e09ebedfdcdda9a6dc88816b33281b2840b2d`.

## Cleanup and remaining gates

The local mocked/loopback checks created no cloud resources. Real-cloud make e2e, the cleanup dry run and final latest-head CI results are recorded separately. The new cross-repository portable-source OpenSandbox scenario requires its own Docker/provider workflow; successful native-standard calls or old maturity receipts do not certify that new workflow. Keep this PR draft until mandatory gates and dependency order are satisfied. No release is requested.
