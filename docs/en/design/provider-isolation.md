# Provider implementation boundaries

The host selects a `Provider` for every lifecycle operation, including the bundled
Express backend. There is no null/default-provider bypass. Core API objects consume
structural protocol and authentication contracts; they do not instantiate a vendor
SDK, exchange cloud credentials, derive backend URLs, or select a wire protocol.

## Ownership

| Responsibility | Owner |
| --- | --- |
| Provider selection, consent, integrity checks, output, generic configuration precedence, client-resource cleanup | Host |
| Authentication, endpoints, wire mapping, backend errors/statuses, lifecycle and optional create inputs | Selected Provider |
| Template authentication, build/register/poll/delete, Docker/registry specifics | Provider template implementation |
| Template source search/download, project scaffolding and runtime validation | Host, using the selected provider's declared metadata and factories |
| Express SDK, management-plane signing, FC/ACR deployment, CLI options/prompts, AI management schemas | `providers/alicloud_express/` |
| Reusable E2B/envd wire adapters and token formatting | `providers/shared/e2b/`, explicitly selected by a provider |

The distribution composition roots register bundled adapters, configuration descriptors,
CLI extensions and AI extensions. The generated configuration catalog is declarative
configuration data. Retired `api`, `protocol` and `transport` forwarding imports are removed.
The shared HTTP/Connect transport implements framing and connection reuse; providers
choose its authentication and adapters. It never chooses a cloud backend.

## SDK contract

`Provider.build_infra(config)` is used for the bundled default and plugins alike.
`session_protocols`, `prepare_session`, `resolve_session_url` and `open_terminal`
assemble provider-owned sessions. Express uses native HTTP/Connect/WebSocket
adapters directly; the retired Python gRPC engine and its lifecycle hooks stay
removed. The external Node engine/EPP client remains a separate provider contract.

`TransportConfig(provider="external")` and `load_config` leave undeclared endpoint and
region defaults empty. Explicit endpoints remain intact. Failed create binding cleans
up the newly created resource; failed connect preserves the borrowed one. Missing optional
protocols fail E8004 without selecting Express.

CLI template factories and AI/CLI discovery live in the CLI owner; no new Python
image deployment API is introduced. See the [CLI boundary contract](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/design/provider-isolation.md).
Bundled provider updates still follow matching SDK releases. Adapter isolation does
not promise zero-change migration or capabilities absent from a backend.

Explicit provider selection wins over an unrelated ambient default. Pure bundled
configuration values live in `utils/bundled_config.py`; transport consumes the
`_provider_schema.py` contract and injected discovery rather than importing a registry.


## Port and file URL ownership

The selected adapter implements synchronous port access and project-server gateway
headers. An adapter exposing only asynchronous port discovery must be called through
`await sandbox.network.resolve(port)`; synchronous helpers fail E8004 instead of
guessing an Express/E2B address or sending a foreign token. Standalone network
constructors require an explicit port adapter. File transfer URLs
are optional filesystem adapter hooks; missing hooks fail E8004 even if the session
URL happens to use HTTP. The core never constructs `/files` routes for foreign providers.

Neutral Python transport/protocol imports do not load built-in authentication or wire
adapters. Consumers import implementations from their owning provider modules.

Provider configuration metadata remains declarative. Lower layers consume the shared schema and injected discovery; executable adapters stay in their owning provider modules. Retired forwarding imports and implicit URL builders are removed.
