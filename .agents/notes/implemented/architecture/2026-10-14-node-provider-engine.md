# Decision: Python reaches node-kind providers through the Node engine

Status: implemented
Implemented: 2026-10-14

## Problem

Catalog providers are implemented once, as Node ES modules. The Python SDK still has to call them, and the default built-in provider must keep working when Node is absent.

## Decision

The Python SDK reaches `node`-kind providers through the local Node engine (`abx-engine/1`), not by loading `provider.mjs` itself.

`python-sdk/client-sdk/src/agent_sandbox/providers/registry.py` returns `EngineProvider` when `manifest.kind == "node"`. `EngineProvider` (`engine_provider.py`) and `engine_client.py` talk HTTP/JSON, SSE and WebSocket to the engine that `abx provider engine serve` publishes in `~/.abx/engine.json`. Sandbox URLs on that path use the marker `engine://{provider}/{id}`. `discover` holds one start lock per event loop, and `EngineClient.request` retries once after the engine restarts.

`rest` and `exec` manifests stay in-process (`RestProvider`, `ExecProvider`). The default `alicloud-express` provider is `builtin.py` and does not start Node.

The earlier Python gRPC engine (`python-sdk/client-sdk/src/agent_sandbox/engine/`, `engine.proto`, Unix socket `~/.abx/engine.sock`, protocol `abx.engine.v1`) is superseded for catalog providers. It still serves the built-in `alicloud-express` path.

The architecture record for the host, the kit, the engine and the decision not to use gRPC as the SDK transport is the CLI ADR [2026-10-14-node-provider-engine](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/notes/implemented/architecture/2026-10-14-node-provider-engine.md).

## API Design

```python
# python-sdk/client-sdk/src/agent_sandbox/providers/engine_provider.py
class EngineProvider(Provider):
    kind = "node"
    def connection(self, config: TransportConfig) -> dict[str, Any]: ...
    async def build_infra(self, config: TransportConfig) -> ProviderInfra: ...
```

`envd_url` for a sandbox created this way is `engine://{provider_id}/{sandbox_id}`.

## Alternatives considered

- **Load the ES module inside the Python process.** Rejected. The host layer lives in the Node CLI; the SDK sends the resolved connection to that host.
- **Extend the Python gRPC engine to catalog providers.** Rejected for providers. That engine remains the built-in `alicloud-express` transport. The reason the SDK transport is HTTP/JSON + SSE + WebSocket is in the CLI ADR linked above.

## Dependencies

- `python-sdk/client-sdk/src/agent_sandbox/providers/engine_client.py`
- `python-sdk/client-sdk/src/agent_sandbox/providers/engine_provider.py`
- `python-sdk/client-sdk/src/agent_sandbox/providers/registry.py`
- The Node engine started by `abx provider engine serve` (see the CLI ADR)

## Test Strategy

`pytest tests/test_providers tests/test_engine` from `python-sdk/client-sdk`, including `tests/test_providers/test_engine_provider.py` (CubeSandbox through the engine, and a call after the engine restarts). The run is recorded in the CLI evidence file linked from the CLI ADR. There is no dedicated automated Python test for `node`-kind OpenSandbox.

## Acceptance criteria

- An installed `node`-kind provider is an `EngineProvider` and is reached only through `abx-engine/1`.
- `engine://{provider}/{id}` is the sandbox marker for that path.
- A restarted engine is discovered again under the per-loop start lock, and the in-flight client retries once.
- `alicloud-express` still resolves to the in-process built-in provider.

## Consequences

Catalog providers are one Node implementation. Python grows a client of that engine, not a second copy of each plugin. The gRPC engine is superseded for those providers and remains in the tree for `alicloud-express`.
