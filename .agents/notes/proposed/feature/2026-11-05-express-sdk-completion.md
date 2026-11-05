# Decision: Complete Express session and application command interfaces

Status: proposed

## Problem

Express's standard client already supports the main E2B runtime surface, but the typed
provider client rejects pause/resume, loses the independent public-traffic credential and
cannot pass explicit network creation settings. Application command keywords conflict
with transport options, and STS identities lose their SecurityToken when forwarded to the
shared management engine. The preceding audit was challenged by three independent agents
before implementation. Refs https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/152.

## Decision

Keep standard and provider client responsibilities distinct. Implement the documented
Express pause/connect behavior in an Express-owned protocol adapter, with returned session
information rebinding the existing object's credentials, URL and cached modules. Keep
ProviderSandbox.connect read-only and never acquire credentials through an implicit
application-client reconnect. Retain traffic credentials in memory, exclude them from
default serialization and allow explicit attachment/client overrides.

Add an explicit application invocation method without changing any existing run keyword.
Add supported provider network creation inputs and the Python-owned STS configuration key.
Resource-management and runtime extension commands continue to use the existing shared
engine client; Python does not duplicate the native management API implementation.

## API Design

- `ServerClient.commands.invoke(name, arguments, /, *, request_timeout=None)` and
  `ProviderSandbox.invoke(name, arguments, /, *, server_port=9000, application_token=None, request_timeout=None)`,
  with matching `invoke_sync` helpers. Existing run keyword semantics remain unchanged.
- `ProviderSandbox.create(..., network=None, allow_internet_access=None)` supports the
  declared Express network creation fields. Unsupported providers fail before I/O.
- `ProviderSandbox.connect(..., traffic_access_token=None)` and
  `application_client(..., traffic_access_token=None)` accept independent gateway credentials.
  The latter override affects only that client.
- Provider lifecycle methods accepting cloud AccessKeys also accept `security_token`.
  Its only environment name is `ALIBABA_CLOUD_SECURITY_TOKEN`; it is a secret credential.
- `SandboxProtocol.resume()` may return `SandboxInfo` or None. Existing providers returning
  None retain their behavior. Express returns new session information through documented
  POST connect and uses a 300-second lifetime, preserving the existing no-argument API.

## Alternatives considered

- **Add arguments as a run keyword** — rejected because it steals a currently valid business
  argument. A new invoke method creates an unambiguous boundary.
- **Change attach to POST connect or reconnect inside application_client** — rejected because
  that silently resumes a sandbox or renews its lifetime.
- **Only enable the pause operation gate** — rejected because the old generic adapter uses
  a stale resume route and does not rebind rotated credentials.
- **Return live credentials through generic provider commands** — rejected because command
  results are routinely printed; session credentials stay in the typed session path.
- **Add a second complete cloud SDK or restore configuration aliases** — rejected because
  cloud mappings already belong to the shared engine and each current key has one env name.

## Dependencies

The configuration registry in `utils/config_keys.py` owns the JSON export consumed by CLI
and Node. Consumers synchronize that schema before using new credentials. New runtime
commands need a compatible abx installation and remain provider-declared operations.
The Node application's matching HTTP invocation work is tracked at
https://github.com/Alibaba-Agent-Sandbox/nodejs-sdk/issues/23. Native cloud mapping belongs
to https://github.com/Alibaba-Agent-Sandbox/agent-sandbox.

## Test Strategy

Add failing regressions for STS resolution/handoff, invocation field collisions, traffic
credential retention and headers, explicit attach without POST, network request fields,
typed pause/connect routes and same-object session rebinding. Exercise invoke against the
real local SandboxServer. Run client/server required checks and record local environment
failures separately from remote CI and real Express acceptance. Cloud mutations and owned
cleanup are coordinated by the root task, not silently triggered by these unit tests.

## Acceptance criteria

- All explicit business fields reach the server while HTTP options stay separate; old run
  calls preserve their meaning and command errors retain their typed mapping.
- STS uses the complete triplet in the shared engine and the official single environment
  name, with no unrelated provider inheritance or plaintext display.
- Create, attach, refresh and resume preserve the correct independent credentials; no
  application operation performs an implicit cloud lifecycle mutation.
- After actual pause/resume the same provider object can execute commands and read/write
  files with refreshed credentials and addressing.
- Network inputs preserve explicit false/empty values and require secure envd for private
  public traffic; unsupported providers reject them before construction.
- Required local checks, real-component verification, bilingual documentation and independent
  review are complete before this decision moves to implemented.

## Evidence

- [Verification](../../../evidence/verify/2026-11-05-express-sdk-completion.md).
