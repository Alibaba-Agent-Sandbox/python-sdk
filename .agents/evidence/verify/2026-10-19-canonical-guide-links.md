# Verification: canonical active-guide links — 2026-10-19

Result: PASS for public destinations and documentation scope; current-head hosted gates required before merge.

Canonical https://www.agent-sandbox.cn/ and https://registry.agent-sandbox.cn/ independently return HTTP200. Updated active English/Chinese documentation indexes/provider references and CLI installation/engine references where present. The .com registry does not resolve from this environment; .com website returns different/older content. No DNS, runtime endpoint, dependency, credential, repository visibility or historical evidence changed.

The change follows the release-readiness review. Repository health/hygiene, exact changed paths and latest-head CI are recorded before delivery. Existing installed artifact/cloud results remain linked from the accepted release records, without claiming a new E2E run for link-only edits.

Local gates: repository health 106 PASS/1 WARN/0 FAIL; hygiene and diff whitespace PASS. Only docs/records/CHANGELOG change. Current-head hosted gates remain required.
