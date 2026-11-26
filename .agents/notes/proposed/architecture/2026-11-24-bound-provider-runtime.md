# Decision: Prepare explicitly bound Provider implementations

Status: proposed

## Problem

Python's existing installed Node Provider path uses the user's shared abx engine. It also
resolves several sandbox behaviors from the global Provider registry after creating a handle.
An application that uses a single standalone Provider should be able to bind its own target
and prepare only the executable artifacts needed by that implementation.

## Decision

Use an explicitly supplied, already installed Python Provider when it meets the required feature
set. Otherwise select a standalone EPP entry from an operator-approved release lock. Filter
platform and feature requirements before opening any artifact, prefer the host language, then use
the documented priority. Preflight of the selected implementation terminates on failure. The
approved lock binds opaque compressed bytes to their source, digest, size, and archive member.
The host retrieves public HTTPS archives only during explicit online preparation and reuses
verified private cache blobs offline.

Reuse the EPP transport and its operation contract. Give each bound Sandbox handle its own
transport because EPP/1 process notifications identify a process without its Sandbox ID. Share
only verified artifacts and the account configuration within a client. Each handle receives its
negotiated Provider object for endpoint resolution, refresh and terminal calls. Close tasks own
local cleanup, including cancellation of a caller waiting for close. Remote deletion is explicit.

The dependency-free OpenSandbox plugin is the first standalone Node example. The source
fixture pins the existing published Provider and official Node archives. The built-in Express
route uses an explicit Sandbox key and endpoint without account discovery. The current Node CLI
continues to load compatible installed Node modules through its existing ProviderKit.

## API Design

- `ProviderClient.prepare(ProviderLock, TransportConfig, native=..., required_features=..., cache_dir=..., download=False)`
- `create(SandboxConfig, request_timeout=..., on_created=...)`, `connect`, `list`, `get`,
  `set_timeout`, `delete`, `close`, and async context management
- `ProviderLock` fixes a release and its approved standalone implementations. Each
  `EppImplementation` declares language, platform, priority, features, entrypoint and artifact,
  with an optional `ProviderRuntime` and required target keys.
- Public usage and prerequisites are in [the English guide](../../../../docs/en/guide/provider-runtime.md)
  and [the Chinese guide](../../../../docs/zh/guide/provider-runtime.md).

## Alternatives considered

- Bundling the abx executable or interpreters into the SDK would charge direct HTTP callers
  for unrelated assets and would retain CLI configuration and subprocess discovery coupling.
- Reusing the ambient catalog index as a trust root would let bytes and the expected hash
  change together. Start with an independently approved lock. A signed multi-implementation
  publishing workflow is a separate milestone.
- Sharing the EPP process between Sandbox handles can route notifications to the wrong
  stream when two backends reuse a bare process ID. Retain per-handle isolation.

## Dependencies

Use the installed Python package dependencies, existing EPP/1 protocol and fixed Node and
OpenSandbox distributions. No interpreter or Provider binary is included in the SDK wheel.
The example host is Linux x86-64 with glibc. Native packages are installed by the application
owner. Additional platforms, native package auto-installation and catalog release automation
require their own published artifacts and acceptance.

## Test Strategy

Review separate native binding, artifact verification and Node operation boundaries. Run an
explicit Express cloud lifecycle with command and file round-trip and confirmed cleanup. Run the
published Node and OpenSandbox artifacts against the exact protocol with system Node masked,
using cold, warm and offline preparation. Exercise same-ID concurrent streams and cancellation
during process startup and shutdown. A live OpenSandbox deployment is a separate acceptance gate
from the protocol backend test.

## Acceptance criteria

1. Required features and explicit target are checked before dispatch. Native use makes no
   Provider artifact request. Cross-language launch uses the exact verified interpreter/entry.
2. Normal and cancelled shutdown reaps owned local processes. Closing one handle leaves siblings
   usable. After client close, a stale handle cannot reuse HttpClient or the EPP process.
3. Asset mismatch fails closed. Cache readers see a complete verified blob. Offline preparation
   never opens the artifact network connection.
4. The supported backend, operation and platform set in the public guides follows real evidence.
   Record missing gates distinctly before making release claims.

## Evidence

- [Delivery issue #166](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/166)
- [Verification and review results](../../../evidence/verify/2026-11-24-bound-provider-runtime.md)
