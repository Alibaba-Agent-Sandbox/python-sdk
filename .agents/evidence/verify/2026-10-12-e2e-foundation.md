# Verification: real-cloud E2E suite foundation (python-sdk)

- Date: 2026-10-12
- Change: ADR [`2026-10-12-e2e-suite-and-definition-of-done`](../../notes/implemented/process/2026-10-12-e2e-suite-and-definition-of-done.md)
- Result: PARTIAL (all runnable scenarios behave as recorded; the Docker/ACR custom-template flow is BLOCKED by registry upload throughput)
- Binary / package under test: `easy-sandbox` (`client-sdk`) and `easy-sandbox-server` (`server-sdk`) installed editable from the working tree at commit `e26562b`
- Environment: real Alibaba Cloud FC agent sandbox platform (cn-hangzhou), Python 3.12, Linux. Credentials: supplied via the gitignored `.env` (values not recorded)

## What was verified

The new `e2e/` pytest suite itself: that it authenticates against the real platform, creates, uses and destroys real sandboxes (envd data plane and the in-sandbox `easy-sandbox-server` from the `python-hello` template), tags and cleans up everything it creates, skips with an exact reason without credentials, and pins known product defects as strict xfails.

## Commands run

```bash
make e2e                                   # fast path
make e2e-all                               # slow tests + Docker/ACR flow
python scripts/e2e-cleanup.py --all-tagged # dry run: lists leftovers (none)
```

## Results

| Run | Selection | Result | Duration |
|---|---|---|---|
| 1 | `not e2e_slow` (fast path) | 67 passed, 13 xfailed (known issues KI-001 to KI-010), 0 failed | 8 min 8 s |
| 2 | `e2e_slow` and `e2e_docker` | 1 passed, 4 skipped (Docker/ACR flow), 1 xfailed (KI-008) | 4 min 41 s |

Skip reason of the Docker module, verbatim: `e2e_docker skipped: ACR push not usable from this host: a 2000 KB layer did not finish uploading within 120s (upload throughput <17 KB/s to the ACR public endpoint); real template images are far larger` (KI-011).

The 13 xfails are strict: when a defect is fixed the test XPASSes and fails the run, forcing the marker to be removed. They are catalogued in [`e2e/KNOWN-ISSUES.md`](../../../e2e/KNOWN-ISSUES.md).

## Cleanup

The session finalizer deleted every tracked sandbox. `python scripts/e2e-cleanup.py --all-tagged` after both runs reported no sandbox carrying an `e2e` tag; no `e2e-` template remained. Nothing leaked.

## Problems found

- Eight SDK defects (KI-001 to KI-007, KI-010), two platform quirks (KI-008, KI-009) and one environment limit (KI-011); see `e2e/KNOWN-ISSUES.md`. None is fixed by this change, since the change does not edit SDK sources.

## Not verified

- The custom-template flow end to end (`DockerBuilder` to ACR push to `CreateTemplate` to sandbox): blocked by KI-011.
- AI code-generation features (`OPENAI_API_KEY`): not exercised by this suite.
