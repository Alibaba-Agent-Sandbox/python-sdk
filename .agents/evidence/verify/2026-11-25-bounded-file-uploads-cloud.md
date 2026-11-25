# Verification: Candidate file uploads in a real Express sandbox

- Date: 2026-11-25
- Change: [PR #172](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/172),
  [Issue #171](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/171), and
  [decision](../../notes/implemented/feature/2026-11-25-bounded-file-uploads.md).
- Result: PASS for the scoped candidate cloud path and owned-resource cleanup.
- Tested source: `4e4201869015daebc00f2227957f60c28c2595ff`; server implementation
  is unchanged from `37bdbbd04b3cf575957ece1699613214cba8f9d9`.
- Packages: client/server 0.4.0a7 source candidates, not a new public release.
  The candidate server wheel was extracted in the guest and selected through
  `PYTHONPATH` ahead of the base image's installed runtime.
- Environment: one owned Alibaba Cloud Express `base` sandbox with the configured
  region `cn-hangzhou`; local Python
  3.13.13. Credentials were loaded only into the execution subprocess and are not
  recorded. The root task executed the cloud driver; a second agent independently
  reviewed its script, result and candidate/source identity.
- [Sanitized result](2026-11-25-bounded-file-uploads-cloud.json).

## What was verified

The candidate runtime was started using the SDK's process acknowledgement and
continuously drained startup stream. An HTTP application command returned a nonce,
PID, port and hash of the running `app.py`; the guest verifier checked the nonce,
and the external application client returned the identical identity. A separate
process checked that the launcher PID was alive and owned the listening socket.
Only after that identity chain were the transfers accepted as candidate results.

Both direct guest HTTP and the external Client SDK round-tripped zero-byte and
8 MiB files. The SDK called discovery first, checked the upload byte count and
compared downloaded bytes. Independent native `sha256sum` checks matched all four
guest files. The upload protocol remained complete base64 JSON, without an
explicit increased request-body policy override.

An additional independent archive/source comparison found all 58 server Python
files in the tested wheel identical to this PR's source. The runtime's `app.py`
hash matches that wheel. This complements the live identity assertions; a separate
import alone was not treated as proof of the listener's implementation.

## Commands run

Within the task tooling directory, using the project virtual environment:

```bash
python local-ack-rehearsal.py
python auth-run.py python cloud-uploads-ack.py
```

The local rehearsal ran the same launcher, guest verifier, listener diagnostics
and SDK transfer helper without creating cloud resources. The cloud driver used
`ProviderSandbox.start_server(..., wait=False)` for acknowledged startup,
`application_client` through the real sandbox application endpoint, native
`commands.run` for independent file hashes, and `kill` followed by a separate
management HTTP query for cleanup confirmation. Its inputs and report were
reviewed without another cloud run.

After adding this owner evidence, repository checks were run:

```bash
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

## Results

| Scenario / check | Result | Scope |
| --- | --- | --- |
| Local acknowledged-start rehearsal | PASS | Same candidate launcher, direct guest HTTP, identity/listener checks and SDK byte comparisons |
| Candidate process acknowledged | PASS | Existing SDK startup transport and stream drain, no detached `nohup` assumption |
| Candidate identity and listener | PASS | Nonce, runtime source hash, PID command line and socket ownership agree |
| Guest direct HTTP, 0 bytes | PASS | Empty base64 upload and exact empty download |
| Guest direct HTTP, 8 MiB | PASS | 8,388,608 original bytes returned |
| External SDK, 0 bytes and 8 MiB | PASS | Real application endpoint, discovery, upload sizes and exact downloads |
| Independent native file hashes | PASS | All four files match the originating content |
| Candidate startup log | PASS | Empty log observed after startup and transfers |
| Cleanup | PASS | Finally-based deletion; separate management GET returned HTTP 404 and local owned receipt was removed |
| Wheel versus PR server source | PASS | All 58 Python files match |
| Public repository package description | PASS | Independently read back `async client (agent-sandbox-client)`; distribution names themselves are unchanged |
| Owner repository checks | PASS | Health: 106 passes, one existing release-runbook warning, no failures; hygiene and whitespace checks pass |

Content SHA-256 values are
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
for the empty file and
`7d212b9c884f5c77896de960ae17cc341cda43b14d6a971f34ca29ebd4badf7f`
for the 8 MiB fixture. Candidate identity:

| Artifact | SHA-256 |
| --- | --- |
| Server wheel | `ab04f67a7a8d9172d3ea1bca51d2e887d65aaccc37167415926916e7e5857c74` |
| Runtime `app.py` | `345bc711aef8a9ba8b19854ac9aed4e6b74ccd0c8f9023c07f4b64d89fe0e800` |
| Upload handler source | `50f131050fed258b3dd103966d41544c7a6138a73547c4c2c294f9523ac6c93e` |
| Sanitized result JSON | `d97b9ee8ff5a8140d6175531f6ed9fcd9be8fdc54da4534f29e36a706f96c0b1` |

## Cleanup

This follow-up used exactly one owned cloud sandbox. Its driver deleted it in
`finally` and independently confirmed HTTP 404 from the management endpoint.
Local rehearsal processes, readers and temporary files were closed. The five
earlier probe instances remain separately accounted for in the original record;
no account-wide resource audit is claimed.

## Problems found

Earlier probes used a detached process and did not bind the responding listener
to the candidate. The new driver supplies acknowledgement, identity and listener
ownership. The guest has proxy environment variable names, which are the only
proxy details retained in the sanitized result. Direct `http.client` ignores those
settings. This observation does not prove that proxies caused the earlier 404s.
Those failures and their unknown cause remain in the original evidence.

## Not verified

This targeted real-cloud verification completes the upload-specific acceptance
path. It is not a repository-wide `make e2e` run, all-Provider certification,
throughput/peak-memory measurement, true HTTP streaming, production-model test or
package publication. The original full client invocation's two failures and their
separate passing isolated reruns remain unchanged. Latest-head remote CI and
review/merge are separate gates and must be checked after this record commit.

Historical records remain unchanged:
[original upload checks and cloud failures](2026-11-25-bounded-file-uploads.md)
and [download-limit correction](2026-11-25-download-limit-review.md).
