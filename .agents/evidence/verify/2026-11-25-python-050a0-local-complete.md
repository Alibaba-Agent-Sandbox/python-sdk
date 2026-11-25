# Verification: Complete local Python 0.5 regression invocation

- Date: 2026-11-25
- Change: [PR #174](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/174),
  [Issue #173](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/173), and
  [decision](../../notes/implemented/process/2026-11-25-python-050a0-preview.md).
- Result: PASS with 29 explicit optional client skips for the full local test
  invocation. Publication, latest-head remote CI/review and CLI consumer
  acceptance remain distinct gates.
- Tested source: matching 0.5.0a0 runtime/test source committed as
  `8cd2705f21959ae676e850066b28490d5202cf5d`; the subsequent
  `cde406277a336c40c447939e732881c5a1d15cf3` changes only the changelog and
  engineering records. Runtime/test source was unchanged throughout the run.
- Environment: Linux, Python 3.13.13, declared existing development/build tools.
  Private user/PID/network namespace, private `/proc`, enabled loopback and a
  child-reaping Python PID 1. No cloud resource or credentials used.
- Delivery status: intentionally left uncommitted during PR #174 validation so
  a result-only update does not replace the head undergoing normal remote CI.
  The final delivery-record PR will preserve this checkpoint.

## What was verified

One complete original `make test` invocation ran both owning package suites and
returned exit status 0. All server cases and all runnable client cases passed,
including packaging, both previously process-sensitive managed cases, application
discovery and zero-byte/8 MiB upload round-trips. No test assertion, timeout,
marker or product implementation was weakened.

## Commands run

With the project interpreter and dev tools selected, the normalized invocation
was:

```bash
unshare -Urnpf --mount-proc bash -c 'ip link set lo up && exec python reap-init.py env PYTHONPATH="$PWD/client-sdk/src:$PWD/server-sdk/src" make test'
```

`reap-init.py` is the task's test-environment child reaper, not a new repository
script. Source-path selection bound imports to this release worktree without
rebinding another task's editable installation. The separate fresh-wheel checks
in the preparation record establish installed package metadata and imports.

After the test command completed, a separate SHA-256 comparison confirmed all
four local wheel/sdist files still match the committed
[candidate manifest](2026-11-25-python-050a0-artifacts.json).

## Results

| Check | Result | Original summary |
| --- | --- | --- |
| Full server suite | PASS | 895 passed in 316.92 s; no failure or skip |
| Full client suite | PASS with optional skips | 2,471 passed, 29 skipped in 162.49 s; no failure |
| Complete `make test` process | PASS | Exit status 0 after both suites |
| Candidate artifacts unchanged | PASS | All four current SHA-256 values equal the committed manifest |
| Independent release review | PASS | Root and a separate component reviewer checked actual metadata/README bytes, matching extras, bilingual migration and publisher ordering without finding a blocker; not a substitute for CI/publication |

The 29 existing client skips are:

- Nine optional PostgreSQL scenarios without the optional `pgserver` dependency.
- Two opt-in real-engine scenarios without `ABX_COMMAND_TEST_BIN`.
- Five sibling CLI fixture-copy checks requiring the expected sibling checkout.
- Thirteen Container/Cube/E2B catalog-engine scenarios requiring the expected
  sibling CLI checkout and its Node dependencies.

These optional matrices were not expanded or counted as passes for the version
metadata change. Unlike the earlier upload checkpoint, this complete invocation
had the build backend installed and ran the packaging modules rather than
collection-skipping them.

## Cleanup

Existing fixtures shut down local servers/processes and temporary directories;
the namespace PID 1 reaped owned child processes. No new cloud sandbox, database,
image or model workload was created. Source control was clean after the tests,
before adding this uncommitted evidence file.

## Problems found

No failure in this original full test command. The preparation record retains
its earlier artifact/verifier issues, and the upload records retain their earlier
failed full invocation and cloud probes. None is rewritten as a pass.

## Not verified

This local result does not publish packages or establish a remote CI result.
The root task must verify the latest actual PR head's required matrix and review,
then use the normal tag publisher and validate the four public artifacts and
fresh exact-version installation. Issue #173 remains open through actual public
pair consumption by
[CLI Issue #270](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/270)
and [PR #271](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/271).
