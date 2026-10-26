# Decision: Share application authentication test vectors

Status: proposed

## Problem

The CLI, Python client and Node HTTP client maintained similar authentication examples independently. User-requested CLI onboarding work must not introduce SDK configuration commands or change the library's input responsibilities.

## Decision

Own a small, language-neutral application authentication fixture under contracts/testing/. Consumers verify the same anonymous, application-token and case-insensitive gateway-header cases. Python continues to accept its existing parameters, environment/dotenv and configuration inputs. No runtime API, cloud behavior or package version changes.

## API Design

N/A — additive test vectors and tests only. The fixture contains a version and cases with headers, optional token and expected lowercase header names. All values are placeholders.

## Alternatives considered

- Share runtime code across languages: unnecessary and couples independent distributions.
- Add SDK setup commands: outside this library's role.

## Dependencies

Existing ServerClient and pytest. Consumer follow-up: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/189.

## Test Strategy

Run the fixture and application-binding tests, both package test suites, repository checks and CI. Consumers pin the reviewed source revision rather than requiring sibling checkouts.

## Acceptance criteria

- All consumers run byte-identical vectors.
- Gateway credentials remain separate from explicitly supplied application credentials.
- No SDK configuration command, prompting behavior or public export is added.
- Owner evidence distinguishes fixture checks from cloud acceptance.

## Evidence

- [Verification](../../../evidence/verify/2026-10-26-application-auth-vectors.md).
