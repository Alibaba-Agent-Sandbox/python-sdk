# Verification: public a6 installation and current guidance

- Date: 2026-10-25
- Result: PASS for actual public checks below; this guidance follow-up's exact-head CI, independent review and merge remain pending.
- Runtime: official non-all client/server `0.4.0a6`, Python 3.13.13, Linux; new ordinary environment, isolated HOME and working directory outside the checkout, no PYTHONPATH/editable injection.
- Source/tag: `8e610a3658040d8d6973e7951f9590ea50a4d70a`, immutable `v0.4.0a6`, annotated object `21228b09e40c2ef64bf268f0db3b64f27ddf8186`.
- Source PR: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/131

## Publication and artifact readback

Exact reviewed head `4c45a404fa101d4740305f2431083a28bc6e2467` passed all 13
required checks and independent review before normal SHA-bound squash merge.
The actual main tree equals the reviewed tree. Existing publisher
[40225846586](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40225846586)
completed SUCCESS on attempt1 after all 12 tag-validation jobs. The tag, release
and both version-specific public metadata endpoints were absent before creation.
Initial independent metadata reads observed HTTP404 after upload; later official
metadata/downloads were HTTP200. No digest mismatch or retry mechanism change
was introduced; normal bounded publication verification passed.

Original preserved artifact12611362808 and official metadata/actual download
bytes match for all four files:

| File | SHA-256 |
| --- | --- |
| client wheel | `0a4d9c4b322b1e28b4dc4bc9c4a36b867232afc61fa87b483cae65f4eebb9222` |
| client sdist | `bf57cae0eb81dc1a95a9e7ed4862ec3af15e7b5dba2d6283b9be2bced4616aa6` |
| server wheel | `85b937438acf943b3d92736dd6a07c4829cd80416336da35c0b25f2e5679850d` |
| server sdist | `812388ba126973e7ab5911214eaacdd7b352a6ef81356a2ce099e2af3341e6c3` |

The package READMEs use the official index and `--pre`; neither embedded wheel
README contains an obsolete fixed a4 installation pin. The
[sanitized combined receipt](2026-10-25-public-a6-delivery.json) records artifact,
installation, help, multiline, real HTTP and actual current-design results.

## Fresh public installation and commands

```bash
python3 -m venv public-sdk
public-sdk/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a6'
public-sdk/bin/python -m pip check
```

The actual install used no all extra and automatically installed matching server6.
Standard synchronous/asynchronous, Provider and server imports resolved from
site-packages. All 28 first-party Template/Sandbox help imports executed and
resolved to the correct root/interpreter identities. All 390 installed Python
files / 2358 docstrings had zero retired upstream namespace import residue;
neither e2b package was installed. Twelve Provider help/signature checks passed,
and 24 retired Provider keyword binds still rejected without network requests.
The four corrected source-file bytes matched the reviewed source.

Three additional unique multiline error imports from six EN/ZH guide/reference
locations executed successfully on actual public a6. This is a separately scoped
supplement; earlier audit totals and line-fallback limitations remain unchanged.
The current-document scan's 33 actual public-a5 imports already included these
three, but that result is not relabeled as a6 execution.

## Real HTTP, document programs and cleanup

Fresh public-a6 local server/client health, shell output `4`, file roundtrip and
independent absence of the owned server PID passed. The private server was
terminated and no unrelated process was touched.

Both complete current design-page programs were extracted unchanged from source
`8e610a3` and rerun on the public non-all a6 environment. The six EN/ZH Python
block occurrences still map to the same two exact source hashes:

- Command/file/context cleanup: PASS, 2.730s.
- `base` plus `commands.run("sleep 100", timeout=5)`: actual typed E3001 with
  finally deletion/closure, PASS, 7.350s.
- Both examples' own cleanup had already removed the resources; observer recovery
  was never counted passing. A second independent process confirmed typed
  SandboxNotFoundError for both exact owned resources (2/2).

These two cloud calls are separate from the earlier public-a5 document run and
the public-a4 14-example/local runner receipts. Those histories remain unchanged.
[Subsequent public-a6 example acceptance](2026-10-25-public-a6-examples.md) separately
records the new 14-example cloud run, 29 independently absent owned resources and
local runner with real negative timeout controls. The earlier results are not
relabeled.

## Current guidance and owner checks

The follow-up changes 38 current install/fixture files to exact public a6,
including two Skills and both official-index Docker recipes. The existing CI
guest-version assertion selects a6. No API/runtime/version file changes occur.
The only Python example edit is an installation docstring; execution AST is
unchanged. Both already delivered help process notes are accepted with actual
merge/publication facts; older evidence is unchanged.

Local record/link health passed (106 checks, one existing missing release.md
warning, zero failures); hygiene and diff checks passed. Exact-head remote CI,
independent review and merge remain pending for this follow-up. No Docker engine is available locally, so actual fixture builds
must pass the existing remote Docker jobs before normal merge. No new package
or release tag is created for this documentation update. Host installation does
not update older sandbox images or certify the full template catalog or models.
