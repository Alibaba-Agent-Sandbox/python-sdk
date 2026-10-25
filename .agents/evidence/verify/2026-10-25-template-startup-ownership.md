# Verification: template startup ownership documentation

- Date: 2026-10-25
- Result: PARTIAL — existing public-package observation passed; local documentation checks passed; exact-head required CI and merge are pending.
- Base: ec3bcf1eb788acb42fea32dec06537ef915e9ba2.
- Change: bilingual template consumption/authoring/design overview prose, SDK Skill specification number and owner records only. Client/server remain public 0.4.0a6; no source implementation or package version change.

## Real public-package observation

A bounded owner experiment used actual official client/server 0.4.0a6 and public CLI 0.5.5. The advanced preparation stage contained only template.yaml with native startup/readiness fields removed; the original application manifest was passed unchanged to Python. This is one explicitly inspected preparation path, not a generic promise about empty CLI flags or all providers.

Before Python startup, actual port 9000 was closed and no application server process existed. After startup, the port was open, exactly one server existed, and its token was present and matched. Actual HTTP application calls returned 200 with result 8 for the correct token and 401 for both missing and incorrect tokens. Bearer and the existing same-value application fallback header were tested together. Neither credentials nor resource IDs are recorded here.

The exact one owned sandbox was independently absent via typed lookup after cleanup; the exact one owned prepared template was independently absent with E2001 and its alias absent. No owned resources remained. This observation does not certify other preparation paths or all providers. No candidate runtime was used or needed.

## Owner checks

`bash scripts/check-repo-health.sh`: 106 PASS, one existing missing release-guide recommendation WARN, zero FAIL. `make hygiene` and `git diff --check`: PASS. No runtime/tests changed; no additional cloud resources were created for prose checks. Full exact-head remote checks remain pending. Earlier full local checks from a separate investigation are not a pass for this head: the server suite observed one WebSocket status mismatch (879 pass, 1 fail); the cause was not established. No server behavior or gate is changed here. Remote required matrix results must be read for the exact new head.

## Not verified

This is prose only. No new whole-catalog, provider matrix, model or performance claim is made. Previous package and example receipts remain unchanged.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/133
