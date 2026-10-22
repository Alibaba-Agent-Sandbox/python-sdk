# Verification: accepted removal of retired compatibility

- Date: 2026-10-22
- Result: PASS for this repository's delivered scope
- Code pull request: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/85
- Verified merged source: `d1a54f78e447bc67b90dbfdf48168b020275c871`
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/84 (verified closed after merge)

## Acceptance evidence

The client/server Python 3.10, 3.11 and 3.12 matrix, package build, pinned upstream contract, hygiene and Markdown-link jobs all succeeded. Four real-cloud SDK checks passed with owned cleanup.

The exact reviewed-head checks and actual remote merged state were inspected before acceptance. Required gates were not bypassed. Historical local failures and skips remain in the original [verification record](2026-10-22-remove-legacy-compatibility.md).

## Record lifecycle

Move the accepted architectural note to `implemented`, retain its original verification history, and update the local index. This follow-up changes engineering records only. Its document/link checks and normal remote CI apply.

## Coordination and cleanup

The cross-repository CLI cleanup is tracked at https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/103 . Shared contracts land before consumers. Cloud fixtures cleaned their owned resources; the record update creates none. No release or manual deployment was performed.
