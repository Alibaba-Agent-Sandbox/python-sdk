# Decision: Honor the native envd process OS user

Status: proposed

## Problem

Issue [83](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/83) records that
`ProviderSandbox.commands.run(user="root")` returns UID 1000 on Express base while
the standard `AsyncSandbox` handle for the same sandbox returns UID 0. The native
adapter put `user` into a process protobuf object that does not define that field.
The request still authenticated as the default envd Basic principal.

## Decision

For a nonempty process user, send a per-request Basic Authorization header for
that OS account through the existing `HttpClient.envd_stream(headers=...)` hook.
Remove the unsupported process JSON field. Do not mutate the shared token manager
or change gateway access tokens, sandbox-routing headers, transport interfaces,
standard clients, other provider adapters or application-server authentication.
An empty user keeps existing configured/default principal behavior. Reject colon,
NUL and line breaks before I/O because they cannot name the requested Basic principal
without ambiguity. Keep missing-account backend errors visible.

Prepare client and server 0.3.1a2 together, retaining the client's exact server
dependency. Publication remains a separate release operation after acceptance.

## API Design

No callable signature changes. Native `commands.run`, `commands.start` and
`commands.stream` retain their existing `user: str = ""` parameter. Explicit users
now select the actual account instead of being ignored. Standard clients and
provider-specific exec/engine process payloads remain unchanged.

## Alternatives considered

- Mutating `EnvdTokenManager._basic_user` would leak identity across concurrent
  operations and was rejected.
- Adding an OS-user capability system or changing provider registration is not
  needed to correct an existing envd protocol field.
- Silently falling back to the default user would preserve the defect.

## Dependencies

Existing shared E2B/envd adapter, `HttpClient.envd_stream` request headers, and
Python's standard-library Base64 encoder. No new dependency.

## Test Strategy

Wire-level regressions exercise the real HTTP client with a mocked HTTP endpoint:
concurrent root/user/default requests, configured default identity, unchanged
gateway/routing headers, no unsupported user field and no shared-state mutation.
Invalid Basic principals fail before I/O. Real Express tests compare native and
standard callers on the same owned sandbox, verify start and nonexistent-user
behavior, then kill and query the exact owned identity independently.

## Acceptance criteria

- Native root/user UID matches the standard caller on the same real target.
- Default identity survives explicit and concurrent user requests.
- A nonexistent OS user raises a backend error, never default execution.
- Relevant regressions, mandatory CI and real non-slow E2E are recorded accurately.
- English/Chinese guidance, paired version metadata and scoped cleanup evidence
  accompany the normal reviewed PR; no release is inferred from local version files.

## Evidence

- [Verification](../../../evidence/verify/2026-10-24-native-process-user.md)
