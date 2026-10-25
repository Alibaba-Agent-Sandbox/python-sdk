# Verification: CLI acceptance discrepancy and focused file diagnostic

- Date: 2026-10-25
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/108
- Diagnostic follow-up: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/109
- Candidate: paired Python packages 0.4.0a1 and built CLI 0.5.0.
- Implementation head: `66c86f2b6dc7cd33e02c2a53d98dda2125d05236`.
- Publication/merge: neither was performed by this verification.

This follows the [earlier cloud checkpoint](2026-10-25-unified-template-cloud.md).
The five unified-template startup cases passed, including two services started
from one template. They are independent of the CLI file-transfer discrepancy below.

## Final implementation CI

All 11 remote checks passed for implementation head `66c86f2`: client and server
on Python 3.10/3.11/3.12, Python-to-Node Provider engine, package build, hygiene,
pinned standard contract and Markdown links. An evidence-only follow-up commit
must still receive its own applicable checks.

## Keep the two full CLI runs separate

| Run | Result | Duration | Detail |
| --- | --- | --- | --- |
| Configured CLI follow-up | PASS | 376.63 s | Lifecycle, list, exec/stream, upload/download and repeated deletion passed. |
| Additional explicit Express environment mapping | FAIL | 355.17 s | Lifecycle/list/exec/stream passed; upload exit 2, download exit 4 and absent downloaded content; both deletion calls exited 0. |

The second run mapped the E2B API key, API URL and domain environment names to
existing ABX_SANDBOX Express settings. Credential values are not recorded. Its
second deletion reported the owned sandbox absent.

Read-only review of `e2e/provider_live.py::cli_express` confirms that creation sets
`--timeout 300` and each subprocess allows up to 240 seconds. The fixture discards
file-command stderr and does not record individual operation durations or HTTP
status. Both whole-run durations exceed 300 seconds, but the passing run was longer.
This cannot establish that the failed transfer hit the sandbox deadline. Exit 2
and exit 4 cover multiple error categories and cannot identify a cause alone.

The failure's root cause remains **unconfirmed**. It is not attributed to template
startup, Provider support, file API logic or network interception. Issue 109 owns
the missing diagnostic evidence; no unrelated runtime or fixture change was added
to the template refactor.

## Focused real-provider file check

A separate diagnostic used the same explicit Express environment mapping and
built CLI, a fresh engine socket and a newly owned sandbox. It retained monotonic
operation timings and sanitized stderr in memory. It ran only this command sequence:

```sh
abx --provider alicloud-express sandbox create base --detach --timeout 300
abx --provider alicloud-express sandbox upload "$SANDBOX_ID" "$SOURCE_FILE" /tmp/unified-template-file-diagnostic.txt
abx --provider alicloud-express sandbox download "$SANDBOX_ID" /tmp/unified-template-file-diagnostic.txt "$DEST_FILE"
abx --provider alicloud-express sandbox kill "$SANDBOX_ID"
abx --provider alicloud-express sandbox kill "$SANDBOX_ID"
```

The runner saved the detached ID from creation, used a temporary local directory,
wrote `unified-template-file-diagnostic` followed by a newline, compared downloaded
bytes exactly, and always ran deletion in `finally`. No credentials or raw private
responses are included in this record. No retries or product changes were used.

| Operation | Elapsed | Since start | Exit | Observation |
| --- | --- | --- | --- | --- |
| Create | 42.601 s | 42.601 s | 0 | One detached sandbox ID; stderr empty. |
| Upload | 29.551 s | 72.153 s | 0 | stderr empty. |
| Download | 30.885 s | 103.038 s | 0 | stderr empty; downloaded bytes equal source bytes. |
| Delete | 38.036 s | 141.074 s | 0 | stderr empty. |
| Delete again | 39.871 s | 180.945 s | 0 | Reports the owned sandbox was not found. |

**Focused result: PASS**, total 180.946 seconds. File operations completed before
300 seconds even when measuring from before creation; both cleanup commands passed
and the owned sandbox was confirmed absent. The CLI exposed no failing HTTP status
in this successful run, so none is invented here.

This establishes that the candidate's real file upload/download and cleanup worked
in this experiment. It does not explain or erase the failed full-gate run, prove
repeatability under all conditions, or close Issue 109. No further cloud reruns or
unsupported claims about deadline behavior were made.
