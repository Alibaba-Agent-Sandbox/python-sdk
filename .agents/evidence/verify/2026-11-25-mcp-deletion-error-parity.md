# Verification: MCP deletion error parity and reference follow-up

- Date:2026-11-25
- Result:PARTIAL — final paired checks and remote CI pending.
- Base:da6b0ef85f15798b84383c58d300374a4fbc3a11; editable paired0.5.0a1 source, Python3.11/Linux.
- Scope:one lifecycle-classification entry, two existing regression modules, bilingual
  lifecycle/Server API/current CLI usage references, changelog and owner records.

## Triage and review

The original170 deletion retry implementation is superseded by185. Exact diff inspection
found its lifecycle-classification entry was still absent from main;170 was not closed
as fully duplicated. Independent API/MCP review confirmed the one-line reuse, explicit
and default target coverage, and no equivalent omission among remaining lifecycle tools.
The broader execution/file tool error contracts are intentionally separate.
Second review found one remaining old process-command spelling; bounded current-guide
search also corrected pause/snapshot and troubleshooting CLI examples. Actual CLI help
confirms options precede the sandbox ID. Python registration and HTTP routes remain intact.

## Executed checks

- Added16 explicit/default deletion cases across8 existing exception classes: all16
  failed on the unchanged implementation. Failures use synthetic fixture values only.
- Corrected lifecycle/cleanup tests:119passed. Actual uvicorn HTTP over a temporary
  Unix socket exercises initialize, explicit/default `tools/call` errors, retained
  handle/default, DELETE503, successful sibling cleanup, same-session DELETE200/404.
  Provider failures are controlled doubles; this is real transport, not a new cloud run.
- `make lint typecheck format-check`:passed across both packages.
- Full paired `make test` in isolated user/PID/network namespaces with a child-reaping
  PID1 and loopback enabled:pending at this record checkpoint.

## Cleanup and boundaries

Temporary HTTP listeners and sockets are closed by existing finally blocks. No cloud
resources or package artifacts were published. The prior real Express cleanup run is
preserved in [the original evidence](2026-11-25-mcp-cleanup-retry.md), not counted again.
This patch does not complete native v1 templates, six Harnesses, Provider runtime downloads
or FC MCP deployment. Public0.5.0a1 remains the original immutable release.
