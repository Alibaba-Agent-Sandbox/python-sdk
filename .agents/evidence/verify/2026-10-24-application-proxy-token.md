# Verification: application token through OpenSandbox proxy

- Date: 2026-10-24
- Change: [Issue #99](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/99)
- Result: PASS for the application authentication fix; public release and all-template acceptance are separate gates.
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
- Local `make build dist-check` passed: both a4 wheels and source distributions, metadata, `py.typed` and a fresh combined installation.
- Full [CI 40110173595](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40110173595) and [Docs 40110173624](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40110173624) passed at runtime commit `588d126af9310ee5536ea631856b092b84c6ce6b`. CI includes Python 3.10/3.11/3.12 client/server suites, pinned standard contract, Python-to-Node engine, hygiene and package builds.
- Real [OpenSandbox T4 40110372103](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40110372103) passed against OpenSandbox 1.1.1. The default/direct, portable/direct and default/server-proxy python-hello paths each passed CLI launch, named application HTTP calls, Python `application_client` and prepared-image workflow. Two independent Node `ServerClient` proxy calls passed. Actual greeting responses were checked.
- Exact T4 inputs: provider `65d8e5a9c130f424c05a662fe430b0eb04793c0e`, CLI `80c45cd2594d0fc997badfd31246d60ffa434de5`, Python `588d126af9310ee5536ea631856b092b84c6ce6b`, Node `344d297df816063b6580d7f2bb34180111ad9a54`, templates `295aff8f45f710eadf46d164b7ce4150b2c914ec`. These were source candidates, not public-package installations.
- Raw protocol observations remain direct Bearer 200, proxy Bearer 401 and proxy X-Access-Token 200. The 401 is the reproduced upstream filtering behavior; the updated SDK passes through the existing accepted header.
- The final record-only commit does not change these tested runtime files.

## Cleanup

The initial live probe used only its owned disposable sandbox and independently confirmed cleanup. Local header regressions use mock transports and create no cloud resources. The updated-client T4 independently confirmed cleanup; its final cleanup step passed. No task-owned resource was reported retained.

## Problems found

The proxy strips Authorization. Adding a control-plane key would not fix this application-token failure. The server already implements the second header, so no new server protocol is needed. A second review identified injected HTTP client default headers as another gateway credential source; these are also protected from replacement.

## Not verified

This change does not establish all-template business correctness or real-model behavior. Full template matrix runs are tracked by the templates repository and remain separate from authentication acceptance.
