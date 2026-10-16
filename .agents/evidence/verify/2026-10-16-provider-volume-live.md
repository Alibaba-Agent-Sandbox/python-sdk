# Verification: real Python Volume mount and independent OSS readback

- Date: 2026-10-16.
- Result: PARTIAL overall; real Volume mount/read/write/cleanup PASS.
- Tested SDK revision: `ec595c81030b30f0669de8989c0c432a74d136a0`, both source packages on PYTHONPATH.
- Shared CLI product revision: `940b9d558bd40d364bf9f4619e11f94eb91f37e3`.
- Environment: Linux, Python 3.11.15, Node 22.22.2, Alibaba Cloud cn-hangzhou.
- Issue/PR: [#34](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/34),
  [draft PR #38](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38).

## Commands and behavior

With the user's explicit authorization, the host provisioned temporary infrastructure using
existing AK/SK; the Python run used a newly created same-Team sandbox key. The repository
configuration and original credentials were not changed. Source packages were selected with
PYTHONPATH; `ABX_ENGINE_SOCKET` was unique for this run, `E2E_VOLUME_TEMPLATE=base`,
`ABX_E2E_VOLUME_MOUNT=1`, and the exact owned Volume/path were passed privately.

```sh
python -m pytest e2e/test_09_volume_mounts.py -q --tb=short
```

The formal scenario passed **1 test in 8.06 seconds**. It used the actual public API, local
gRPC engine, real cloud sandbox, kernel mount inspection and guarded sentinel I/O/cleanup.
An additional independent script used `Sandbox.create(volume_mounts=...)` and the public
commands/files/kill/info APIs, with a separate OSS SDK process checking object contents and
subsequent absence. No mock provided these storage results.

Infrastructure ownership and detailed Team/key/quota results belong to the
[host verification](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/feat/provider-operations-20261016/.agents/evidence/verify/2026-10-16-provider-volume-live.md).

## Real storage results

| Check | Result | Observable evidence |
| --- | --- | --- |
| Private OSS Bucket and FC-trusted RAM role | PASS | Dedicated custom policy grants access only to the newly created Bucket; no existing role/policy was modified. |
| Volume create/get/list/delete | PASS | Two sequential test Volumes reached AVAILABLE; role configuration persisted; deleted resources returned not-found. |
| Dedicated same-Team API key | PASS | Exclusive secret file mode 0600; CLI output redacted; key metadata matched the Volume Team. |
| CLI `volume-mount-cloud/existing-volume-roundtrip` | PASS | Exact kernel mount checked before exclusive sentinel write/read/delete; sandbox deletion and built-in leak check passed. |
| Python `e2e/test_09_volume_mounts.py` | PASS | 1 passed in 8.06 seconds through the real built-in gRPC lifecycle. |
| Independent Python/OSS cross-check | PASS | SDK-created sandbox mounted the Volume, wrote/fsynced an exclusive file; separate OSS API read identical bytes, SDK read agreed, and OSS confirmed deletion. |
| Tagged sandbox query | PASS | Zero remaining resources with either exact test-run metadata tag. |

The test explicitly selected the `base` template in cn-hangzhou; this is not a claim about
all templates or regions. Custom MicroVM source images require ossfs2 >= 2.0.10 according to
the [official mounting guide](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1).
The root credentials were read from the existing ignored configuration and passed privately;
no credential values, account IDs or private resource names are included here.

## Cleanup

The initial three test sandboxes were deleted and their absence checked. The first
infrastructure run removed two sequential Volumes, one private Bucket, one RAM role, one
bucket-scoped custom policy and one dedicated API key. A second independent infrastructure
run supplies the added sandbox-recreation check, recorded below. Cleanup order was sandboxes, inactive/delete key, Volume, Bucket objects and
multipart uploads/Bucket, policy attachment/custom policy, then role. Each control plane
confirmed not-found, including OSS NoSuchBucket and RAM EntityNotExist. The generated key
file was removed. Existing Teams, subscriptions, credentials, storage and permissions were
not modified. Separate empty-Team/quota tests deleted their own quota overrides and Teams.

## Failed setup attempts and limits

An initial supplemental cross-check passed the unsupported `base_url` keyword to
`Sandbox.create`; it failed with TypeError before creating any sandbox. The corrected
`sandbox_base_url` invocation passed all independent checks. An initial anchored runner
filter selected zero scenarios: its zero exit is excluded from verification results. The
corrected filter explicitly checked the number and status of selected cases.

An attempt to reuse the deleted Bucket name for the supplemental run received OSS
BucketAlreadyExists (409), despite another NoSuchBucket read. No existing Bucket was
adopted or deleted; a fresh random name passed the unused-name guard and provisioning.

The legacy locked FCSandbox SDK exposes Volume status updates without a documented writable
transition. No transition was invented or tested. Newer storage types, STS credentials,
dynamic mount/attach, custom domains and other templates/regions are not established by
this run. Domain API prerequisites remain tracked in
[CLI #32](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/32).

## Repository checks and remaining gates

- Repository health: **106 PASS / 1 WARN / 0 FAIL**.
- Formal Python real Volume scenario: **1 PASS**; SDK product source is unchanged; the published opt-in E2E scenario adds persistence coverage.
- Hygiene and `git diff --check`: PASS, exit 0.

The previous required local server suite remains **847 PASS / 8 FAIL**; the full isolated
client suite previously passed **1981 tests / 23 SKIP**. Those historical attempts are in
[integration evidence](2026-10-16-provider-command-integration-final.md).
No new full local make-ci pass is claimed for this E2E/translated documentation follow-up.
Real mount acceptance is now established for the tested configuration. The shared host must
land first, and the required local aggregates remain unresolved. PR #38 stays draft/unmerged;
the ADR remains proposed. Historical evidence is preserved unchanged.

## Supplemental persistence acceptance

The extended published Python suite ran at `ec595c8` plus the scoped changes to
`e2e/test_09_volume_mounts.py`: **2 PASS in 17.17 seconds**, exit 0. The original mount
roundtrip passed again. The added persistence case wrote/fsynced an exclusive file,
destroyed the first sandbox, required its exact not-found result, created a different
sandbox mounting the same Volume, then required identical contents and deleted the file.
Both sandbox mount tables were independently inspected before file I/O. Missing persisted
files fail the read step; cleanup mode alone cannot substitute for this assertion.
An independent, paginated SDK query using the exact run metadata confirmed **zero remaining
owned sandboxes** before the test key was revoked.

The supplemental run's three sandboxes were removed. Its dedicated key was inactivated,
deleted and not-found verified; both sequential Volume resources were deleted; Bucket
objects/multipart uploads and the Bucket were removed (NoSuchBucket); the temporary policy
was detached/deleted and the role deleted (RAM EntityNotExist). The second-run cleanup
completed successfully with every owned resource absent. Across the two infrastructure
runs, six sandboxes, four sequential Volumes and two Bucket/role/custom-policy/key sets
were created and cleaned up; the metadata-only Team/key/quota runs also cleaned up their
own resources. Generated key files were removed; original credentials were unchanged.

Scoped Ruff lint, Ruff format check and Python compilation of the changed E2E module PASS.
