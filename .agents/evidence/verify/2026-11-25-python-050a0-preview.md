# Verification: Python 0.5.0a0 preview preparation

- Date: 2026-11-25
- Change: [Issue #173](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/173)
  and [decision](../../notes/proposed/process/2026-11-25-python-050a0-preview.md).
- Result: PARTIAL. Candidate packaging and scoped owner checks pass; full local
  tests, latest-head remote CI/review, actual publication and CLI consumer gates
  are separate pending checks at this checkpoint.
- Base: actual main `d333d9d51387c89027987d4cfda4f6d2a9ce0daa`, the normal squash
  merge of PR #172 on 2026-11-25. Its final reviewed `b516356` head passed all 13
  remote checks and Issue #171 closed. This release preparation contains neither
  pending feature branches nor a package-publication claim.
- Packages: matching local client/server 0.5.0a0 source candidates.
- Environment: Linux, Python 3.13.13, declared existing build/dev tools. Fresh
  installation checks use new virtual environments. No cloud resource was
  created and no credentials are recorded.

## What was verified

Both source versions and the optional server requirement select 0.5.0a0. Wheel
metadata confirms the base client has no unconditional server dependency and the
`server`, `all` and `dev` extras require the exact matching server. Both wheels
and sdists include READMEs matching the final source, selecting 0.5.0a0 and using
the supported template build/deploy commands.

The two installation/SDK guide languages describe base-client installation,
matching local runtime, removal of module-level application calls and rebuilding
existing sandbox images. They select the 0.5 preview and link available releases;
they do not assert that PyPI already serves this candidate.

The delivered upload ADR is moved to `implemented`, naming its actual merge.
Only the ADR link targets in the three earlier evidence pages change with this
move; their commands, failures, results and cloud-result JSON remain unchanged.

## Commands run

Using the existing project build environment:

```bash
python -m build --outdir dist/server-sdk server-sdk
python -m build --outdir dist/client-sdk client-sdk
make dist-check
python scripts/check_release.py candidate --tag v0.5.0a0
make lint typecheck format-check
bash scripts/check-repo-health.sh
make hygiene
git diff --check
```

An independent Python archive inspection records the four artifact hashes,
dependency lines, embedded README identity and cloud-source delta in the
[candidate manifest](2026-11-25-python-050a0-artifacts.json). It validates UTF-8
metadata and the sdist README bytes rather than trusting source version strings.

Full `make test` runs in an isolated user/PID/network namespace, with private
`/proc`, enabled loopback and the same child-reaping PID 1 used for the earlier
managed-process follow-up. Source paths select this worktree without changing
the shared test environment's editable installation. This original invocation
is pending at this checkpoint; no test assertion or timeout is changed.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Both wheel/sdist builds | PASS | Exactly four 0.5.0a0 candidate artifacts |
| Versions and matching server extras | PASS | Client-only metadata plus exact `server`/`all`/`dev` pins |
| Embedded READMEs | PASS | Wheels and sdists match final source; no old exact install pin or retired template deploy spelling |
| Distribution and installation checks | PASS | Twine, both `py.typed` markers, clean client-only imports/real local HTTP, then matching `[server]` registration/imports and `pip check` |
| Candidate tag agreement check | PASS | Both `_version.py` values match the supplied tag text; this does not create a tag |
| Previous cloud candidate delta | PASS | Of 58 server Python files, only `_version.py` differs; the actual upload/runtime implementation is identical |
| Owner checks | PASS | Lint, type, format, health, hygiene and whitespace checks |
| Full local regression command | Pending | Original result will be recorded in new follow-up evidence |
| Latest-head remote CI/review | Pending | A Draft PR triggers the full matrix while local tests run |
| Publication | Not performed | Both official 0.5.0a0 metadata endpoints returned 404 during preparation; no tag/release/upload created |
| CLI image/HTTP MCP consumption | Pending | Requires actual public pair and the owner gate below |

An initial artifact inspection caught READMEs built before their final edits, so
both package artifacts were rebuilt. A subsequent verification utility used the
email parser's default ASCII body decoding and reported a false UTF-8 README
mismatch; explicit UTF-8 decoding corrected the verifier without altering source
or artifacts. The final archive checks above passed with the full assertions.

## Cleanup

Fresh distribution-check environments and local HTTP servers are cleaned up by
their existing context/finally handling. No new cloud resource was created.

## Problems found

The installed package README still used retired `abx template build|deploy`
spelling. Its candidate instructions now name `abx template build` and
`abx deploy <reference> --name <name>` explicitly. Historical versioned examples
and original release receipts are retained.

## Not verified

This checkpoint is preparation, not complete release acceptance. The full local
test command and latest-head remote CI/review remain outstanding here. Actual
publication must use the existing tag-bound workflow, four preserved artifacts,
digest preflight, server-before-client order and fresh public readback.

[CLI Issue #270](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/270)
and [CLI PR #271](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/271)
retain the real image and HTTP MCP consumption gate for the public 0.5 pair.
Issue #173 must remain open until publication and that consumer acceptance pass.
No new cloud matrix, true HTTP streaming, model task or peak-memory claim is made.

The inherited [real upload evidence](2026-11-25-bounded-file-uploads-cloud.md)
keeps its original version and scope. The root task supplied the normalized
invocations: local `unshare -Urn bash -c 'ip link set lo up && exec python local-ack-rehearsal.py'`
with its project interpreter, and `python auth-run.py python cloud-uploads-ack.py`
with the credential child runner and the same interpreter. The cloud driver
explicitly bound `alicloud-express`, API key/base URL/domain, template `base`,
900-second sandbox TTL and 90-second create request timeout. These command
details supplement the earlier record without reclassifying its failures.
