# Decision: Align buffered file upload limits and accept empty files

Status: proposed

## Problem

The upload handler rejects a valid zero-byte base64 payload. Its advertised decoded
limit defaults to 100 MiB, but the shared 10 MiB JSON request limit rejects an
8 MiB file before the handler runs. Obviously oversized base64 is decoded before
its size is checked, creating an avoidable second large allocation.

## Decision

Keep the existing JSON/base64 protocol. Accept the empty string while continuing
to reject missing, null and non-string content. For `files_upload_stream` only,
derive the fallback body budget from the effective decoded `max_bytes` (or
`ABX_MAX_UPLOAD_SIZE`) plus 64 KiB of JSON envelope space. Explicit policy
`max_request_bytes` retains priority; other routes keep their 10 MiB default.
Reject base64 longer than the largest permitted encoded payload before decoding,
and retain strict validation and the exact decoded-byte check after decoding.
Keep path, extension, authorization and overwrite checks intact. Clarify the
buffered transfer format and replace the expired README release forecast.

## API Design

The public path, JSON fields and success response stay unchanged. An explicit
`content_base64: ""` creates or truncates a zero-byte file under the existing write
policy. The decoded-file limit and HTTP-envelope limit remain independent. A
request over either limit remains `413` with `payload_too_large` and `limit`.

## Alternatives considered

- Raise the global body cap: rejected because unrelated endpoints do not need the
  larger file budget.
- Add multipart or a new streaming protocol: deferred as an independent contract
  change. This patch does not remove buffering or establish a fixed memory bound
  independent of configured file size.
- Remove the decoded limit or explicit body cap: rejected because both protect
  different parts of request handling.

## Dependencies

Existing standard-library HTTP server, policy context and base64 codec. No new
runtime dependency or package release is introduced.

## Test Strategy

New real HTTP/filesystem regressions cover empty and 8 MiB upload/download,
missing/invalid content without overwriting existing data, encoded rejection
before decoding, padding-boundary decoded sizes, policy precedence and the
unchanged body cap on other endpoints. Client tests call discovery before the
empty and 8 MiB round-trip. Run the full suites for both packages, lint,
format/type checks, distribution checks and repository health checks. Real-cloud
candidate runtime and owned-resource cleanup are tracked separately in evidence.

## Acceptance criteria

- Empty and 8 MiB files round-trip through the candidate server and Client SDK.
- Invalid or oversized payloads leave no successful file update; explicit request
  caps, decoded caps and existing authorization/path/overwrite rules still apply.
- Other routes retain the 10 MiB fallback; no streaming claim is added.
- Required local and remote gates, bilingual docs and the changelog are recorded.
- Real-component cloud verification identifies the candidate runtime and confirms
  owned sandbox deletion before completion is claimed.

## Evidence

- [Issue #171](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/171).
- [Verification](../../../evidence/verify/2026-11-25-bounded-file-uploads.md).
