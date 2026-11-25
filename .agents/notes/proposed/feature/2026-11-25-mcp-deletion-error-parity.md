# Decision: Complete deletion error parity and current reference guidance
Status: proposed

## Problem

The final review of Issue169 and draft170 found one remaining change after merged185:
the explicit/default `kill_sandbox` tool was absent from the existing lifecycle error
classification. Its failure therefore followed the generic tool error path even though
its ownership and connection retry behavior had already been corrected.

The Server API reference also still described pip subprocess inventory after185 changed
the implementation to installed distribution metadata. Five current bilingual SDK
guides retained removed CLI wrappers or internal build-file handoffs.

## Decision

Add deletion to the existing lifecycle classification, without changing platform calls,
state transitions, credentials, request schemas or the other tool error paths. Extend
the existing classification and real HTTP cleanup tests for explicit/default deletion.
Correct the affected bilingual references and current CLI examples; keep Python
decorators, HTTP routes and native deployment selection unchanged.

## API Design

No new API or input is added. Deletion failures use the same fixed categories, safe
HTTP status, SDK code and static suggestions as other lifecycle tools. Package inventory
documentation describes the already published current-interpreter behavior. CLI business
operations require a bound OpenAPI contract; registration alone does not create one.

## Alternatives considered

- Merge all of old170: its retry-state implementation is superseded by185 and would
  discard later cancellation/session/client-close corrections.
- Add a new error sanitizer or change Provider exceptions: unnecessary; reuse the
  existing classification and its tested error model.
- Rename Python registration and server routes with the CLI: changes independent APIs
  without solving the documentation mismatch.

## Dependencies

Existing MCP lifecycle formatter and HTTP transport; no new package or version.
Refs [169](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/169),
[170](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/170),
[184](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/184),
[185](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/185).

## Test Strategy

First run the additional16 error cases against the unchanged implementation. Re-run
the lifecycle and real Unix-socket HTTP checks with the correction, full paired suites,
lint/type/format, repository records and current-head remote CI. Inspect the complete
lifecycle-tool set for other equivalent omissions. Do not relabel the earlier real
Express cleanup acceptance as a new run or create unrelated cloud resources.

## Acceptance criteria

- Explicit/default deletion results and logs preserve useful categories and omit raw
  synthetic exception values and traceback details.
- Failed deletion keeps the same handle/default; HTTP termination still retries.
- Python inventory and current CLI documentation match their existing implementations.
- Required checks and independent review pass; only then close the superseded170/169.
- No package publication is claimed by this source patch; release is separately decided.

## Evidence

[Verification](../../../evidence/verify/2026-11-25-mcp-deletion-error-parity.md).
