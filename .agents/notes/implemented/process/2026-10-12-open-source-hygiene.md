# Decision: Open-source hygiene sweep and `check-no-local-paths` guard

Status: implemented

## Problem
Before the `python-sdk` repository is published, files inherited from the original
single repository still carried developer-machine specifics: an absolute
home-directory path used as the benchmark working directory, `.venv/bin/python` in
script usage text and evidence logs, a personal ACR namespace (as `.env.example`
value and as an implicit default in the e2e scripts), a hard-coded `ebx` invocation
in the e2e scripts, and a personal home directory in sample MCP output.

## Decision
1. Fix each finding the way a public-repo maintainer would:
   - Benchmarks and scripts derive paths from `__file__` (`Path(__file__).resolve()`),
     never from a fixed location; `benchmarks/bench_cli_startup.py` (which hard-coded
     the author's directory and the removed Python CLI) no longer exists here - the
     CLI benchmark lives in the `cli` repository.
   - Python entry points are invoked as `python ...` from the active interpreter
     (`sys.executable` where a subprocess is needed); usage text no longer says
     `.venv/bin/python`.
   - `scripts/e2e/e2e_build_and_test.py` and `scripts/e2e/quick_build_test.py` require
     `ACR_NAMESPACE` (no personal default; clear exit message), registry/repo/tag stay
     overridable (`ACR_REGISTRY`, `ACR_REPO`, `ACR_TAG`).
   - The `ebx` executable used by `scripts/e2e/cloud_e2e_test.py` and
     `examples/compat-demos/e2e_capability_validation.py` comes from `PATH`,
     overridable with `EBX_BIN`.
   - `.env.example`: `ACR_NAMESPACE=<your-namespace>`.
   - Docs: a user-home absolute path to `mcp.json` became `~/.cursor/mcp.json`.
   - Ignored `.agents/evidence` logs: `.venv/bin/python` / `.venv/bin/ruff` replaced
     by `python` / `ruff`.
2. Add a regression guard: `scripts/check-no-local-paths.sh` (bash + grep only, no
   `rg`) scans every tracked or untracked-but-not-ignored file for user-home paths,
   Windows user paths, `Documents/Qoder` / `chat-N` project directories,
   `.venv/bin|Scripts/`, agent scratch locations, the personal ACR namespace / fixed
   e2e tag, and AccessKey / API-key / token / private-key shaped strings (values are
   never echoed). Legitimate matches go into `scripts/local-paths.allowlist`
   (`<path-glob>[|<regex>]`, narrow entries with a justification).
3. Wire it in: `make hygiene` (also part of `make ci`) and a dedicated `hygiene` job
   in `.github/workflows/ci.yml`.

## Rationale
- Product names such as "Qoder" are legitimate in docs; only the path forms are
  rejected. `/home/user` (the sandbox's default home) is exempt.
- `platform="linux/amd64"` in the e2e build script is the sandbox runtime
  architecture, not a host assumption, and stays.
- Default `cn-hangzhou` region / `*.aliyuncs.com` endpoints are public product
  defaults, not account identifiers.

## Known gaps
- `docs/en/design/repository-layout.md` (split audit) quotes the leaks it describes
  and is allowlisted temporarily; remove the entry once the literal paths are
  scrubbed.
- `.agents/evidence/research/*pypi*` and `*ai-native*` (gitignored) mention the former
  personal `anycodes/*` placeholder project URLs; scrub them if the directory is
  ever un-ignored.
- `client-sdk/tests/test_protocol/test_filesystem.py` uses `C:\Users\test\...` as
  Windows-path parser test data (allowlisted).
- `.github/SECURITY.md` / `CODE_OF_CONDUCT.md` contain the maintainer contact email on
  purpose (not checked).
- `.env` (gitignored, local) holds real credentials; it is never committed, but must
  not be copied into the published repository.
