# Verification: managed FC source Gateway and independent business artifacts

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; source runtime `cd43e9e40ef5c90212b8ea6a1cc293c10f71ad2e`.
- Result: PARTIAL overall — normal source deployment, all 39 positive operations, all 38 protected-route authentication rejections, two-turn business checks and live idle-Session SSE pass. Active-cancellation, completed revision upgrade and public-package recipe remain separate gates.
- Environment: Alibaba Cloud FC Gateway/Worker/Dispatcher, private RDS PostgreSQL 17 with explicit CA and `verify-full`, real Express Sandboxes and Qwen Code/model tools. Existing credentials remain private.
- Packages: unpublished matching client/server 0.4.0a7 from exact CI run 42169013251; client wheel SHA-256 `1ac32d508980297ec80629b6c9e2fb5fd0b268db354d13d39120dfbaada8d4e0`, server wheel SHA-256 `210db5e796f4fc63e84156d19076c946d261b48c47ec6c8c1db82b8b60691f08`.

## Executed behavior

The normal deployment reaches ready in 351 seconds. Unlike the earlier interrupted source
experiments, its normal Dispatcher timer is enabled by the deployment state machine; this
acceptance run does not use the temporary manual-dispatch controller or rewrite a receipt to ready.

The independently frozen HTTP inventory observes 39 positive operations and HTTP 401 for all
38 protected operations. Health is intentionally public. The report's inventory/authentication,
complete HTTP trace, independent-source checks and public cleanup gates all pass. The full
business run takes 412 seconds. The business HTTP client uses the single Gateway endpoint;
engineering source inspection uses separate private provider credentials.

The real model first fixes the seeded CSV aggregation program and generates its source, summary
CSV and report. The second turn uses the same Session/workspace to add share calculations.
The controller downloads the actual bytes before independent checking. A pinned helper runs only
inside the exactly matched owned Sandbox: original test bytes remain unchanged, original tests
pass, four first-turn and eight second-turn held-out cases pass, and the tested program hash equals
the downloaded source artifact. The helper's exit and process completion are confirmed before the
next turn. No generated program executes on the host; this is cooperative same-UID evidence,
not adversarial guest attestation or a direct PostgreSQL ownership query.

The independent live SSE check creates an idle logical Session without starting a model turn.
Its first frame arrives in 0.169 seconds, normal EOF in 20.369 seconds, and a concurrent Session
read completes during the stream. This proves FC transport flush and concurrency for that finite
stream; it is not described as real-time model-token streaming.

## Evidence chain and cleanup

The controller retains exact private receipts, native identity proof, HTTP identity ledger,
artifact bytes/manifests, helper results and raw command captures in restricted local storage
with authenticated encrypted recovery. Repository evidence contains no credentials, endpoints,
cloud IDs or raw model responses. The safe capture/report labels are:

| Label | Actual result | Scope |
| --- | --- | --- |
| `source-final-public-39` | PASS | 39 positive operations, 38 authentication failures, two real model/tool turns, both independent source checks and public resource cleanup. |
| `source-final-live-sse` | PASS | First frame/normal finite EOF/concurrent read and public cleanup, without a model turn. |
| `source-final-active-cancel` | FAIL | `FileOperationError` before busy/queue/cancel checks. Subsequent private diagnostics locate HTTP 500 while downloading `/proc/PID/stat` after stat succeeded; that observer failure is not treated as process absence or a cancellation result. Both public and direct native cleanup are confirmed; no active-stop or reuse pass is claimed. Original scripts/reports remain. |
| `source-final-upgrade-prepare` | PASS | An actual old Qwen Session and workspace marker are prepared and intentionally retained for the controlled update. This is not completed upgrade acceptance. |

The public-39 and live-SSE reports explicitly leave independent provider-wide absence false.
That final check belongs to the owning controller after all ongoing upgrade work and application
destruction. An intentionally retained upgrade Session is not reported absent. The earlier
window's signed drain and exact cleanup are recorded separately in the private-invocation/drain
evidence; they do not certify cleanup of this live window.

## Preserved failures and next candidate

Earlier source runs stop at final production-credential verification, and their partial manual
business runs stop at template name/ID comparison. The new engineering proof resolves the native
display name only after same-account/team exhaustive uniqueness and repeated created-ID/image
readback; it does not relax metadata, Session, revision or native identity gates. Those old failures
remain historical evidence.

The first attempted Qwen-to-Codex update subsequently fails its candidate-health planned-revision
gate in 37.566 seconds. Its cause remains under investigation; normal source Qwen ready/39 results
are retained, and no update replay or successful upgrade is inferred.

The later runtime input-boundary commit `8df1ed77c1262719d2c0a12cc846a855fde638e8` is a different
candidate. Its SQLite/PostgreSQL empty-revision regressions and new CI artifacts are recorded
separately. This source run does not claim it used that new wheel. Public publication, public
installation/readback and the final recipe must execute before whole-template delivery is declared;
the architecture decision remains proposed.
