# Verification: workflow migration real-cloud acceptance

- Date: 2026-10-23
- Result: PASS for the executed Express/native-standard and local-component suite; portable-source OpenSandbox launch remains a separate gate.
- SDK source: https://github.com/alibaba-agent-sandbox/python-sdk/commit/2c7c4dd554d0623143b7e6277faf0019ca3138ee.
- CLI implementation: https://github.com/alibaba-agent-sandbox/agent-sandbox/commit/128f8dc6c71a9be9e28a9608e1e19f1b2e44a374. The production dist used the same endpoint-guard source; later fixture/golden updates do not change runtime behavior.
- Owner Issue: https://github.com/alibaba-agent-sandbox/python-sdk/issues/88.
- Environment: Python 3.11.15, Node 22, editable client/server 0.3.0 and source-built CLI, real configured Express account plus local HTTP components. Credentials were read from ignored configuration into subprocess environment and masked before any captured output; values are not recorded.

## Executed command and scope

`make e2e` executed the ordinary real-cloud suite, followed by the repository janitor dry run. No retries of uncertain creates or restored legacy CLI flags were added. The provider-live CLI scenario uses current create/info/list/exec/kill syntax and an explicit provider. Project interpreter checks assert exact unimplemented adapter operations before I/O; they do not infer absence in the upstream platform. Pinned standard clients exercise their own real contract separately.

## Results

- PASS: 120 tests; 8 conditional skips; 2 slow cases deselected; 0 failures; 667.59 seconds.
- PASS: platform/authentication, sandbox lifecycle, command execution/streaming, files, in-sandbox server operations, declarative execution, Express project SDK, current Express CLI, MCP, named string arrays and integers, agent transport, local typed SDK and server HTTP routes.
- PASS: pinned standard create/connect/list/exec contract. Conditional pause and snapshot were skipped, not certified.
- SKIP (4): OpenSandbox, CubeSandbox, E2B and container project plugins are not installed in this Express suite environment. OpenSandbox Docker verification is owned by the Provider PR; these skips are not portability evidence.
- SKIP (2): volume mount cases require the explicit ABX_E2E_VOLUME_MOUNT opt-in.
- SKIP (2): standard pause requires an enabled template; snapshot requires MicroVM and allowlist.
- DESELECT (2): slow cases excluded by the repository ordinary e2e target.

Prior migration runs remain failed historical observations: 116 passed / 9 skipped / 3 failed and 118 passed / 8 skipped / 2 failed. Their remaining old rename/CLI/pause/interpreter expectations were migrated to current public contracts. No compatibility entry was restored.

## Cleanup

Run identifier: e2e-workflow-20261023-4274abf7. Fixtures tracked and killed their created resources; the provider-live cases use their own finally cleanup, and the CLI scenario confirmed idempotent deletion of its returned ID. The post-suite `python scripts/e2e-cleanup.py --all-tagged` dry run reported 0 candidates out of 0 listed, sandboxes_killed=0. No cloud sandbox remained listed after this run. The janitor was not asked to delete another run's resources.

## Limits and next gates

This pass does not certify Python source preparation, managed launch without immutable identity, unsupported project interpreter mappings, or new portable-source OpenSandbox workflow execution. Those boundaries stay explicit. Latest-head Python 3.10/3.11/3.12 CI remains required. Local unchanged server framing/handshake tests received HTTP 501/502 under this environment; remote server CI, without weakening those assertions, is the authority for that gate.
