# Verification: builtin native HTTP data plane

- Date:2026-10-18
- Result:PARTIAL; configured component acceptance passes, final hosted gates pending.
- Base:42d4449, accepted auth/replay source; auth PR56 now merged.
- Scope:builtin create/process/files/terminal migration, old Python bridge and
  grpc/protobuf dependency removal, bilingual migration and owner records.

## Checks and results

- Original focused create/MCP/replay baseline:145 PASS.
- Migrated focused suite:144 PASS; the sole removed adapter-specific bounded
  file test references the deleted bridge. Direct bounded file tests remain.
- New end-to-end HTTP-mocked public API regressions:2 PASS, envd0.5.2/0.6.1.
  Verify all creation options/request timeout, platform metadata/resources/alias,
  binary bytes, generation-dependent outgoing stream framing and cleanup.
  The retired engine import is blocked and socket absent in these unit tests.
  Initial test fixtures omitted the user query/basic auth; corrected to the
  existing native protocol. These are unit tests, not cloud proof.
- Full normal client:2082 PASS /1 FAIL /21 SKIP /10 DESELECTED. The one local
  server-policy HTTP loopback request disconnected; exact isolated repeat:1 PASS.
  One existing event-loop subprocess warning. No claim of a green full local run.
- Fresh full configured real-cloud suite on native source:116 PASS /4 SKIP /
  1 XFAIL /2 DESELECTED, exit0 in332.89s. Includes the new bounded background
  worker test:held handle refreshes state while an independent connection polls
  completion, then both read the same live sandbox. No automatic write replay.
- Janitor exit0:zero candidates and zero total sandboxes. Node-provider suites
  and actual built CLI lifecycle also pass in that configured suite.
- Ruff client/server and both distributions/twine/py.typed/combined wheel
  installation:PASS. Final alias spelling cleanup preserves the identical
  payload and satisfies the Pydantic type stub. Final focused146 PASS, full
  client/server lint/format and mypy PASS (80 client/56 server files).
- Health106 PASS /1 existing WARN /0 FAIL; hygiene PASS.

## Limits

Native OpenSandbox/Cube/E2B/container credentials/runtimes absent:four explicit
skips, never provider passes. Jupyter404 remains the existing strict xfail.
The specific original Droid installation failure is not reproduced merely by
this background regression; Issue35 remains open for that separate acceptance.
Hosted full three-interpreter client/server, package/links/hygiene and final
review remain required. No server implementation or Node engine was deleted.
