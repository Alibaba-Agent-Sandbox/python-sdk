# Decision: Preserve application tokens through filtering proxies

Status: proposed

## Problem

OpenSandbox 1.1.1 removes Authorization when proxying application traffic. A real same-sandbox probe returned 200 for direct Bearer, 401 for proxy Bearer and 200 for proxy X-Access-Token. The server already accepts the latter header, but ServerClient only sends Bearer.

## Decision

Keep Bearer and also send the explicit application token through the existing X-Access-Token header when unused. Never replace a case-insensitively matching gateway header, including defaults owned by an injected HTTP client. Derive the headers per request without mutating saved configuration, so token rotation and removal cannot retain an old generated credential.

## API Design

No new API, configuration, authentication protocol or provider special case. ServerClient.auth_headers() retains its public return type and uses existing server authentication. Server runtime behavior is unchanged; both distributions advance together to 0.3.1a4 as required by their lockstep contract.

## Alternatives considered

- Disable server authentication or silently choose a different endpoint: changes the requested security or network behavior.
- Add a new authentication header or provider option: unnecessary because the server already accepts X-Access-Token.
- Replace a gateway's occupied header: would lose a separate credential.

## Dependencies

Existing ServerClient, httpx and SandboxServer authentication. Coordinated CLI and Node.js consumers use the same existing header convention.

## Test Strategy

Exercise proxy filtering and Bearer-only services, explicit and injected gateway headers with mixed casing, borrowed HTTP client ownership, token rotation/removal, and existing redirect refusal. Run the full CI matrix and a real proxy application_client test through the unchanged OpenSandbox server.

## Acceptance criteria

- A filtering proxy can authenticate application requests with the existing server token header.
- Existing gateway headers, Bearer compatibility and redirect refusal remain intact.
- Token rotation/removal cannot retain a generated previous token.
- Real proxy verification, bilingual usage documentation and matching distributions accompany the change.

## Evidence

- [Issue #99](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/99)
- [Provider investigation](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/issues/31)
- [Verification](../../../evidence/verify/2026-10-24-application-proxy-token.md)
