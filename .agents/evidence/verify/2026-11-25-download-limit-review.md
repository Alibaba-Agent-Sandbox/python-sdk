# Verification: Download-limit documentation review

- Date: 2026-11-25
- Change: [PR #172](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/172),
  [Issue #171](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/171), and
  [decision](../../notes/implemented/feature/2026-11-25-bounded-file-uploads.md).
- Result: PASS for this documentation correction and local HTTP boundary probe;
  candidate cloud upload acceptance remains pending in the original evidence.
- Tested implementation: `37bdbbd04b3cf575957ece1699613214cba8f9d9`, with only
  documentation and engineering-record edits added during this review.
- Environment: Linux, Python 3.13.13, existing editable candidate installation;
  isolated user/network namespace with loopback enabled. No cloud resources or
  credentials were used.

## What was verified

An independent review of `_read_checked` found that downloads apply only the
effective policy `limits.max_bytes`. Without that rule, they do not apply a
file-size limit and do not inherit `ABX_MAX_UPLOAD_SIZE`. Both guide languages now
state this instead of referring to the upload limit as the same download limit.
No runtime, default policy, public protocol or package version changed.

## Commands run

With the existing project virtual environment activated:

```bash
unshare -Urn sh -c 'ip link set lo up && python download-limit-probe.py'
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

The temporary probe imports the existing `server-sdk/tests/test_server/_live.py`
real HTTP fixture. In a temporary base directory it creates a five-byte file,
sets the upload environment limit to four bytes, and checks the following three
requests. Each server is closed in `finally`; temporary files are removed by the
temporary-directory context.

## Results

| Scenario / check | Result | Observed behavior |
| --- | --- | --- |
| Download without a policy size limit | PASS | HTTP 200, five original bytes returned despite the four-byte upload environment limit |
| Upload with the four-byte environment limit | PASS | HTTP 413, `limit: 4` |
| Download with its own `max_bytes: 4` policy | PASS | HTTP 413, `limit: 4` |
| Bilingual guide correction | PASS | Effective download policy and upload-only environment limit match the implementation |
| Existing handbook explanation | PASS | Clarifies complete base64 JSON and independent download policy; its 22 fenced blocks and two historical endpoint summaries remain byte-identical |
| Repository health, hygiene and whitespace | PASS | Final checks pass; the existing missing release-runbook warning remains |

An initial health invocation preceded creation of this new evidence file and
reported its two pending relative links and slug as missing. Creating this file
resolved those draft-record failures; final checks were rerun.

## Cleanup

Both temporary local servers shut down and their files were removed. This review
created no cloud resources.

## Problems found

The old bilingual download sentence incorrectly implied it inherited the upload
byte limit. The published-baseline handbook retained misleading historical
`Chunked` summaries; its explanation now states the actual buffered protocol
without rewriting those captured summaries or examples. The handbook remains a
separate workspace deliverable and is not copied into this repository.

## Not verified

This documentation review does not establish cloud upload/download acceptance,
throughput, peak memory, true HTTP file streaming or publication. The original
[upload evidence](2026-11-25-bounded-file-uploads.md) retains its failures and
blocked cloud result. Required CI, cloud acceptance and merge are coordinated
separately for PR #172.
