# Decision: preserve the bound MCP workspace after a failed explicit deletion
Status: proposed

## Problem

The Python MCP manager cleared its workspace registry and default before the
Provider delete call. A pre-request failure was enough to lose the default and
exclude an owned workspace from shutdown. [Issue 169](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/169).

## Decision

Hold the workspace record and the exact bound handle until explicit deletion
succeeds. Serialize explicit deletions with the start of shutdown, and compare
the exact handle when clearing the default. A concurrent create may install a
different default while the Provider request is in progress. Release the
connection after success. Use the existing sanitized lifecycle error path.

## API Design

Tool arguments and results remain unchanged. A failed delete of a cached
workspace leaves its lookup and connection available to the active MCP session
for an explicit retry. An internal Sandbox kill option retains the original
Provider connection on a failed MCP deletion. The public SDK default still
closes that connection after a failed request.

## Alternatives considered

- Removing the record first loses retry and shutdown ownership on failure.
- Reconnecting by raw ID risks using a different Provider or region and can
  require a second transport or a resume operation.
- Automatic retry would disguise an ambiguous Provider response. Explicit
  observation and retry remain with the user or client.

## Dependencies

Existing Python Sandbox lifecycle protocol, bound connection and MCP owner
records. The feature applies to explicit tool deletion while the session is
active. HTTP Session termination and durable cleanup require separate work.

## Test Strategy

Reproduce the missing default before changing the source. Test successful
retry, bare and qualified IDs, a concurrently created default, and Provider
resource use and confirmed absence on a real Express instance.

## Acceptance criteria

- A failed explicit delete retains the handle, default, lifetime, ownership and
  background-task retention data.
- Successful deletion forgets that exact object and keeps any new default.
- An overlapping close does not take a stale ownership snapshot mid-delete.
- Express reports typed not-found after the successful retry.
