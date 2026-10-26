# Decision: Verify storage and retained sandbox state with real effects

Status: proposed

## Problem

A Skill description or registered operation cannot prove persistent mounts,
process-memory preservation, Snapshot clone isolation or conversation reuse. The
initial Snapshot test also placed its overwrite marker directly under sticky
`/tmp`; the tested envd image rejects that same SDK overwrite before any Snapshot.

## Decision

Add a standard-client, explicit-owned-fixture OSS acceptance test covering an
exact kernel mount, exclusive fsynced sentinel, sandbox destruction/recreation,
read-only access and typed cleanup. Keep the Snapshot overwrite marker inside an
owned non-sticky directory so Snapshot isolation and the independent envd `/tmp`
overwrite failure have separate evidence. Document the exact opt-in prerequisites
and retain initial failures as well as subsequent real-cloud passes.

The additional local acceptance uses only newly owned buckets, scoped RAM
roles/policies, Volume definitions, tagged sandboxes and Snapshots, with cleanup.
MicroVM mounts require a suitable ossfs2 runtime. The documented append endpoint
is a backend check, not a newly registered Provider operation. LangGraph reuse is
a real framework/cloud boundary check without model execution.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

- Metadata-only Volume creation — cannot prove a mount or persisted data.
- Chmod or root-write workaround in the Snapshot regression — would conceal the
  separate envd behavior and weaken the expected ordinary-user isolation check.
- Selecting an arbitrary existing Volume — unnecessary risk and unrepeatable
  ownership; explicit owned RW/RO fixtures are required.

## Dependencies

The existing standard Python client, pytest suite and cloud credentials. The
opt-in test requires two owned OSS Volume definitions pointing to one dedicated
storage path, in the API key's Team/region, and an eligible runtime. The manual
fixture provisioning additionally used official FC/RAM SDKs and oss2; these are
not added as SDK runtime dependencies.

## Test Strategy

Run the existing real pause/resume and Snapshot tests, the new opt-in OSS test,
and real framework session reuse/isolation. Observe random in-memory service
state across pause and Snapshot restoration. Prove persisted bytes only after
killing the first sandbox and creating a distinct second one. Verify read-only
write rejection, marker ownership and cleanup. Keep full repository checks
separate from these scoped cloud results.

## Acceptance criteria

- Standard Snapshot clone can read retained files and the in-memory service value;
  ordinary-user overwrite changes the clone without changing its source.
- Owned OSS data persists after actual sandbox deletion and recreation; a distinct
  read-only mount can read it and rejects a write.
- Mounted MicroVM pause/resume retains the exact mount, file and process-memory
  service value; required image preparation is recorded.
- Framework conversation reuse and distinct-user isolation use real sandboxes.
- Initial failures, skipped checks, cleanup and unrun repository gates remain
  explicit in the verification evidence.

## Evidence

- [State/storage acceptance](../../../evidence/verify/2026-10-26-skill-storage-state-acceptance.md)
