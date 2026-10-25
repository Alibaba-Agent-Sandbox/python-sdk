# Decision: Use current public SDK contracts in maintained guides
Status: proposed

## Problem

Maintained guides still installed a retired Git archive or older alpha packages,
published decorator/MCP keyword names absent from current signatures, mixed MCP
credentials with the standard E2B entry, and described the removed local Python
gRPC engine. The Express quickstart bypassed the current template launcher.

## Decision

Use public paired 0.4.0a2 installations, canonical sandbox_* configuration and
explicit root ProviderSandbox imports for provider-extension examples. Preserve
valid native synchronous wrappers and genuine third-party provider options.
Use the single template launcher for application startup, with application tokens
separate from platform credentials. Keep standard-client migration documentation
separate and preserve historical design/evidence files that are labeled retired.

## API Design

No new API, alias, compatibility path or version is introduced. Correct the
maintained guides to match the actual published decorator and MCP signatures.
The beginner tutorial uses base command/file operations; it does not claim an
unimplemented Express ProviderSandbox interpreter operation.

## Alternatives considered

Keeping old examples with fallback aliases conflicts with the requested cleanup.
Replacing every api_key or domain occurrence would corrupt valid external SDK and
provider-option contracts. Rewriting historical engineering receipts would destroy
the distinction between previously tested and current behavior.

## Dependencies

Official PyPI paired packages and the separately maintained CLI template launcher.

## Test Strategy

Execute complete English and Chinese beginner scripts extracted from the actual
pages using fresh public packages, assert command/file transfer behavior and
independently verify owned sandbox absence. Inspect actual public signatures and
run the documented MCP HTTP app health/auth locally. Run document, link, health
and hygiene checks. Record the broader public example rerun separately and honestly.

## Acceptance criteria

- Maintained installations and first-party examples use current public contracts.
- Both beginner scripts pass with real Express resources and no leaked sandboxes.
- MCP/decorator parameters match public a2; HTTP app health/auth work locally.
- The independent browser cold-install failure remains recorded, not hidden or
  treated as a passing example; Issue 111 remains open until its full criteria pass.

## Evidence

- [Verification](../../../evidence/verify/2026-10-25-public-sdk-documentation.md)
- [Example cleanup Issue 111](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/111)
