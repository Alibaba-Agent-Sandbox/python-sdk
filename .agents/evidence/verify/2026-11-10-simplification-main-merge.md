# SDK simplification mainline reconciliation — 2026-11-10

Scope: merge the already published simplification branch with fixed main
`eb7c980a825d804483474923938277700e048571` for
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/160 .

## Diagnosis and resolution

GitHub reported the PR as open/draft with `mergeable=false` and
`mergeable_state=dirty`. Repository Actions were enabled; CI and Docs workflows
were active and had succeeded for other commits earlier the same day. There were
no Actions runs for the simplification head. Its queued check suite belonged to
the Cursor app, not GitHub Actions. GitHub documents that pull_request workflows
do not run while a PR has a merge conflict:
https://docs.github.com/en/actions/how-tos/troubleshoot-workflows .

A read-only merge-tree probe identified only the Unreleased CHANGELOG insertion
as conflicting. The merge retains both the client/runtime boundary entries and
mainline preview/community documentation. README announcements, QR image and
PR #158/#159 engineering records remain intact. No runtime, dependency, release
version, workflow trigger or approval policy was changed to unblock CI. The
published branch was merged, not rebased or force-pushed.

## Local verification

- Targeted packaging, release-validation, version-lockstep, missing-server and
  command-registration tests: **88 passed** on the existing Python 3.11 venv.
- Repository hygiene and git diff whitespace checks passed.
- Changed Markdown local-file links: 9 files checked, no missing targets. This
  does not check remote HTTP links or anchor fragments.
- Current mainline QR asset and four prior engineering record files matched the
  fixed upstream bytes. Both README announcement and community lines matched
  upstream verbatim.

The broader earlier SDK verification and its recorded raw-network failures remain
in `2026-11-10-client-runtime-boundaries.md`; this documentation merge does not
claim a new full-suite or cloud result. Remote CI must run on the pushed merge
commit before the PR can satisfy its merge gates.
