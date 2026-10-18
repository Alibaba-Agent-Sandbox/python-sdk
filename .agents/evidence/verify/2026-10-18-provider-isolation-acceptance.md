# Verification: Provider isolation and current Express acceptance

- Date: 2026-10-18
- Result: PASS for the implemented host/adapter isolation and tested Express configuration. Other native backend feature acceptance remains explicitly outside this result.
- Tested implementation: `937eb5edc5330c9afe7577604c1078f22c17f079`; CLI `12f0d693da415e0e3827a319d29d669a83ac090d`, Python `937eb5edc5330c9afe7577604c1078f22c17f079`.
- Delivery: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35 and https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38. Both were unmerged when this evidence snapshot was written; the final evidence-only head must also pass configured checks before merging.
- Environment: Linux, Node 22.22.2, Python 3.11.15, real Express cn-hangzhou with existing `base` template. Existing credentials stayed in the ignored environment; temporary key material was private and deleted.

## Observable behavior

Every lifecycle uses the selected Provider, including bundled Express. Authentication,
cloud SDK/API mapping, template deployment/polling, wire protocol choice, data-plane and
port/file URL formats, gateway headers, backend CLI/AI/configuration metadata remain in
owned adapters. Compatibility exports are explicit facades; neutral Python imports remain
lazy. Async-only providers get E8004 from synchronous URL helpers, and their asynchronous
resolver returns their own URL and headers. Missing hooks never fabricate native behavior.
Created-resource binding failures clean up owned resources; failed connects preserve borrowed ones.

Bundled update reports the current host release, unknown latest version and matching
upgrade guidance. External Git-plugin update/ref/consent/integrity/rollback behavior is
preserved. Existing Express resources can be reused; replacing an SDK still requires the
documented import/API/configuration adjustments. This is not a zero-change migration claim.

## Executed checks

- Both-package Python lint/format/mypy: PASS, 101 client and 56 server modules.
- Latest full Python client: **2177 passed, 24 skipped**, 149.56 seconds. Skips identify optional build/CLI checkout/engine prerequisites; they are not passes.
- Latest local server: **853 passed, 2 failed, 1 skipped**. The two intentional malformed HTTP probes receive intermediary 501/502 responses locally; unchanged assertions pass in all hosted server jobs. Earlier failed attempts remain in separate immutable checkpoints.
- Latest full CLI in the temporary locked-dependency checkout: **3913 passed, 20 failed, 2 skipped**. All 20 failures reproduce against unchanged main after normalizing the Cube no-PTY test name; hosted Node 20/22 passes. No test timeout or malformed-response assertion was weakened.
- CLI source/test/script/E2E snapshot: **563 files, zero content differences**; SHA256 `7e49f73998ee51654f8bd2dd7846bdb051b987e4167012ef709f43eaf8177682`. This separates slow workspace module-scope I/O from execution without increasing test budgets.
- CLI parity ledger: **907 passed, zero failed/skipped, zero missing**; 11 previously moved SDK entries are reported separately.
- CLI strict typecheck/build: PASS. ESLint: zero errors, 248 warnings. npm 10 dry-run contents: PASS.
- Python wheel/sdist build, twine, py.typed and combined clean install/import: PASS.
- New offline CLI capture: **114 cases, zero skipped, 17 documents**, preserved alongside historical captures.
- Linux executable build/version smoke: PASS; SHA256 `8797dbe0bf6b1f3ecac8afb28c37aa2f9f1e38263cb26ac1e7cd50a8d65e34ed`.
- Repository health: CLI **105 pass / 11 historical warnings / zero failures**; SDK **106 pass / 1 historical warning / zero failures**. Hygiene and configured-secret scans: PASS.

Hosted checks on this owner's tested implementation revision:

- [Build packages](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117701432415): PASS
- [server-sdk (Python 3.11)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250797): PASS
- [server-sdk (Python 3.12)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250731): PASS
- [No local paths or secrets](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250700): PASS
- [Markdown links](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909194/job/117700250688): PASS
- [client-sdk (Python 3.12)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250674): PASS
- [client-sdk (Python 3.11)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250659): PASS
- [client-sdk (Python 3.10)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250629): PASS
- [server-sdk (Python 3.10)](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/39135909258/job/117700250482): PASS

## Real Express acceptance

Commands used the ignored environment in memory and sanitized output; placeholder values
below describe actual private inputs, not published credential/resource identifiers.

```sh
python -m pytest -m 'e2e and not e2e_slow' -q -ra
ABX_BIN=<built-executable> node e2e/run.mjs --suite offline
ABX_BIN=<built-executable> node e2e/run.mjs --suite offline,cloud-readonly,cloud-lifecycle,provider-commands-offline,provider-management-cloud
ABX_E2E_VOLUME_MOUNT=1 E2E_VOLUME_TEMPLATE=base python -m pytest test_09_volume_mounts.py -q -ra
ABX_BIN=<built-executable> ABX_E2E_VOLUME_MOUNT=1 ABX_E2E_TEMPLATE=base node e2e/run.mjs --suite volume-mount-cloud
```

- Full configured Python E2E after the port changes: **116 passed, 6 skipped, 2 deselected, 1 documented platform xfail**, 422.92 seconds.
- Its skips were four unconfigured native backend environments and two separately gated storage cases. The latter then ran successfully with newly provisioned temporary storage as described below.
- The known xfail remains KI-009: this cloud's Jupyter endpoint returns HTTP 404, so shell fallback cannot return the value of a trailing expression. This is not relabeled as full interpreter parity.
- Combined executable acceptance initially had **142 passed, 2 failed, 1 guarded destructive skip**. Both failures were offline harness region inheritance. Cloud/management cases all passed, including real `/proc` process info and measured system metrics; two owned sandboxes deleted, zero leaked.
- After fixing harness environment isolation, offline acceptance: **61 passed, 1 no-resource leak-check skip**. A regression also proves cloud regions are passed only through the explicit credential map.

### Fresh real storage and persistence

Using the user's existing AK/SK authorization, the run created one private OSS Bucket,
one FC-trusted RAM role, one custom policy restricted to that Bucket, one Volume, and
one exclusive API key belonging to the same existing Team. It did not modify that Team
or existing credentials, roles, policies or storage. The temporary key file used mode 0600.

- Volume reached AVAILABLE and its key's Team identity was checked.
- Current Python HTTP lifecycle formal storage suite: **2 passed in 13.52 seconds**. Both mount tables were checked. A sentinel survived destruction of the first sandbox and recreation in a different sandbox, then was read and removed.
- Current standalone executable formal mount suite: **2 passed** including leak check; one owned sandbox created and removed. The mount roundtrip case took 6557 ms.
- Independent OSS listing confirmed the new Bucket had no residual objects after the suites.
- Temporary infrastructure dependencies were isolated from product/test dependencies: oss2 2.19.1, alibabacloud-ram20150501 1.3.0, alibabacloud-sts20150401 1.2.0 and python-dotenv 1.2.4. An initial dependency install used an incorrect legacy package name; resolution failed before any cloud resource creation, then the correct locked package names installed.

Official prerequisites were rechecked against [mounting](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1) and [FC role configuration](https://help.aliyun.com/zh/agent-sandbox/create-ram-role). The orchestration remains test tooling outside the product; provisioning is not core backend logic.

## Cleanup

The full Python acceptance was followed by an independent SDK listing showing **zero total
sandboxes**. Executable cloud and storage suites each reported zero leaked resources.
Storage tests released their three Python sandboxes and one binary sandbox. The temporary
key was made inactive, deleted and not-found verified; the Volume was deleted and not-found
verified; objects/multipart uploads and the Bucket were removed, with NoSuchBucket verified.

The initial three RAM policy/role cleanup operations failed. A private recovery ledger
recorded only owned identifiers; a subsequent attempt detached the same owned policy,
deleted it and the role, then verified EntityNotExist for each. The ledger and generated
key file were removed. No failed cleanup is silently counted as a first-attempt pass.

## Limits and remaining native work

Native E2B credentials, an authorized CubeAPI, an ACS/ACK container sandbox-manager and
a working OpenSandbox runtime remain unavailable. No Docker or Podman executable is
installed in this restricted environment; the local OpenSandbox bootstrap requires
privileged system installation/mounts outside the writable workspace, which cannot be
performed under the current permissions. These prerequisites were requested and are
not inferred from Express credentials.

No new native image-factory acceptance, publication, full-region/full-template feature
parity or zero-change SDK substitution is claimed. Optional image-factory PRs stay separate
and unactivated. Historical failures and earlier native gRPC acceptance are preserved as
history; this run verifies the current direct HTTP Express lifecycle.
