# Verification: Unused-code cleanup acceptance

- Date: 2026-10-27
- Result: PASS for the merged scoped implementation and its observed post-merge gates.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/146
- Implementation PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/147
- Verified merge commit: `c7a66351127731132fb94937a1ba45aa70bf71fa`
- Record update scope: move the accepted decision to implemented, update its index, and add this receipt. No runtime, dependency, image or public contract changes.

## Verification

Latest implementation-head CI at 9aeb27bb0ce5853c8949b5fa3f94bd81d1f39519 passed all Python 3.10/3.11/3.12 client/server jobs, public contracts, runtime fixtures, Node provider engine and Docs links. Post-merge CI also passed.

Real-component acceptance totals 130 passing cases across the initial 129-pass run and a corrected single-case CLI invocation. Eleven optional/provider/conditional cases were skipped and two slow cases deselected. The initial local server run has 878 pass / 2 altered-HTTP failures; independent negative controls reproduced local forwarding effects and the original assertions passed in the remote matrix. Those failures remain in the original evidence and are not relabeled as local passes. Both package builds, type markers, clean installation, lint/format/types and repository health passed.

Run-scoped janitor dry run reported zero candidates. Subsequent independent inventory listed zero total sandboxes. No key preparation or renewal was attempted. No package version was changed or manually published.

Remote evidence:
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40477035278
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40477035155
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40477906508

## Historical evidence and metadata checks

The [original verification](2026-10-27-dead-code-cleanup.md) is unchanged and retains initial failures, skips, source/artifact hashes and limitations. This new receipt adds verified acceptance rather than rewriting that history.

The lifecycle update requires document/link/record/diff checks and its current-head CI before merge. No new cloud run is needed to validate this metadata-only update. The prior real-component results are attributed to the implementation, not presented as a new execution.

## Metadata verification

- PASS: scoped Markdown local-link check, seven-section/status consistency and `git diff --check`.
- PASS: `bash scripts/check-repo-health.sh` (full actual counters in the task verification log).
