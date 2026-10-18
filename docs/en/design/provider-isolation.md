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
| Express SDK, control-plane signing, explicit custom exchange, FC/ACR deployment, CLI options/prompts, AI management schemas | `providers/alicloud_express/` |
| Reusable E2B/envd wire adapters and token formatting | `providers/shared/e2b/`, explicitly selected by a provider |

The distribution composition roots register bundled adapters, configuration descriptors,
CLI extensions and AI extensions. The generated configuration catalog is declarative
compatibility data. Historical `api`, `protocol` and `transport` imports remain export
facades; they do not constitute a second implementation or a core fallback.
The shared HTTP/Connect transport implements framing and connection reuse; providers
choose its authentication and adapters. It never chooses a cloud backend.

## SDK contract

`Provider.build_infra(config)` is used for the bundled default and plugins alike.
`session_protocols`, `prepare_session`, `resolve_session_url` and `open_terminal`
assemble provider-owned sessions. Express uses its native HTTP control/data plane for
create and connect; no local gRPC daemon is installed, selected or restored. Catalog
plugins continue to use the separate Node provider engine. Native sandbox calls require
an explicit sandbox API key; AK/SK is reserved for control-plane management. A custom
exchange callback remains an explicit compatibility API, with no automatic key creation.

`TransportConfig(provider="external")` and `load_config` leave undeclared endpoint and
region defaults empty. Explicit endpoints remain intact. Failed create binding cleans
up the newly created resource; failed connect preserves the borrowed one. Public import
facades retain module identity for historical monkeypatch users. Missing optional
protocols fail E8004 without selecting Express.

CLI template factories and AI/CLI discovery live in the CLI owner; no new Python
image deployment API is introduced. See the [CLI boundary contract](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/design/provider-isolation.md).
Bundled provider updates still follow matching SDK releases. Adapter isolation does
not promise zero-change migration or capabilities absent from a backend.

An explicit provider wins over an unrelated ambient default. The HTTP regression covers
empty and nonempty Volume hints while the removed daemon is unavailable. Session URLs
are built by the selected wire adapter. Historical TransportConfig URL helpers delegate
to a composition-injected builder; they are not used to choose another backend.

Configuration schema discovery is injected from the package composition root. Reading
the bundled schema loads pure provider metadata without discovering the registry;
provider package exports remain lazy. Compatibility names/constants and generated
configuration declarations remain public data, with one runtime implementation per adapter.
