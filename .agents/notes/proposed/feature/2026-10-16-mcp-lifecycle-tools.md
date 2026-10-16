# Decision: Expose bounded sandbox lifecycle management through Python MCP

Status: proposed

## Problem

MCP callers can create and execute on a sandbox but cannot list existing resources,
refresh safe metadata or explicitly set lifetime through the Python server. Using
execution-tool lookup for inspection would implicitly create, renew or adopt an
external sandbox, allowing session shutdown to destroy a resource it only queried.
Provider failures can also embed credentials in exception URLs and validation input.

## Decision

Reuse existing SDK lifecycle methods and shared MCP schemas/handlers. Add list,
metadata inspection and lifetime tools; extend creation with provider, region,
CPU and memory. Metadata uses a fixed allowlist. External inspection/renewal uses
a temporary client closed in finally, without adopting the instance or changing
the default. Validate arguments before SDK calls. Lifecycle error logs and results
use static categories, safe SDK codes and static recovery guidance.

## API Design

`list_sandboxes(status?, limit=100, offset=0, provider?, region?)` returns a bounded
page of allowlisted metadata. `get_sandbox(sandbox_id?)` refreshes existing metadata;
`set_sandbox_timeout(timeout, sandbox_id?)` updates lifetime from now. Omitted IDs
require an existing default; these operations never create one. Creation additionally
accepts positive integer `cpu` and `memory`, string `region` and `provider`.
Team administration is not exposed because the SDK has no corresponding parameter.

## Alternatives considered

- Reuse execution lookup: rejected because creation, renewal and cleanup adoption
  are inappropriate side effects for metadata reads.
- Serialize complete SDK models or exceptions: rejected because model extras,
  tokens, endpoints, validation inputs and dynamic error suggestions can disclose secrets.
- Add speculative platform endpoints: rejected; use existing SDK APIs only.

## Dependencies

Existing Python SDK and MCP transports; no new dependency or version change.

## Test Strategy

Unit and real HTTP transport tests cover schemas, validation, provider delegation,
state ownership and sensitive success/error values. Real Express E2E exercises
create, get, external inspection/renewal, observer shutdown, files, commands,
list visibility and owned cleanup. Only list visibility retries, following the
existing documented eventual-consistency window.

## Acceptance criteria

Ten Python tools are discoverable on both transports; new metadata never creates
or adopts resources; external instances survive observer shutdown; no configured
secret enters lifecycle failures or logs; real E2E and required repository gates pass.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-mcp-lifecycle-tools.md)
- [SDK issue 31](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/31)

## Implementation

Implemented and real Express handler scenarios pass. Remains proposed while
complete repository gates and full MCP/Skills product scope are outstanding.
