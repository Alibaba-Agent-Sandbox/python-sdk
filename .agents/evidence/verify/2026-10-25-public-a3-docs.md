# Public a3 release and maintained guidance verification

Date: 2026-10-25
Result: PARTIAL (public release/cloud PASS; follow-up source delivery pending)

Scope: current English/Chinese installation pages, two coding-agent skills, two
SDK fixture Dockerfiles and their existing version assertion, current engineering
navigation. Based on merged a7d6aa3e5e16fcf8cde1d91465f4a5fc53f5a030. No runtime
code or new package version; previous evidence is unchanged.

## Immutable publication and independent readback

- [PR 122](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/122) merged at
  a7d6aa3e5e16fcf8cde1d91465f4a5fc53f5a030 after all 13 exact-head checks and
  independent review. Annotated tag v0.4.0a3 resolves to this merge.
- [Publish run 40209677091](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40209677091):
  completed SUCCESS, including complete tag CI, four builds, preflight, ordered
  server/client upload, public hash verification and fresh installation.
- Independently downloaded preserved release artifact 12605089634. Each of its
  four SHA-256 values matched public PyPI metadata and actual downloaded bytes.
  The adjacent JSON contains exact filenames, hashes, tag, source and results.
- Python 3.13.13 new environment, official PyPI `--no-cache-dir` exact client a3
  install: PASS; matching server installed automatically, `pip check` PASS.
  Standard sync/async, ProviderSandbox and server imports resolved inside that
  environment, with no PYTHONPATH injection and a working directory outside Git.

## Actual public-package behavior

The unchanged candidate reproduction script was rerun with public a3. Its source
hash is e59c64622435cc7cdd5e28dc8ce37b0fe809145188c16db6d8bcf4923bcf3ccc;
installed runtime bytes match the reviewed fix. Delayed readiness returned five
nonzero probes, then zero and successful launch, with the exact server PID alive.
A permanent-unready case used a 1s budget and the existing typed phase failure
arrived after 1.195s including cleanup. Cancellation after the first probe also
cleaned up. All three owned sandboxes independently returned typed NotFound.
No recovery, fixed harness wait or weaker assertion was needed. Issue 121 closed
only after this actual public-package verification; Issue 111 remains separate.

## Follow-up checks

- Maintained old-installation sweep and decorator executable-AST comparison: PASS.
- Document/record health: PASS, 106 checks, one warning, zero failures.
- Hygiene and `git diff --check`: PASS. Current install pin sweep found no old
  maintained install. The explicitly dated repository-layout review retains its
  historical 0.3.0 measurements; it is not a current installation recipe.
- Decorator example executable AST: unchanged; only its install docstring changed.
- Existing Docker fixture and full latest-head owner CI: pending; no local Docker.

This is not a new 50-template matrix, real-model test or production certification.
The earlier a2/raw-HTTP failures and candidate T4 keep their exact recorded scope.
