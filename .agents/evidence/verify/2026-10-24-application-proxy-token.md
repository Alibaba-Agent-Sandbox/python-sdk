# Verification: application token through OpenSandbox proxy

- Date: 2026-10-24
- Change: [Issue #99](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/99)
- Result: PARTIAL while real updated-client verification and CI are pending.
- Packages: matching client/server 0.3.1a4 candidate sources; no server runtime changes.

## What was verified

The original problem was reproduced through normal provider endpoints against one owned python-hello sandbox. [Probe 40109164062](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40109164062) used CLI 0.4.15, SDK 0.3.1a3 and fixed OpenSandbox 1.1.1: direct Bearer returned 200, proxy Bearer 401, proxy X-Access-Token 200. Successful calls checked the actual greeting. Independent sandbox cleanup passed. This probe establishes the existing protocol behavior, not the updated Python client's acceptance.

## Commands run

```bash
python -m pytest client-sdk/tests/test_api/test_application_binding.py -q
ruff check client-sdk/src/agent_sandbox/api/server_client.py client-sdk/tests/test_api/test_application_binding.py
ruff format --check client-sdk/src/agent_sandbox/api/server_client.py client-sdk/tests/test_api/test_application_binding.py
```

## Results

- Focused application boundary tests: 47 passed in 0.94s.
- Expanded application boundary, ServerClient model and sandbox-server helper regressions: 101 passed in 3.21s.
- Full client/server lint and type checks passed (98 client and 56 server source files). The first format check requested one line wrap correction; the corrected format check passed.
- Independent client review confirmed gateway header ownership, injected client defaults, retained Bearer compatibility and token removal without persisted generated headers.
- Complete updated-client proxy acceptance and full CI: pending, not counted as passes.

## Cleanup

The initial live probe used only its owned disposable sandbox and independently confirmed cleanup. Local header regressions use mock transports and create no cloud resources. Updated-client live cleanup will be recorded with its run.

## Problems found

The proxy strips Authorization. Adding a control-plane key would not fix this application-token failure. The server already implements the second header, so no new server protocol is needed. A second review identified injected HTTP client default headers as another gateway credential source; these are also protected from replacement.

## Not verified

This change does not establish all-template business correctness or real-model behavior. Full template matrix runs are tracked by the templates repository and remain separate from authentication acceptance.
