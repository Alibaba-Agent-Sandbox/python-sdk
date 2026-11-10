# Decision: Index recent changes to python client, server and runtime boundaries
Status: proposed

## Problem

Recent implementation, user-experience changes and delivery status are spread across
owner records, pull requests and workspace reports. The user requested that recent
changes be retained under each owning repository's `.agents/` and pushed.

## Decision

Keep this dated index in python-sdk; link existing canonical decisions and immutable
verification instead of copying their reports or rewriting historical acceptance.
This index adds no product behavior and does not change any older ADR's lifecycle.

### Owner changes and canonical records

The candidate makes the exactly matching local server an optional [server] extra, preserves independent standard/async/Provider/HTTP client entry points, and removes the misleading decorator-factory execution shortcuts. Real server registration and deployed remote command invocation remain distinct. Managed Agents and Express SDK work already have their own earlier records.

- [Client/server installation and invocation boundaries](../../../notes/proposed/architecture/2026-11-10-client-runtime-boundaries.md).
- [Isolated package and local HTTP verification](../../../evidence/verify/2026-11-10-client-runtime-boundaries.md).
- [Managed Agents implementation](../../../notes/proposed/architecture/2026-11-05-managed-agents-api.md).
- [Managed release-candidate evidence](../../../evidence/verify/2026-11-06-managed-agents-release-candidate.md).
- [Express SDK completion](../../../notes/implemented/feature/2026-11-05-express-sdk-completion.md).

### Mainline and candidate boundary

- Mainline observed: `eb7c980a825d804483474923938277700e048571`.
- Candidate/source observed before this records commit: `2abbdb02500c12dd8841ab32211372c3ef883c12`.
- [python-sdk PR #160](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/160), OPEN and Draft at the recorded query; not merged.
- The unified source CLI is different from published CLI 0.5.10. This task does
  not issue npm/PyPI releases, deploy sites or certify changed templates.

Recent mainline changes, inspected from the refreshed Git history:

| Date | Commit | Change |
| --- | --- | --- |
| 2026-11-10 | [eb7c980a825d](https://github.com/Alibaba-Agent-Sandbox/python-sdk/commit/eb7c980a825d804483474923938277700e048571) | docs: replace community QR image and join link (#159) |
| 2026-11-10 | [75c7b8b01268](https://github.com/Alibaba-Agent-Sandbox/python-sdk/commit/75c7b8b01268637ea1bb52b60f096436c0782988) | docs: announce preview release schedule and developer community (#158) |
| 2026-11-06 | [fa15efd7e679](https://github.com/Alibaba-Agent-Sandbox/python-sdk/commit/fa15efd7e679b1697e140363a395d998cde7f66a) | Merge pull request #156 from Alibaba-Agent-Sandbox/feat/managed-agents-api-20261105 |

### Remaining delivery limits

The candidate PR remains Draft for coordinated delivery and its complete-suite/E2E acceptance. Recorded isolated wheel installation and localhost HTTP success do not establish full real-backend acceptance. The native OpenSandbox thin-adapter design discussed on November 5 remains a proposal; this index does not introduce an adapter or extra.

## API Design

N/A — this decision does not involve API changes. Existing runtime, credential,
source identity and resource ownership contracts remain with their original owners.

## Alternatives considered

- A workspace-only summary cannot travel with an independent checkout.
- Copying all cross-repository reports duplicates authority and may expose private logs.
- Marking all proposed records implemented would confuse source work with accepted delivery.
- Combining unrelated local changes or permission-only differences in this commit
  would conceal the actual records scope.

## Dependencies

Existing owner records and GitHub PR/commit state. Coordinated implementation is
tracked in [CLI Issue #244](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/244).
Each repository retains its own branch, record, verification and push.

## Test Strategy

Check the new record structure, relative links, pinned Git source revisions and
scoped diff; run the owner's applicable documentation/health checks. Query PR/CI
state separately from local checks. Do not run cloud tests solely to validate prose.

## Acceptance criteria

- Recent owner work is reachable from `.agents/README.md` with dated source references.
- Merged, Draft, failed, unrun and planned work remain distinguishable.
- Existing historical evidence and unrelated work remain intact.
- Documentation checks and remaining gates are recorded; scoped commits are pushed
  to task branches and remote branch hashes are independently compared.

## Evidence

- [Records verification](../../../evidence/verify/2026-11-10-recent-change-index.md).
