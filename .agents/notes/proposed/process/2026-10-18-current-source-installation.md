# Decision: Make current SDK installation recipes executable
Status: proposed

## Problem

Both0.3.0 PyPI metadata endpoints return404, but current package/root README and
multiple active guides instruct index-only installation. Troubleshooting invokes
a retired root Python version CLI. Websites already use a working source pair.

## Decision

Add a bilingual canonical paired-source guide at accepted native e86cb0b; keep
client/server/extras on the same commit. Update current README/package guides,
examples and install comparison links; preserve archived designs/evidence. Use
metadata imports to inspect installed versions, not a nonexistent root CLI.
Move accepted config composition PR61 note to implemented with current index.
No package publication, runtime source, API or optional provider activation.

## API Design

No code/export/schema/dependency changes. Existing package names and same-version
namespace coupling remain. Source provenance differs from publication state.

## Alternatives considered

- Claim PyPI publication from package names/version: contradicted by metadata404.
- Install only the client source: its exact server dependency still seeks PyPI.
- Delete active namespace compatibility dependency: breaks public consumers.

## Dependencies

Accepted native source: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/57.
Accepted composition: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/61.
Website/registry consumers use the same already-tested source revision; their
hosted403 gate remains separate. Naming changes and package releases excluded.

## Test Strategy

Fresh public archive pair and all extras installation, pip check, actual SDK/MCP
imports/version command; existing health/links/hygiene and required hosted matrix.
The current runtime already has real-cloud116PASS evidence; this documentation
change performs no cloud mutations and does not rerun unrelated model scenarios.

## Acceptance criteria

- Displayed current installation uses a working matched source pair.
- Optional MCP/declarative guidance includes its declared extras.
- Retired version CLI replaced; package publication not asserted.
- Bilingual indexes/records/changelog and required checks pass.
