# Decision: Bounded binary files through Python MCP

Status: implemented

## Problem

P0 umbrella Issue 45 requires upload/download beyond text helpers. Existing SDK
file APIs transport bytes, but the Python MCP surface cannot preserve arbitrary
binary artifacts. A Stat-only limit races with modifications and does not bound
special or hostile response streams. File operations also carry existing MCP
session ownership semantics that must not be silently changed.

## Decision

Add `upload_file`/`download_file`, strict standard Base64, a 1 MiB decoded limit,
byte counts and SHA256. No MCP-host paths or credential-bearing file URLs are
accepted. Both transports share the handlers. Validate encoded size before
allocation and reject invalid/unknown arguments before sandbox resolution.
Preserve existing file-tool adoption, TTL renewal and shutdown destruction;
metadata/TTL tools and retained background tasks retain their distinct rules.

## API Design

`upload_file(path, content_base64, sandbox_id?)` overwrites a remote file and
returns success/count/hash. `download_file(path, sandbox_id?)` returns bounded
Base64/count/hash. Failures use static messages and categories without raw
upstream exception output. Tool transfer waits are bounded to 120 seconds;
accepted remote writes are not guaranteed cancelled or atomic.

SDK `files.read_bytes(path, max_bytes=None)` adds an optional streamed limit,
with `FileSizeLimitError` E4003 carrying `limit`. The default remains compatible.
Native create injects the existing direct envd HTTP protocol into the legacy
engine file adapter for explicitly bounded reads; native connect already uses
that data plane. No gRPC schema or platform endpoint is invented. Node-provider
adapters explicitly reject bounded reads until their streaming contract exists,
rather than falling back to an unlimited transfer.

## Alternatives considered

- Text encoding: cannot preserve arbitrary bytes.
- Host-local upload/download paths: expand MCP host filesystem access.
- Stat-only checks: do not bound the actual stream or concurrent modification.
- New Range or guessed provider endpoints: unsupported by verified contracts.
- Silently changing file-tool ownership: breaks the documented public policy.
- Claiming all providers or all P0–P2 complete: outside this narrow slice.

## Dependencies

Existing SDK native envd GET/POST `/files`, httpx streaming, Base64/hashlib,
MCP shared handlers. No new dependency or provider package is added.
[Issue 48](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/48),
[umbrella 45](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/45),
[lifecycle 31](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/31).

## Test Strategy

Exercise maximum-size actual STDIO and HTTP framing with explicit fake file
delegates; stream arbitrary/misreported-length/error/cancelled responses through
the actual httpx client and check closure. Validate Base64 allocation order,
byte equality, hashes, error privacy and adopted-file shutdown semantics.
Execute real Express max-size/empty upload, independent remote sha256sum,
create/connect bounded reads, reconnect, missing and overflow outcomes; verify
owned cleanup. Run complete repository CI-equivalent checks and real-cloud E2E,
recording environment failures and native-provider skips separately.

## Acceptance criteria

- Invalid input is rejected before remote effects; maximum payload fits both transports.
- Streamed limit closes on overflow/error/cancellation and never returns partial success.
- Native create/connect binary bytes and hashes match independent real cloud checks.
- Existing file ownership and background-task retention contracts remain unchanged.
- Current-head CI/review, real-component evidence, bilingual docs and changelog exist.
- Complete P0–P2 Issue 45 remains open; unsupported providers are explicit.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-mcp-binary-files.md)

## Implementation

Implemented source 0832e3526661379e1c5fe839324ff30c339c98bd passed real
Express acceptance, independent review and all nine GitHub checks. The final
records-only head must pass its own required checks before normal PR merge.
This note does not assert a remote merge before that state is confirmed.
