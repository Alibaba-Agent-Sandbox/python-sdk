# Verification: workspace-source delivery review

- Date: 2026-10-16
- Result: PASS for workspace install and real-cloud runtime; final evidence-only head CI is checked before merge.
- Change: PR 29, synchronized with documentation merge `991c36c`.

## Scope and actual results

The source mapping in root `pyproject.toml` remains unchanged from the reviewed
packaging fix `b6e03a5`. The newer main branch adds the complete Chinese archive
from PR 40; its only conflict with this branch was the Unreleased changelog.
Both the Added archive entry and Fixed uv entry were preserved. The original
English archive and historical evidence remain unchanged.

- Previous head `b6e03a5`: nine successful GitHub checks, including both packages
  across Python 3.10/3.11/3.12 and package build/dist validation.
- Current repository health and hygiene: PASS after merging the archive fix.
- Synchronized head `42f3ff2a626b21ed62f03061921d6a2e55e673bb`: nine successful
  GitHub checks, including both packages on Python 3.10/3.11/3.12 and package build.
- A fresh Python 3.11.15 virtual environment installed both editable SDKs using
  the original uv workspace command without source overrides: PASS, 87 packages.
- Client packaging: seven passed; server packaging: five passed. The real uv
  parser/negative-control regression executed rather than skipping.
- Exact synchronized branch, installed in that fresh environment: three real
  Express tests passed in 9.74 seconds (create/info/kill, independent connection
  sharing, text/Unicode file roundtrip). The owned tracker recorded three
  sandboxes and `leaked_after_cleanup=0`.
- The final follow-up changes only this verification record; its exact-head CI
  is inspected before merge.

## Remaining acceptance

The original complete cloud run exposed incorrect fixture credentials and
missing catalogs; report review exposed unexecuted CLI checks. The separate
[harness correction in PR 33](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/33)
then passed the complete make e2e suite: 113 passed, four explicitly unavailable
native-backend skips, two slow deselections and one documented platform KI-009
expected failure. That broader run uses its own lifecycle/harness source tree;
it is not misrepresented as a direct run of this branch. The three direct real
checks above establish this workspace branch's own runtime behavior.

This packaging fix does not imply public package publication or other-provider
backend acceptance. Exact scoped manifests are unchanged by the final record:
root workspace `6dc8e0ff4c8d711ec1f39523213fc65ac7b4b2b4`, client manifest
`c0627b361c434440e360dd3cc627ef23df66fc37`, server manifest
`cdadc18b652818c9b7583e2791defa3b7a155aa3` (Git blob IDs).
