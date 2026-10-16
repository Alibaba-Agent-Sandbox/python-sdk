# Verification: complete CI for stacked pull requests

- Date: 2026-10-16
- Result: PARTIAL
- Change: [issue #37](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/37); [PR #33](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33)
- Scope: `.github/workflows/ci.yml`, bilingual contributor guidance, changelog and these engineering records.
- Environment: Linux; authorized GitHub token supplied in memory; no secret values recorded.

## What was verified

Before the change, the stacked PR's latest head had only the successful Markdown
check. The CI pull-request base filter excluded it. The filter is removed while
main-only push selection and every existing job remain unchanged.

## Commands run

Workflow parsing and structural comparison against `git show HEAD:.github/workflows/ci.yml`;
`git diff --check`; repository hygiene and health checks. Remote CI execution and
results are recorded below after publication.

## Results

- Initial GitHub audit: the complete CI matrix is absent from this stacked PR.
- YAML parsed with PyYAML BaseLoader: PASS. The original main-only pull-request filter
  is removed, the push filter remains main-only, and parsed job definitions match exactly.
- `git diff --check`: PASS.
- `bash scripts/check-no-local-paths.sh`: PASS.
- Repository health: FAIL; 105 PASS, one warning, one pre-existing missing archive translation failure. New records did not add failures.
- Remote matrix execution pending publication; no remote pass claimed yet.

## Cleanup

No cloud resources were created. No existing developer work was staged.

## Not verified

This change triggers existing validation; it does not establish clean public
package installation, hosted MCP deployment, IDE acceptance or other-provider cloud support.
Existing product and repository-health limitations remain blocking where applicable.
