# Decision: Keep borrowed MCP connections out of shutdown deletion

Status: proposed

## Problem

Real hosted Streamable HTTP acceptance reproduced a destructive ownership bug:
[Issue #139](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/139) tracks the defect.
Session A created a sandbox, session B used its explicit ID with the same account
authority, then deleting B killed A's sandbox. Cached handles did not distinguish
creation ownership from a borrowed connection. Public 0.4.0a6 has this behavior.

## Decision

Track manager-created IDs separately from cached handles. Add ownership only
after successful creation. On shutdown, kill only manager-owned instances;
close borrowed connections and explicitly retained background-task handles.
Use provider-qualified IDs for cache, creation ownership, TTL and retained tasks;
an alias reuses an existing canonical handle instead of replacing it. Bare IDs
are accepted only when unambiguous. Mark a manager closed at shutdown. A create
completing afterwards deletes its newly owned instance; a late borrowed connect
only closes its client handle. Neither can repopulate the terminated session.
Remove creation ownership during explicit kill and shutdown. Explicit authorized
`kill_sandbox` remains destructive for both owned and borrowed IDs.

Update binary-file and MCP lifecycle documentation in both languages to describe
this source correction and distinguish it from public 0.4.0a6. Tests using a
manually constructed owned manager must mark that ownership explicitly.

## API Design

No public signatures or MCP tools are added. `SandboxManager` gains private
provider-qualified ownership keys and closed-session guards. Background-task
handles now return the actual `provider:id`; this output representation changes,
so clients must return the complete opaque handle rather than parse a raw ID.
Historical unqualified references remain usable within the documented unique
cache/default-provider scope. This is a cleanup-ownership boundary, not tenant authorization;
sessions sharing account credentials retain the same explicit-access authority.

## Alternatives considered

- Kill every cached handle — reproduced the cross-session deletion.
- Reject every explicit external ID — removes legitimate same-authority access.
- Close every handle without deleting owned sandboxes — leaks resources and
  changes ordinary synchronous-session cleanup.

## Dependencies

The existing Python MCP manager, ProviderSandbox close/kill behavior, STDIO and
Streamable HTTP session finalizers. No new runtime dependencies are introduced.

## Test Strategy

Independent adversarial review reproduced cross-provider raw-ID collision and
create/connect completion races after the first ownership patch. Six regressions
fail before the namespace/lifecycle correction and pass afterwards. Three further
task regressions cover cached non-default-provider reuse, ambiguous bare-ID
refusal, late-connect submission, and provider-preserving reconnect handles.

A two-manager regression must fail on the old implementation: borrower shutdown
closes the borrowed handle without killing it, the owner stays usable, then owner
shutdown kills its own creation. Preserve explicit borrowed-kill behavior, binary
file tools, retained background tasks and full existing MCP tests. Build private
source wheels for real hosted HTTP revalidation; public 0.4.0a6 is not relabeled
as fixed by those private test artifacts.

## Acceptance criteria

- Borrower close/HTTP DELETE never implicitly kills another manager's creation.
- Owner cleanup, explicit borrowed kill and retained-task cleanup remain correct.
- Identical raw IDs from separate providers cannot change ownership, and aliases
  cannot replace the original owned handle.
- Lifecycle work completing after shutdown is cleaned up without registering state.
- Regression fails before the change and passes afterwards.
- Hosted real-cloud regression, repository checks, bilingual documentation and
  sanitized cleanup evidence are recorded before completion is claimed.

## Evidence

- [State/storage and local regression evidence](../../../evidence/verify/2026-10-26-skill-storage-state-acceptance.md)

## Explicit resource verification

[Issue #140](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/140)
tracks a separate creation acceptance defect found in the same campaign. MCP
accepted explicit CPU/memory overrides without reading their actual values.
The new resource helper refreshes platform metadata, rejects unknown or mismatched
values, rolls back only the new provider-qualified resource, and independently
checks absence even if the deletion response failed. A non-confirmed deletion
retains a recovery handle. Direct SDK creation remains unchanged. Four regression
scenarios (five parametrized cases) failed before the helper and pass afterwards.
Real base-template acceptance observes 2 CPU / 2048 MiB: a requested 3 / 2304 was
previously reported successful, then the corrected handler rejects and deletes
only the new sandbox; the matching request succeeds and an existing sandbox
continues executing. All four campaign sandboxes have independent not-found
readbacks. This correction adds no dependencies or tool names.

Independent red-team review found that the first resource helper's cleanup read
lost per-create regional endpoint context after removing the cached handle. A
wrong-region 404 could falsely confirm deletion. The final helper freezes the
created instance's resolved TransportConfig, builds a fresh infrastructure using
the actual provider, reads the exact raw sandbox ID, and closes that fresh client.
Only get_info's not-found is evidence of absence; infrastructure setup/close
failures remain unknown with a recovery handle. The regional routing regression
failed before correction. Separate setup/query/close tests enforce that boundary.
The final affected unit suite passes 279 cases; maintained real lifecycle/resource/
task acceptance passes 5. The real matching/mismatch campaign was repeated after
this correction, including independent absence of all four newly owned resources.

Final parent/independent review extended the same identity boundary across both
resource verification and rollback. Metadata awaits can overlap session shutdown
or replacement of a cached handle. Two rollback regressions failed before the
correction (missing cache selected the default endpoint; replacement selected a
different handle). Two initial-verification regressions also failed when a
replacement/default-endpoint read happened to report the requested resources.
The final helper reads only the captured new handle's refresh_info, removes local
entries only while that exact object still owns them, and kills only that captured
handle. It never resolves the rollback by ID through the manager. Cleanup still
uses the frozen control-plane configuration and independent target get_info.
The resulting affected suite passes 283 cases; all original before-fail cases
remain documented. This does not expand the contract to hostile host code
replacing the provider registry implementation while the server is running.
