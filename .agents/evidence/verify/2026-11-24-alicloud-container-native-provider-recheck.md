# Verification: Container Edition Python Provider follow-up review

- Date: 2026-11-24
- Change: [PR #168](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/168), reviewed starting revision `ab789cc27b77160aa1e9cc7f6419461fb5e0ccfc` and its follow-up patch
- Result: BLOCKED for live ACS/ACK acceptance
- Package under test: Client and Server SDK 0.4.0a7 from source, and locally built distributions
- Environment: Debian 13, Python 3.12.15

## What was verified

Two independent reviews checked the Container Edition routes and SDK behavior, and checked the user guides and acceptance prerequisites. The review traced the E2B interpreter's [HTTP route](https://github.com/e2b-dev/code-interpreter/blob/db9fdb1cfe6552455d58b1690971bdd3052538c6/template/server/main.py#L81-L129) into its [response wrapper](https://github.com/e2b-dev/code-interpreter/blob/db9fdb1cfe6552455d58b1690971bdd3052538c6/template/server/stream.py#L34-L40). The wrapper emits the public `end_of_execution` event even though the inner iterator consumes its own completion message. Executing the original parser on a well-formed result-only response returned exit code zero. The follow-up rejects responses without completion, with regressions for both gateway layouts.

## Commands run

- From `client-sdk`: `pytest -q tests/test_providers/test_alicloud_container.py tests/test_providers/test_bound_client.py tests/test_providers/test_registry_scoping.py tests/test_providers/test_engine_alicloud_container.py`
- From the repository root: `python -m pytest e2e/test_alicloud_container_native.py e2e/test_08_providers.py -k 'alicloud_container_native or container_refuses_without' -ra`
- `make lint format-check typecheck` and `make build dist-check`
- `bash scripts/check-repo-health.sh`, `make hygiene` and `git diff --check`

## Results

| Scenario | Result | Notes |
| --- | --- | --- |
| Provider, bound client and registry tests | PASS | 47 passed, 4 external-engine cases skipped. The new result-only NDJSON regression rejects incomplete responses. |
| Provider credential refusal | PASS | One case passed without a configured Container Edition cluster. |
| Live lifecycle and interpreter cases | BLOCKED | Two cases skipped before I/O. No Container Edition manager endpoint or Key was available from the workspace configuration or process environment. |
| Lint, formatting, types and distributions | PASS | Both packages checked. Wheel-only imports and a local HTTP packaging probe passed. |

## Cleanup

The targeted tests used controlled transports or locally owned test processes. The live cases made no requests. No cloud resources were created.

## Problems found

The previous interpreter fixture used HTTP EOF as a success signal. The review also found that the initial guide required Jupyter for basic use and that the provider E2E credential-refusal check assumed the container provider was an external plugin. The guides now show basic and interpreter usage separately. The live test distinguishes an ordinary SandboxSet from an interpreter SandboxSet, uses cluster-specific credential masking, and verifies absence of returned IDs against that cluster. Its cleanup does not prove absence for a create that returned no ID.

## Not verified

Live ACS/ACK acceptance requires an existing cluster manager endpoint, its cluster Key and a SandboxSet for each selected case. The prerequisite [PR #167](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/167) also remains a draft. No artifacts were released.
