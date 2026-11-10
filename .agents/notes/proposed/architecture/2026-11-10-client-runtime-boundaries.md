# Decision: Separate client installation from local server execution

Status: proposed

## Problem

The Python client installed the local application runtime even when callers only
used standard cloud clients or application HTTP. The module-level `sandbox.run`
also created an implicit code-interpreter sandbox and called a name without
uploading the registered local function, obscuring the deployment boundary.

## Decision

Keep both distributions and their lockstep versions. Move the server dependency
to the client `server` extra and include it in `all` and `dev`. Preserve standard
clients, ProviderSandbox, ServerClient, shared client models, and the real remote
execution decorator. Remove only the factory's legacy run/run_async and private
execution helpers and unconsumed registered-function source capture. Local registration requires the server extra and fails with
installation guidance before storing local metadata if the runtime is missing.

## API Design

- `pip install agent-sandbox-client` installs the client alone in future releases.
- `agent-sandbox-client[server]` selects the exact matching local runtime.
- `@sandbox(...)`, `@sandbox.register`, `sandbox.server` and `list_registered`
  remain distinct operations. Registration does not deploy functions.
- Remove `_SandboxFactory.run` and `run_async`. Use an explicitly selected
  `ServerClient.commands.run` for deployed application commands.
- Instance `ProviderSandbox.run` / `invoke` remain unchanged.

No release version is changed or published in this work.

## Alternatives considered

- Keep the hard dependency: preserves unnecessary coupling and conceals the
  difference between calling a remote application and running its server.
- Remove the real decorator or merge standard/provider clients: independent
  capabilities with observable contracts; outside the simplification scope.
- Keep a compatibility factory forwarding to an arbitrary template: still cannot
  deploy the local registered function and preserves the ambiguity.
- Silently allow registration without a runtime: reports success for an unusable
  command and becomes more common after making the dependency optional.

## Dependencies

Tracking: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/157


The runtime remains a separate namespace distribution with its current exact
version pin. No new library, framework, launcher or cloud resource is introduced.
Release and health checks must enforce optionality rather than the old mandatory
runtime invariant.

## Test Strategy

Run both package suites, lint, type checks, builds, repository health and hygiene.
Inspect actual wheel metadata for base/server/all/dev requirements. Install the
client wheel in an isolated environment outside source directories, assert the
runtime is absent, import all client surfaces and perform a real local HTTP
request. Resolve the server extra only from the locally built wheel and register
a real function. Keep cloud E2E results separate from local distribution checks.

## Acceptance criteria

- Base installation works without a local runtime and calls application HTTP.
- Optional server installation preserves namespace imports and registration.
- Missing-runtime registration is actionable and leaves no partial registration.
- Removed factory execution is absent; existing decorator/instance tests pass.
- Both languages document installation and the explicit invocation boundary.
- Required validation and its limits are recorded before merge.

## Evidence

- [Verification](../../../evidence/verify/2026-11-10-client-runtime-boundaries.md)

## Mainline reconciliation

PR #160 initially had no Actions run because its branch conflicted with the current mainline. GitHub reported `mergeable=false` / `mergeable_state=dirty`; repository Actions and CI/Docs workflows were enabled. The one queued check suite belonged to Cursor, not GitHub Actions.

Merge fixed main `eb7c980a825d804483474923938277700e048571` without rebasing the published branch. Its changes are the preview/community announcement and QR replacement from PR #158/#159. Only the Unreleased changelog insertion conflicts; retain both sides' entries and preserve the README announcements, current QR asset and their historical records. No SDK/runtime/workflow changes are needed for this reconciliation. Parent review accepted this minimal resolution and documentation plus focused packaging validation.

References: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/160 ; https://docs.github.com/en/actions/how-tos/troubleshoot-workflows .
