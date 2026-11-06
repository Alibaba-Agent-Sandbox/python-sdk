# Verification: managed FC private invocation and normal drain

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; runtime `cd43e9e40ef5c90212b8ea6a1cc293c10f71ad2e`.
- Result: PARTIAL — real FC private invocation, PostgreSQL drain and this failed deployment's cleanup pass. Complete business/model, upgrade and public-package acceptance remain separate.
- Environment: Alibaba Cloud FC custom containers, RDS PostgreSQL with an explicit public CA and `sslmode=verify-full`; existing authorized credentials, never copied into this record.
- Package under test: matching unpublished client/server 0.4.0a7, installed in the image from exact GitHub CI wheels.

## What was verified

A real InvokeFunction call to the existing Dispatcher first reached the private HTTP handler but
returned the bounded `unsupported_media_type` error. FC transported that response with native
status 200. The [private media continuation](2026-11-06-managed-agents-private-invocation.md)
records the official conversion contract, scoped correction and real local HTTP regressions.
The earlier build and private response are preserved separately; a native transport 200 was
never counted as application success.

The controller then used the new exact CI package image to repair only this already-owned
Dispatcher for cleanup. It retained the original application ID, PostgreSQL state, complete
environment, role, VPC, startup arguments and native creation identity. It did not replay apply,
publish a control trigger, activate admission or replace the database. Normal CLI destruction
subsequently invoked the signed private Dispatcher drain and completed resource cleanup.

## Exact package identity

The previous frozen runtime `218ad48141ff44913cd4a4a5cffd59209a4f96a0` used client wheel SHA-256
`e8759959597510803a372dcebf0b88a67a948f63d5d950a22891b7cfc074afe5` and does not contain the
private media correction. Its original failure and package files remain historical evidence.

The replacement uses [CI run 42169013251](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/42169013251)
and Docs run 42169013242, both successful, at runtime `cd43e9e40ef5c90212b8ea6a1cc293c10f71ad2e`.
Artifact 13480710650 has ZIP SHA-256
`d32c203c8b63b8b4488e27ca5c3362388cd625e0f6a02adb68b729bb9bde52b1`.

| Distribution | Bytes | SHA-256 |
| --- | ---: | --- |
| Client wheel | 692232 | `1ac32d508980297ec80629b6c9e2fb5fd0b268db354d13d39120dfbaada8d4e0` |
| Server wheel | 226017 | `210db5e796f4fc63e84156d19076c946d261b48c47ec6c8c1db82b8b60691f08` |
| Client sdist | 705564 | `289dc0e3c9f7648830556737cecd4095f152e77efaf40adba594b0ad0e5cdaec` |
| Server sdist | 272580 | `f2e1f4fb6e8e17d272ad35e52e02df26a640c7adcb6e909515b501de517ac063` |

An independent local read of the owned build's actual source wheel files matches both wheel
hashes above. A fresh installation of these exact CI wheels passes dependency checks and actual
HTTP Dispatcher/Worker octet-stream and public Gateway JSON-boundary checks; its installed HTTP
module bytes match the tested source. Local shared-filesystem build archives are not substituted.

## Commands and capture chain

The controller's private recorder retains original stdout/stderr, exact receipts and full native
readbacks under encrypted recovery storage. The following labels identify that chain without
copying credentials, endpoints, cloud IDs or raw cloud logs into the repository.

| Recorder label | Actual result | Meaning |
| --- | --- | --- |
| `third-cleanup-status-after-repair` | Native status 200; `unsupported_media_type`, `invalid_request_error` | Original media failure after the separately reviewed CLI storage-descriptor correction. No successful status/DB round trip is inferred from the error envelope. |
| `third-cleanup-dispatcher-image` and `third-cleanup-dispatcher-image-diagnostic` | Exit 1 | Early local recovery failures retained. No apply replay is performed. |
| `third-cleanup-dispatcher-image-after-dead-lock` | Exit 1, 37.796 s | Admission and protected build use were persisted, but the original complete three-line journal has no native-update intent. Its exact failure cause remains unproven. |
| `third-cleanup-stage-compare` | Exit 0, 5.397 s | One independent native read: original creation identity, all baseline fields, environment and container match; state Active and update Successful. No native mutation. |
| `third-cleanup-exited-proof` | Exit 0 | Recorder waited for the original mutator to exit; frozen source and complete journal establish that no UpdateFunction had been called. No PID was guessed. |
| `third-cleanup-complete-admission` | Exit 0, 60.305 s | A new fixed, one-shot completion admission precedes the sole image update; native identity/full environment and exact new image digest are confirmed by readback. |
| `third-cleanup-destroy-plan` | Exit 0 | Normal read-only destruction planning. |
| `third-cleanup-app-destroy` | Exit 0, 15.025 s | Normal `abx app destroy` completes with status/phase `destroyed` and `drainConfirmed: true`. |
| `third-cleanup-native-absence` | Exit 0, 1.217 s | Independent native reads report Worker, Dispatcher and Gateway all absent. |
| `third-cleanup-guest-images-apply` | Exit 0 | Three exact owned guest-image targets have independent absence; original records are unchanged. |

The standard CLI command shapes are `abx app plan --destroy RECEIPT --out DESTROY_PLAN` followed by
`abx app destroy DESTROY_PLAN --bindings PRIVATE_BINDINGS --yes`. Actual private arguments remain
with their controller; no secret-bearing binding file is reproduced here.

The recorded destruction receipt independently shows three confirmed function cleanup entries,
one confirmed prepared-template entry and one confirmed original Server-image entry. The CLI
sets `drainConfirmed` only after the native signed control result explicitly reports draining and
zero active Sessions, pending cleanup and uncertain resources. Thus this is a real PostgreSQL
control/drain round trip, not a transport-200 or local fake result.

## Recovery and cleanup boundary

All recovery changes passed independent review before execution. The new image is protected by
the normal build-use guard before its function update. Unknown results never authorize replay;
the narrowly reviewed completion uses a separate admission only after original process exit,
complete no-update-intent evidence and a fresh full native baseline. Any existing update intent
would permit observation only. The original plan, receipts and failed journals remain historical.

Private-backup time bounds were increased while retaining locks, byte budgets, authenticated
encryption, fsync and atomic replacement. The original 37.796-second failure was not reclassified
as a proven backup timeout. Frozen dependency caches were not deleted to bypass identity checks.

The failed deployment's three FC roles, prepared template and original Server image are confirmed
cleaned. At that receipt's completion, its externally managed database and drained application
ledger are retained, as designed. The replacement Server image is separately owned and protected
for the controller's next deployment; this receipt does not claim to delete that different resource.
The owning controller later destroys the remaining original-window deployments and independently
releases that test database before admitting a new test window. Those are later lifecycle results,
not an implication that application destruction deletes external PostgreSQL or all task resources.

## Not verified by this scope

This failed deployment had no published business Gateway or completed model workflow. Empty
drain does not prove cancellation of active remote work. This record does not certify the 39
public operations on FC, real model tool execution, artifacts, multi-turn continuity, live cloud
SSE, revision updates, public PyPI installation or final cleanup of the ongoing deployment.
Those results must be recorded after they actually execute. No merge, release or whole-template
qualification is inferred; the architecture decision remains proposed pending its acceptance gates.
