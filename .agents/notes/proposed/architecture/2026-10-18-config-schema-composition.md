# Decision: Inject provider schema discovery outside transport
Status: proposed

## Problem

Transport configuration lazily imports the provider registry to discover fields,
violating the documented dependency direction. Discovery must still support
builtin, registered, entry-point and installed providers without eager startup.
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/59

## Decision

Move ProviderSchema values and a typed callback holder to a private low-level
module. The package root registers a lazy adapter that obtains the current
registry provider only when requested. Transport uses the callback; builtin
resolution bypasses discovery. Keep the existing TransportConfig/ProviderSchema
imports, derivation/default/inheritance behavior and provider registration rules.

## API Design

No public signature or configuration schema changes. transport.config.ProviderSchema
explicitly re-exports the same class. The root hook is private; no new plugin
registration API or global discovery/network call is added at import time.

## Alternatives considered

- Keep a lazy upward import: runtime coupling remains hidden.
- Eagerly import the registry at startup: breaks the existing lazy root boundary.
- Require callers to initialize every plugin manually: breaks installed-provider
  and deep configuration imports.

## Dependencies

Accepted native SDK transport is
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/57.
No CLI, registry, website or schema-export consumer change is required:config
names and values are unchanged; source architecture docs aggregate normally.

## Test Strategy

Existing config/provider/conformance suites, fresh-process lazy/builtin import
probe, full client/server quality/package checks and configured real cloud.
Preserve existing source resolution vectors and provider receipts.

## Acceptance criteria

- Transport has no provider registry import and schema class identity is retained.
- Bare import does not load Pydantic/registry; builtin resolution needs no registry.
- All existing selection/source/derive/default/provider behavior remains.
- Required full checks, real component acceptance, docs/changelog/record pass.
