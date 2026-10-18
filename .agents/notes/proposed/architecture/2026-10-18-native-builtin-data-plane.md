# Decision: Retire the builtin Python gRPC session bridge
Status: proposed

## Problem

Builtin create and data operations retain a process-local gRPC session while
connect already supports native HTTP protocols. This duplicates lifecycle,
loses platform response fields and adds grpcio/protobuf runtime dependencies.
Issue35 reports a held handle disappearing during background installation;
its exact original root cause is not established.
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/35

## Decision

Use SandboxProtocol, ProcessProtocol and FilesystemProtocol for builtin create,
as already used by connect. Preserve all create options, response metadata,
request timeout/TTL separation and envd-version stream framing. Remove the old
engine source/generated bindings, session flags, fallback routes and dedicated
legacy tests. Keep installed Node/EPP providers and their engine unchanged.

## API Design

Public Sandbox operations retain their signatures. Experimental deep Engine
imports, module command and ABX_ENGINE_SOCKET are retired; migration uses
Sandbox.create/connect and public data APIs. close retains remote ownership;
kill remains idempotent. No implicit remote mutation retry is introduced.

## Alternatives considered

- Keep two builtin transports: duplicate state and dependency burden remains.
- Extend the legacy daemon with persistence: duplicates the native addressable
  platform ID and expands lifecycle/serialization/security maintenance.

## Dependencies

Shared auth contract: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/56.
Node engine remains owned by https://github.com/Alibaba-Agent-Sandbox/agent-sandbox.
No registry feature or provider badge changes.

## Test Strategy

Compare the original focused baseline, test both envd generations and full
create payload/response, binary bounds, cleanup, all client tests, packaging
without grpc/protobuf, and configured real-cloud lifecycle/background polling
from independent handles. Record exact results and remaining hosted gates.

## Acceptance criteria

- No builtin import/call requires the retired Python engine.
- Metadata/resources/options/framing and public APIs remain correct.
- Background work remains observable from held and independent live handles.
- Full required checks, bilingual docs/changelog/record and cleanup pass.

## Evidence

[Verification](../../../evidence/verify/2026-10-18-native-builtin-data-plane.md).
