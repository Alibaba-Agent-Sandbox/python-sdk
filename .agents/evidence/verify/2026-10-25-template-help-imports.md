# Verification: Template help imports in paired a5 candidate

- Date: 2026-10-25
- Result: PARTIAL — local candidate checks below; exact-head remote CI, independent review, merge and actual publication remain separate gates.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/128
- Base: merged public-a4 guidance `b1dbc5698ed42b9a87ab0ac6df452d5d187dd0a0`.
- Environment: Linux, Python 3.11 development environment. Public negative proof used an independent official non-all a4 install, Python 3.13.13, with no e2b distribution.

## What was verified

Public a4 Template and AsyncTemplate help displayed imports from e2b, which is not
installed by this project. The actual import failed with ModuleNotFoundError.
All corresponding names already exist in the agent_sandbox root exports. The
[frozen public-a4 negative observation](2026-10-25-public-a4-template-help-negative.json)
lists all 24 affected docstrings in five modules; they are ordinary first-party
Examples, not labeled third-party migration comparisons.

The candidate changes only these 24 help imports and three paired version/pin
declarations to a5. Execution AST after docstring removal is identical in all five
modules. NOTICE, MIT LICENSE and original SOURCES hashes are byte-identical.
Standard ApiParams and callable signatures are unchanged. No dependency, alias,
runtime behavior or release retry mechanism is added. See the
[candidate comparison](2026-10-25-template-help-imports.json).

## Commands run

```bash
python -m pytest client-sdk/tests/test_api/test_template_help.py -q --no-cov
python -m pytest client-sdk/tests/test_api/test_template_help.py client-sdk/tests/test_api/test_standard_contract.py client-sdk/tests/test_api/test_provider_docstrings.py -q --no-cov
make lint format-check typecheck
make build dist-check
bash scripts/check-repo-health.sh
make hygiene
```

The new regression reads actual help on public Template/AsyncTemplate methods,
the public builder instance and logger/readiness helpers; it executes only the
displayed import statements and confirms each imported object is the actual root
export. No cloud build/network operation is invoked. Before the correction all
24 cases failed; afterward all 49 focused cases passed, including existing
standard contract and 12 Provider help/signature tests.

Ruff, format and both-package mypy passed. Both lockstep wheels/sdists built;
twine, both py.typed markers and fresh combined wheel installation/imports passed.
The client full suite passed: 2313 passed, 26 skipped, one warning (128.47s).
The local server full suite returned nonzero: 878 passed, two failed (317.14s):
`test_upgrade_without_a_key_is_a_400_not_a_hang` and
`test_transfer_encoding_rejected_in_policy_mode`. These low-level HTTP status
assertions also failed in the earlier a4 local environment; they are retained
as failures, not marked passing or weakened. The required remote matrix must
independently pass on the actual candidate head. Repository health passed with 106 PASS, one existing
release-runbook WARN and zero FAIL; hygiene and diff checks passed. No a5 package
has been published.

Installed candidate wheels also passed 24 actual Template help imports and 12
Provider help/signature checks without e2b, plus pip check. Real local HTTP
health, shell output `4`, file roundtrip and independent absence of the owned
server process passed: [candidate HTTP receipt](2026-10-25-template-help-candidate-http.json).
This is candidate-wheel evidence, distinct from public PyPI installation.

## Previous real-component evidence and cleanup

[Public-a4 examples](2026-10-25-public-a4-examples.md) preserve the later actual
14-cloud run, 29 independent typed-not-found results, local 10-check runner and
negative timeout continuation with 27 independently absent owned child processes.
They remain a4 results, not a5 candidate verification. Original a2 browser failure
and all earlier merged evidence are unchanged. No cloud resources were created by
these help-import regressions or records changes.

## Not yet verified

Exact-head required CI, independent review, normal merge, immutable a5 tag and
official publication/readback remain pending. After publication, compare all four
official file hashes with preserved artifacts; fresh-install non-all client a5,
verify its automatic server dependency, pip check, 12 Provider help/signatures,
24 Template help imports, actual local HTTP/file operations and owned-process
absence. Installation guidance still selects the currently verified public a4.
This patch does not certify all templates/platforms or production workloads.
