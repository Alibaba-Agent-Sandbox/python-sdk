# Verification: Public Python 0.5.0a0 delivery and CLI consumer checkpoint

- Date: 2026-11-25
- Change: [Issue #173](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/173)
  and [implemented decision](../../notes/implemented/process/2026-11-25-python-050a0-preview.md).
- Result: PASS for the public pair, scoped public-runtime checks and actual CLI
  consumer runs. CLI PR #271 remains open at this checkpoint; its actual merge
  and this record PR's normal CI/review/merge remain required before Issue #173
  closes. This is not a claim that the cross-repository integration has landed.
- Source: normal [PR #174](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/174)
  merge `26d679c3e5f67ac616b65b3db935db803c639be0`. Final reviewed
  `cde406277a336c40c447939e732881c5a1d15cf3` passed all 13 remote checks.
- Tag: `v0.5.0a0`, annotated tag object
  `339fb5203c0b3670192cbd957a04afd517816bfa`; an independent remote query peeled
  it to that exact merge. The tag and package artifacts were not replaced.
- [GitHub prerelease](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.5.0a0)
  published at 2026-11-25T05:30:32Z.
- [Sanitized combined receipt](2026-11-25-python-050a0-public-receipt.json)
  retains phase results, earlier failures and independent readback.

## What was verified

The normal tag-bound
[publisher run 45554059881](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/45554059881)
completed successfully at the actual merge. Its complete reusable validation
jobs, artifact preservation/preflight, server upload, client upload and fresh
public readback steps all succeeded. No GitHub Release creation or started job
was counted as a successful PyPI upload.

All four official PyPI artifact metadata digests and downloaded byte hashes
match the original [local candidate manifest](2026-11-25-python-050a0-artifacts.json).
The root task checked the public files, and this record's author independently
fetched both version metadata endpoints and all four actual downloads and
compared their hashes against that manifest and the root receipt.

A second independent fresh public environment passed client-only installation,
runtime absence and `pip check`, followed by exact matching `[server]`
installation, imports and `pip check`. Its original aggregate driver then failed
an incorrect candidate-directory assertion in the HTTP verifier. That failed
aggregate command is retained as failed; its successful install phases and the
separate corrected HTTP command are recorded independently.

The corrected verifier explicitly selected public-installed mode and bound the
module to `distribution.locate_file`, version 0.5.0a0 and all 58 server Python
files from the downloaded wheel. It retained wheel `app.py` hash, nonce, process
acknowledgement/drain, PID command-line and listener ownership checks. Direct
guest HTTP and SDK discovery/upload/download each round-tripped zero-byte and
8 MiB files with exact originating hashes. This is local isolated HTTP with
installed public packages, not another cloud upload run.

## Commands and runs

The public readback driver used the following requirements in its new environment:

```bash
python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --no-cache-dir 'agent-sandbox-client==0.5.0a0'
python -m pip check
python -m pip install --disable-pip-version-check --index-url https://pypi.org/simple --no-cache-dir 'agent-sandbox-client[server]==0.5.0a0'
python -m pip check
```

It removed inherited `PYTHONPATH` and `PYTHONHOME`, disabled pip config, verified
the base client had no `agent_sandbox.server`, and checked both exact versions.
The second fresh aggregate invocation `python public-python-readback.py` passed
these installation phases but failed its original HTTP verifier. After fixing
only the verifier, the separate passing command was normalized as:

```bash
ABX_VERIFY_INSTALLED_SERVER=1 ABX_VERIFY_WHEEL_DIR=<public-wheel-dir> unshare -Urn bash -c 'ip link set lo up && exec <public-venv>/bin/python local-ack-rehearsal.py'
```

The symbolic paths above identify task-owned public artifacts/environment, not
repository entry points. Product package files and HTTP assertions were unchanged.

## Results

| Gate | Result | Evidence and scope |
| --- | --- | --- |
| Actual preparation merge and immutable tag identity | PASS | Independently read actual main and peeled tag; normal merge at 26d679c |
| Tag-bound publication | PASS | Run 45554059881, all jobs successful; upload/readback steps succeeded |
| Four public artifact digests | PASS | Original candidate = official metadata = downloaded bytes; independent repeat agrees |
| Second fresh client-only installation | PASS | Version 0.5.0a0, server absent, standard/Provider/HTTP imports and `pip check` |
| Second fresh matching `[server]` installation | PASS | Exact server 0.5.0a0, runtime import/start and `pip check` |
| Original second fresh aggregate command | FAIL | Passed installation phases, then failed candidate-only verifier path assertion |
| Separate corrected public HTTP command | PASS | Same fresh environment, all 58 installed sources, runtime identity/listener and both zero-byte/8 MiB transfer paths |
| Full original local source test invocation | PASS with optional skips | [Separate unchanged result](2026-11-25-python-050a0-local-complete.md): server 895 passed; client 2,471 passed, 29 skipped; complete command exit 0 |
| CLI generated MCP public client consumer | PASS | Run 45555335298 at 39b2406; real generated HTTP/auth/initialize, 15 tool schemas/catalog, client 0.5.0a0 with server absent, owned process stopped |
| CLI production Docker consumer | PASS | Run 45555335003 at 39b2406; actual builder, two FC-base Dockerfile materializations, non-root runtime, exact version and complete module source comparison |
| CLI pin integration merge | Pending | PR #271 is open/Draft at this checkpoint |
| Final owner record CI/review/merge | Pending | This PR must pass the normal gates; Issue #173 remains open |

## CLI consumer boundaries

The consumer head is `39b240685147876fa29232c209191cbc33a94095` in
[CLI PR #271](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/271),
tracked by [CLI Issue #270](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/270).
Independent API readback confirmed both completed/success workflows at that head:

- [Generated MCP artifact run 45555335298](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/actions/runs/45555335298)
  generated the real project, installed its exact public requirements and tested
  actual HTTP. The result has 15 tools, missing/wrong authentication rejection,
  initialize and schema checks, and zero cloud requests. It does not certify
  invoking every tool against a cloud sandbox.
- [Server wheel Docker run 45555335003](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/actions/runs/45555335003)
  used the production DockerBuilder and a source wheel built from the exact
  Python `v0.5.0a0` checkout. Both conditional and continued `RUN` cases executed
  in real FC-base images, including non-root checks, original application/`RUN`
  effects and complete installed Python source comparison. This is distinct
  from the separate public-wheel install/HTTP check; it is not a direct public
  wheel download inside Docker or an FC cloud deployment.

The exact tested workflow and verifier source at that commit were also reviewed.
Successful consumer checks do not mean PR #271 has merged. Use `Refs`, not an
automatic Issue closure, until the root task confirms its actual merge and the
final owner record gates.

## Earlier failures and corrections

Initial public metadata requests returned HTTP 404 before both version endpoints
were observed at HTTP 200. A first fresh environment passed base-client checks
but its first `[server]` install returned exit 1. The driver captured only static
classification, not pip stdout/stderr, so the exact cause is unknown. Retrying
the same requirement returned exit 0; neither that retry nor later installs
rewrite the first attempt as passed.

The second fresh aggregate invocation's startup log identified the correct
public `site-packages` module, rejected by the verifier's candidate-only path
assertion. Explicit public mode fixed that verification error while retaining
the exact origin/version/source and live identity checks. The original aggregate
failure is not converted into a pass, and no product change is attributed to it.

## Cleanup

The public HTTP verifier closed its clients/readers, terminated/reaped owned
processes and removed temporary server state. The MCP receipt confirms its owned
process stopped. Docker used `--rm` containers and finally-based image/context
cleanup; its workflow intentionally retained a reviewed image archive artifact
for one day. No independent account-wide or image-store purge is claimed.

This record created no new cloud sandbox, database or deployment. The original
candidate cloud [upload/cleanup evidence](2026-11-25-bounded-file-uploads-cloud.md)
remains independently scoped; among its 58 server Python files only `_version.py`
changed in this published pair. Original failed cloud probes and cleanup facts
remain unchanged.

## Limits

This verifies the matching public Python pair and the concrete CLI consumer
paths. It does not upgrade existing sandbox images, certify all templates or
Providers, execute a model business task, establish performance/peak-memory
budgets, or add true HTTP streaming. Earlier preparation checkpoints remain
historical. Package/tag changes are absent from this final record PR.

## Owner record checks

```bash
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

Health reports 106 passes, one existing release-runbook warning and no failures;
hygiene and whitespace checks pass. Both receipt JSON documents parse. A separate
comparison confirms the earlier preparation/changelog checkpoints changed only
their relocated ADR link target, and the complete local result is copied with
only that same link adjustment. All changed paths are engineering records;
package source, tests, artifacts and the published tag are unchanged. This
documentation-only record does not repeat product/cloud tests already identified
above. Its latest-head normal remote CI/review/merge remain pending.
