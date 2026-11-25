# Verification: Bounded file uploads

- Date: 2026-11-25
- Change: [Issue #171](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/171)
  and [decision](../../notes/implemented/feature/2026-11-25-bounded-file-uploads.md).
- Result: BLOCKED — the required candidate cloud upload path has not passed;
  remote CI/review are also outstanding.
- Baseline: main `a9a572d81847fe99216bf1bb454b91810dacc676`.
- Packages: client/server 0.4.0a7 source candidates; neither was released.
- Environment: Linux, Python 3.13.13; editable server/client installs from this
  checkout with declared dev extras and build tools. Loopback tests use an isolated
  user/network namespace with loopback enabled. No credentials are recorded.

## What was verified

The initial added HTTP tests reproduce three independent defects on the original
source: empty files fail, 8 MiB files exceed the shared JSON cap, and obviously
oversized base64 reaches the decoder. The candidate fixes these without changing
the protocol or the default body cap for unrelated endpoints. A further regression
checks that the upload body budget uses the effective policy size rather than a
smaller environment value.

## Commands run

With the project virtual environment activated:

```bash
python -m pip install -e './server-sdk[dev]' -e './client-sdk[dev]' build twine
python -m pip install hatchling
unshare -Urn sh -c 'ip link set lo up && pytest server-sdk/tests/test_server/test_upload_limits.py -q'
unshare -Urn sh -c 'ip link set lo up && make test'
make lint typecheck format-check
make build dist-check
bash scripts/check-repo-health.sh
make hygiene
git diff --check
# Separately from each package directory, after installing hatchling:
python -m pytest tests/test_packaging.py -q
```

Only the two failing managed-process cases were then rerun using an isolated
user/PID/network namespace, private `/proc`, and a child-reaping Python PID 1:

```bash
python -m pytest tests/test_managed_agents.py::test_real_bridge_two_turns_files_artifacts_close_and_delete tests/test_managed_agents.py::test_real_detached_child_survives_leader_but_process_domain_stops_it -q
```

The tests' assertions, timeouts and ProcessDomain implementation were unchanged.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Initial HTTP regressions against original code | FAIL | 3 failed, 11 passed; the three expected defects were observed |
| Same initial regressions against candidate | PASS | 14 passed; real local HTTP and filesystem, not cloud |
| Strengthened upload regression set | PASS | 15 passed after adding policy max_bytes=8 MiB with the environment limit at 4 bytes; the body budget also uses the effective policy limit |
| Both packages: lint | PASS | make lint |
| Both packages: type checks | PASS | 58 server and 114 client source files |
| Both packages: formatting | PASS | 95 server and 260 client files |
| Full server suite | PASS with skip | 889 passed, 1 skipped in 333.79 s; this run included the initial 14 new upload regressions |
| Full client suite | FAIL | 2 failed, 2462 passed, 30 skipped in 179.56 s; both new discovery/upload round-trips passed |
| Managed-process failures under PID isolation | PASS | The two original failing cases passed in 1.24 s with isolated process observation and a reaping PID 1 |
| Packaging module follow-up | PASS | After installing hatchling: server 5 passed, client 7 passed |
| Build/distribution checks | PASS | Both wheels and sdists, twine, py.typed, fresh combined/client-only installs and pip check |
| Repository health | PASS with warning | 106 passes, 1 existing release-runbook warning, 0 failures |
| Hygiene and scoped whitespace | PASS | No local paths, credential-like strings or whitespace errors |
| Candidate cloud runtime | FAIL | Candidate package origin was confirmed; external application discovery returned 404, and the final guest HTTP smoke still returned 404 after a readiness check |
| Cloud acceptance | BLOCKED | No passing complete candidate upload/download path in cloud is claimed |
| Remote CI/review/merge | Pending | No successful gate or merge is claimed in this record |

## Cleanup

Local HTTP fixtures shut down their servers and use pytest temporary files. No
cloud resource was created by the local test runs. The root task coordinated five
cloud probe instances and independently confirmed each owned instance absent with
HTTP 404 after finally-based cleanup. No account-wide resource audit is claimed.

## Problems found

The endpoint and docs described chunked/streaming transfer although HTTP receives
complete base64 JSON. The patch documents this limit rather than claiming it
creates HTTP streaming, fixes all memory amplification or proves an OOM threshold.

The original full client run shared the host PID namespace and failed two
conservative managed-process tests. Both passed with isolated process observation.
This is consistent with the known shared-host boundary; this run does not
independently identify a particular concurrent Git process as the cause. The
original failures remain part of this record.

The initial environment lacked hatchling in the test interpreter (editable builds
used an isolated backend), so packaging modules were collection skips. After
installing hatchling, an attempted combined invocation of two same-named package
test trees failed pytest plugin registration. Running each packaging module from
its owning package directory passed. These environment/invocation results do not
turn the original full sweep into a pass.

Early cloud smoke scripts used close() instead of aclose() in teardown, and one
guest probe did not wait for readiness. The final probe corrected those driver
issues but still observed HTTP 404. Candidate import or sandbox creation is not
successful upload verification. The failures are not classified as a platform
outage or an independently proved server-handler defect. Further cloud resource
creation was stopped.

Other client skips were nine optional PostgreSQL cases without pgserver, two
optional real-engine tests without ABX_COMMAND_TEST_BIN, five sibling CLI
fixture-copy checks, and thirteen catalog engine cases requiring a checkout named
cli with Node dependencies. These unrelated optional matrices were not expanded
for the upload fix.

## Not verified

No throughput, peak-memory, streaming, arbitrary Provider or production-model
workload acceptance is claimed. The original full client command did not pass;
its two failures have separate passing isolated reruns. Candidate cloud
upload/download and remote CI/review/merge remain outstanding, so the change
remains proposed and must not be reported complete.
