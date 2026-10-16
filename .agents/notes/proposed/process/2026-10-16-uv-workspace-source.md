# Decision: Resolve the SDK runtime from its uv workspace member

Status: proposed

## Problem

The client requires the server distribution at the matching release version. The
root declares both distributions as uv workspace members, but does not declare
the dependency source. A normal editable install with uv fails while parsing the
client dependency metadata, before contributors can run local SDK checks.

## Decision

Declare `agent-sandbox-server = { workspace = true }` in the root
`[tool.uv.sources]` table. Keep the published client's exact server version pin
and both package build configurations unchanged. Document the editable uv install
alongside the existing pip workflow.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

- **Require `--no-sources`** — hides the workspace configuration problem and
  prevents the intended local workspace dependency resolution.
- **Publish a path dependency** — would make installed distributions depend on
  a contributor's checkout layout.

## Dependencies

uv for the workspace workflow; Hatchling remains the build backend. The offline
packaging regression skips if uv or the repository workspace is unavailable.

## Test Strategy

Run the original two-package editable uv install without `--no-sources`. Exercise
the real uv metadata parser in an offline dry run; verify a temporary workspace
without the source mapping fails. Build both packages, inspect published metadata,
and run the repository test, lint, type-check and health targets. Record real-cloud
verification separately rather than inferring it from packaging checks.

## Acceptance criteria

- Both editable SDK packages install together with uv without a source override.
- Both packages build and the client wheel retains its exact server version pin.
- The regression passes on the fixed workspace and fails without the mapping.
- Repository gates and required cloud E2E results are recorded honestly.

## Implementation

The local packaging fix is implemented. Keep this decision proposed until the
repository's remaining test and real-cloud verification requirements are resolved.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-uv-workspace-source.md)
- [SDK issue 28](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/28)
