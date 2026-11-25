# Verification: MCP regression PID publication and setup cleanup

- Date: 2026-11-25
- Change: [Issue #176](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/176)
  and [decision](../../notes/implemented/process/2026-11-25-mcp-task-pid-publication.md).
- Result: PARTIAL. Bounded synchronization/failure-cleanup probes, the complete
  targeted module and owner static checks pass. Full local tests and latest-head
  normal CI/review, including Python 3.11, remain pending at this checkpoint.
- Base: actual main `92233621515cae8f294cd5b6e63508ed31dcb321`.
- Environment: Linux, Python 3.13.13, existing dev tools. Process tests use an
  isolated user/PID/network namespace, private `/proc` and a child-reaping PID 1.
  No cloud resource, credential or package publication.

## Original failure

[Main CI run 45557866579](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45557866579)
failed its
[Python 3.11 client job 139014198371](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45557866579/job/139014198371)
on the first attempt. Installation, lint, formatting and type checks passed;
`Run tests` failed at:

```text
test_owned_descendants_cleaned_after_leader_exit[nonzero]
tests/test_agent/test_mcp_tasks.py:182
pid = int(marker.read_text())
ValueError: invalid literal for int() with base 10: ''
1 failed, 2453 passed, 36 skipped, 10 deselected in 158.44s
```

The dependent build was skipped. This failure occurred before the test's
production terminal-state, descendant-absence and repeated-cancel assertions.
It does not prove those product behaviors failed.

The passing PR175 head `a50b259cbdfb3d5a08bf8bb06314b424800fc6d7` and actual main
merge `92233621515cae8f294cd5b6e63508ed31dcb321` have the identical complete Git
tree `a9384977c598fad765aadfeca9f383ee0c3eb39f`; an independent `git diff` is
empty. Historical passing PR/public-release evidence is retained, and this new
post-merge failure is not hidden or rewritten as a pass.

## Bounded diagnosis

The old child writes using `open(marker, 'w').write(pid)`, while the consumer
waits only for existence. A two-process standard-library handshake held the
writer after file creation and before writing, making the window observable:

| Producer protocol | Before releasing writer | Original integer conversion | After completion |
| --- | --- | --- | --- |
| Original created marker | Exists, empty string | ValueError | Complete PID |
| Closed temporary file followed by replace | Final marker absent | Not attempted before publication | Complete PID |

The handshake and its child processes have five-second bounds and finally-based
cleanup. This demonstrates a fixture publication gap; it does not establish the
exact scheduling/IO cause of that CI occurrence, whose writer state was not
captured. No cross-test marker overwrite was identified: each mode has its own
temporary directory, and the production task supervisor writes a separate task
record subdirectory.

## Change and targeted verification

The test child writes and closes a same-directory temporary marker before
`os.replace`. The original five-second wait, all four modes, terminal-state,
descendant-absence and repeated-cancel assertions remain. Waiting/parsing now
run inside `finally` coverage. A failing setup/assertion first cancels the known
owned handle; the original direct kill is limited to a verified PID greater
than one. No empty-read suppression, longer timeout or retry-until-green was
introduced.

A separate controlled failure probe injected a marker-read `ValueError` into the
actual updated test function, retaining the real local task transport. The
original error propagated, the known handle was cancelled exactly once, and the
owned descendant was stopped. This verifies failure cleanup even when PID parsing
does not complete; it does not modify a product assertion.

## Commands run

With the existing project environment and this worktree's source paths selected:

```bash
python -m pytest tests/test_agent/test_mcp_tasks.py -q
make lint typecheck format-check
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

The first command runs from `client-sdk` inside the isolated process/network
environment. The synchronization and injected-setup probes use standard-library
temporary directories/subprocesses and the existing fixture, respectively; they
do not call cloud transports. Production source and version files are compared
against the base separately.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Original main Python 3.11 job | FAIL | Empty test PID marker; original summary above retained |
| Passing PR head versus main merge tree | PASS | Exact same tree; no merge-only source delta |
| Bounded producer/consumer probe | PASS | Old incomplete-file window observed; atomic final marker absent until complete |
| Injected setup-failure cleanup | PASS | Original ValueError preserved, one owned-handle cancellation, descendant stopped |
| Complete MCP task module | PASS | 30 passed in 5.73 s on Python 3.13.13; includes all four original modes |
| Lint, type and format checks | PASS | Both packages; existing mypy unused-section note retained |
| Owner health, hygiene and whitespace | PASS | Existing release-runbook warning retained |
| Full local regression invocation | Pending | Result will be reported separately without rewriting this checkpoint |
| New-head remote CI/review | Pending | Python 3.11 matrix is required; no blind rerun of the failed main job |

## Cleanup and limits

Probe temporary directories and children were removed/reaped. The targeted
fixture cleaned up its owned tasks. No production source, SDK version, public
artifact or tag is changed. This is a test-reliability follow-up, not a new public
release, cloud validation or a claim that CI's exact empty-read cause is proven.
User guides remain unchanged because no user behavior changes; the test
CHANGELOG entry is bilingual. Earlier release and failure evidence is preserved.
