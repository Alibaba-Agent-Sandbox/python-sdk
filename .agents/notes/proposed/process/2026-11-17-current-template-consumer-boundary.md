# Decision: State the actual SDK named-resource consumer boundary

Status: proposed

## Problem

The contributor entry described an earlier single-Sandbox draft as the current YAML
contract. The template owner now defines named Sandbox/Serving resources, but this
SDK's packaged normalizer and public launch convenience still consume the older
shape. Rewording documentation must not claim an unimplemented consumer migration.

## Decision

Correct AGENTS.md to identify the current owner contract and the actual working
runtime paths: generated run.py uses prepared references and ProviderSandbox, while
managed roles consume explicit private configuration. Mark the older YAML consumer
as an unresolved migration, including its use by private instance validation.
A schema-byte synchronization alone is unsafe; migrate consumers and tests together.
Update the paired user guides/reference/design descriptions to the same actual boundary,
remove current-source examples using obsolete service/instance wrappers, and preserve
the independent prepared SDK API. This documentation increment does not close the
remaining consumer criteria in the template owner Issue309.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

- **Claim named-resource support after editing the entry point** — rejected because
  neither the normalizer nor launcher currently consumes that resource shape.
- **Replace only schema files** — rejected because launch and managed instance
  validation still construct and consume the earlier shape.
- **Expand this wording fix into another deployment engine** — rejected because the
  new template runners and managed backend already use explicit runtime APIs.

## Dependencies

The template owner defines current configuration:
https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/311.
The SDK's local immutable source lock identifies the earlier consumer contract.

## Test Strategy

Trace imports/callers in SDK, template runners and CLI; check that the contributor
entry matches those paths. Run repository record/link/hygiene checks. This documentation
correction does not establish new YAML, cloud or model support.

## Acceptance criteria

- AGENTS.md describes named resources without claiming the old SDK parser accepts them.
- The functioning explicit-runtime paths and remaining migration are clear.
- The owning YAML migration Issue remains open until actual consumer criteria land.

## Evidence

- [Verification](../../../evidence/verify/2026-11-17-current-template-consumer-boundary.md).
