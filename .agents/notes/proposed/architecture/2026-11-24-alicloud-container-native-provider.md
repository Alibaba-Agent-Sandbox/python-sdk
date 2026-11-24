# Decision: Bundle the Alibaba Cloud Container Edition Python Provider

Status: proposed

## Problem

Python applications using an ACS or ACK sandbox-manager currently use the Node plugin through the local abx engine. The cluster offers a direct HTTP control plane and E2B-shaped data plane. The client should be able to operate existing SandboxSets without installing a second local runtime.

## Decision

Ship `alicloud-container` in the Client SDK wheel and select it by ID. Bound preparation resolves the shipped Provider directly and matches the lock version before selecting other approved artifacts. Keep the default Express target. The abx catalog plugin continues to own its Node execution and SandboxSet preparation. The Python plugin installation verifier checks the artifact it was asked to install, even where an SDK Provider also has that ID.

Reuse the existing HTTP, Connect process and file implementations. Keep account configuration, routing, lifecycle request shapes and the Jupyter endpoint in the Container Edition adapter. Scope the management key to the control plane. Derive all data URLs from the configured cluster gateway. An existing SandboxSet supplies the base compute configuration.

## API Design

- `ProviderSandbox.create(provider="alicloud-container", template="code-interpreter")` reads provider-scoped settings from the usual Client SDK configuration sources.
- `ProviderClient.prepare(lock, TransportConfig(...))` binds the shipped version using explicit provider options.
- Methods cover lifecycle, timeout, process and file operations, port resolution and the Jupyter default context. `connect` may resume or extend a lease. List returns one page.
- Jupyter execution checks the completion event emitted by the public `/execute` response wrapper. A response without that event raises a protocol error.
- Sandbox creation can be inconclusive after an upstream transport failure or gateway 5xx. `on_created` records IDs from valid receipts. Reconcile uncertain creation in the cluster before a new request.

## Alternatives considered

- Keep the Node bridge for Python. It preserves one host implementation but adds a separate process and runtime for a backend already within the SDK's HTTP capabilities.
- Add the Container gateway to the standard Express client. The management credentials, private data routing, connect and code contracts differ.
- Use a declarative REST preset. The preset cannot express the versioned connect behavior, path routing and Jupyter protocol.

## Dependencies

[Alibaba Cloud Container Edition guide](https://help.aliyun.com/zh/agent-sandbox/quick-start1/), [OpenKruise lifecycle](https://github.com/openkruise/agents/blob/25106aaaf6a73770b1ae1ee2cc0a06d6610cf279/pkg/servers/e2b/pause_resume.go), [OpenKruise v0.6.0 route table](https://github.com/openkruise/agents/blob/a1e0811323b71fd9a54efe26b0f4baf19106c84e/pkg/servers/e2b/routes.go), [OpenKruise listing](https://github.com/openkruise/agents/blob/25106aaaf6a73770b1ae1ee2cc0a06d6610cf279/pkg/servers/e2b/list.go) and [Jupyter response producer](https://github.com/e2b-dev/code-interpreter/blob/db9fdb1cfe6552455d58b1690971bdd3052538c6/template/server/messaging.py). Shares bound-client infrastructure with [PR #167](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/167).

## Test Strategy

Validate both gateway layouts using the real SDK HTTP client with a controlled HTTP contract. Exercise management and data-plane authentication, v2 and v1 connect, list state, file transfers, Jupyter NDJSON, process exits, identity checks and ambiguous creates. Run the basic live case against a maintainer-provided ACS or ACK cluster and confirm deletion by ID. Run the separate interpreter case with a SandboxSet that exposes the Jupyter service.

## Acceptance criteria

The client wheel contains the Provider and requires no Node runtime. Both public Python entry points use it without starting the engine. The cluster test proves real commands, files, interpreter results and owned sandbox cleanup. Keep live acceptance open until a cluster with a suitable SandboxSet and credential is available.

## Evidence

- [Implementation and two-round review evidence](../../../evidence/verify/2026-11-24-alicloud-container-native-provider.md)
- [Follow-up review and verification evidence](../../../evidence/verify/2026-11-24-alicloud-container-native-provider-recheck.md)
