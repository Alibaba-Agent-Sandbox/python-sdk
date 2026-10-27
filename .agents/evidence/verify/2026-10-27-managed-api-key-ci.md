# Verification: Managed API-key remote CI acceptance

- Date: 2026-10-27
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/145.
- Result: PASS for the tested feature implementation and supported CI matrix. Final record-only head is checked again before merge.
- Tested source: d493cb6f21af0bd0cd8a46acc6c5e286f5aae454; client/server 0.4.0a6, no version bump or publication.
- Environment: GitHub Actions Ubuntu; Python 3.10, 3.11 and 3.12.

## What was verified

The repository's complete CI passed for the managed-key feature. This provides supported-environment coverage beyond the local runtime results in [the initial evidence](2026-10-27-managed-api-key.md). The local malformed-WebSocket baseline does not reproduce in that CI run; its cause is not claimed to be fixed.

## Commands run

The [CI workflow run](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40464862377) executed the repository workflow: Ruff, format check, mypy and full client/server tests for each supported Python version, paired package build/twine/py.typed/combined install, standard E2B callable contract, Python-to-Node engine integration, public runtime fixture checks and hygiene. The [Markdown link run](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40464862356) also passed.

## Results

All 13 reported checks passed: client-sdk and server-sdk on Python 3.10/3.11/3.12, package build, pinned E2B contract, Node provider engine, both public runtime fixtures, hygiene and Markdown links. No required review or check is bypassed. The final documentation/record head is rechecked through normal CI before merge.

## Cleanup

This workflow acceptance does not claim new billable cloud coverage. Real AK/SK-only SDK acceptance and its exact owned-key/sandbox cleanup are recorded separately in the initial evidence. No credentials or raw cloud logs are included.

## Problems found

Local baseline #144 remains an environment-specific test follow-up. Required repository CI for this source passed; preserving a local failure report is not a claim that it was repaired.

## Not verified

No package publication, Windows ACL matrix, alternate region or separate restricted RAM identity was added. The new provider operations must land in [CLI PR #202](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/202) before this consumer. Merge state and final-head checks are verified from the PR itself, not inferred from this record.
