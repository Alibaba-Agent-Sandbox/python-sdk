# Decision: Implement the unified Python Client SDK and Server SDK contracts
Status: proposed

## Problem

An application must be able to install the Python SDK, select a Provider, create or explicitly connect to a Sandbox, and call its actual services without installing `abx` or inheriting a developer's CLI configuration. The unified target design also requires Python and Node consumers to agree on resource operations, private access material, application preparation, HTTP behavior, and cleanup. Existing entry points and historical verification do not establish that this target is implemented.

This record assigns the Python repository's implementation work. The design has undergone review; these tasks remain proposed and have no implementation or release acceptance implied by this record. The existing client/server distributions retain their repository-managed version relationship. This repository owns the Python native Express implementation. Installable catalog Provider content, template resource schemas, CLI commands, and Registry indexing remain with their respective owners; this plan does not move the built-in Express implementation into the Provider catalog repository.

## Decision

Maintain the language-neutral runtime contracts and conformance fixtures here, implement their Python consumers, and export the same service contract from the Python Server SDK. Keep shared contracts below their consumers in the existing dependency layers. Node receives versioned data and fixtures; it must not import Python runtime code to use them.

| Task ID | Scope | Deliverable | Depends on |
| --- | --- | --- | --- |
| PY-01 | Canonical neutral runtime contracts | Versioned resource/operation contracts, private operation-completion and access contracts, `ApplicationSource`, helper host/operation contracts, and positive/negative conformance fixtures. Include source-preparation semantics shared by both languages. Publish one owner and revision for each contract; do not duplicate template YAML or Provider package schemas. | Joint contract review with Node, Provider, CLI, and template owners |
| PY-02 | Provider execution and independent installation | Python native Express implementation, Provider loader, and native execution path; explicitly bound implementation/configuration; installation and packaging of supported catalog Providers and the optional Node-only Provider dependency. Reuse the Node owner's internal host through the agreed contract without requiring `abx`, a user-started engine, or another language's system tooling. | PY-01; catalog Provider implementations where selected; Node host artifacts for the Node-only branch |
| PY-03 | Client resource and data APIs | Synchronous/asynchronous Clients, resource references, distinct create/get/connect, retained private access material, explicit style selection, built-in E2B helper, HTTP/OpenAPI/named-command views, and error/stream/file/cancellation/lifecycle behavior. | PY-01; PY-02 |
| PY-04 | Python Server SDK and application preparation | One registration source for routes and exported contracts; static `ApplicationSource` export; declared platform or application authentication; a single authorized create-preparation path with startup/readiness handling and known-resource failure results. | PY-01; PY-03; matching Provider startup/access capabilities |
| PY-05 | Source-distributed helpers and Python MCP | SDK-owned preparation entry independent of CLI; normal Python project dependencies for template source, fixed Git, or optional package sources; explicit factory imports; fixed MCP tool projection, access-handle retention, file-root enforcement, and owned/borrowed cleanup. | PY-01; PY-03; template/Registry source metadata |
| PY-06 | Product acceptance and documentation | Typed exports, package contents, independent-install examples, English/Chinese SDK guides and SDK Skill material, changelog, and repository-owned verification records for the delivered scope. | Relevant PY tasks and their real integration dependencies |

Implement and validate one usable vertical path before broadening protocol or platform support. A selected Provider implementation must remain fixed through operation, endpoint resolution, and cleanup. Installing or updating another implementation must not change an existing Client.

## API Design

The reviewed target API is the authority for signatures and fields. PY-01 records the final neutral contract shapes and fixtures before consumers implement them; this ADR does not introduce another field table or compatibility dialect.

- `ProviderClient` and `AsyncProviderClient` take explicit platform configuration and an optional application-provided default style. Service applications do not automatically load CWD dotenv, HOME configuration, global plugins, or CLI template rules. An application may explicitly supply its own configuration resolver.
- Local resource references do not perform I/O. `get` is read-only; `connect` explicitly obtains the platform's access material and declares any resume/expiry effect; `create` creates one resource. Ordinary calls and discovery do not perform an implicit create/connect/resume or switch protocols after failure.
- The public operation result and private completion/access data have separate purposes. Preserve actual credentials, endpoint/recipient association, expiry, and known partial results through the native and Node-host paths. Public serialization must neither lose the only usable access material nor disclose it. A failed public-result validation after a remote submission must retain known resource identity and submission outcome.
- Styles are explicit or come from the fixed Client default. Built-in E2B support ships with the Client SDK. Helpers use normal imports and typed factories; their local file paths refer to the calling process. HTTP requests, OpenAPI invocation, and Server SDK named commands retain their respective response and error contracts.
- `ApplicationSource` is ordinary static author data, generated from the same service registration and explicitly supplied by application code. An SDK-only example must show its real source/import. It does not require reading a CLI deployment database, fetching image layers, or importing server code in the client. Missing descriptions allow resource-only creation; an explicit request for application preparation must report the missing description before creating whenever detectable.
- Application preparation uses the declared startup owner, permitted channel, authentication mode, and readiness condition exactly once. Platform authentication follows the confirmed ingress policy. Services explicitly adopting the default application mode calculate MD5 from the agreed real template and instance identities; custom credentials and external Serving retain their own contracts. Unknown policy, missing identity, or failed authentication does not enable anonymous access.
- MCP tools use a startup-selected contract and same-language handlers. Calls cannot select new package sources, credentials, or Providers. Sessions retain create/connect handles; borrowed instances are only closed locally, while owned-instance deletion failures retain usable retry state. Client shutdown, remote deletion, and business Session cleanup remain distinct operations.

The normal SDK-only chain is: prepare project dependencies, import the chosen Provider/helper and optional static application description, construct an explicitly configured Client, create or connect, call the selected view, and release resources according to ownership. No step requires CLI installation, a user-managed internal token file, or runtime dependency installation.

After a high-level create with application preparation has obtained a new instance ID, preparation failure or cancellation must trigger a bounded independent cleanup attempt for that owned instance. `ApplicationPreparationError` retains the real ID, failed phase, original cause (including cancellation), and cleanup outcome (`deleted`, `failed`, or `unknown`) plus any cleanup cause. Accepted deletion without completion confirmation is `unknown`. Unknown creation without an ID is neither replayed nor assigned a guessed deletion target. This closing-stage wait is bounded separately from the original call; ordinary Client close never substitutes for remote deletion.

## Alternatives considered

- **Require the CLI or rename the complete CLI as a Python runtime dependency.** Rejected because SDK-only production use must not inherit CLI configuration, command parsing, deployment machinery, or user-managed engine processes.
- **Maintain separate Python and Node definitions for the same neutral contract.** Rejected because private access preservation, result projection, and failure behavior would diverge. Runtime implementations remain language-specific; contract data and conformance cases have one owner.
- **Treat every Provider as Node-only, or require every author to implement both languages.** Rejected. Prefer the selected native Python implementation; support the internal Node path only for Providers that require it. The first-party Express target includes both implementations.
- **Install helpers on first use or read CLI style rules in Python.** Rejected because application behavior must be reproducible from its code and dependencies on a machine without CLI state.
- **Put template deployment or a new generic application orchestrator in this SDK.** Rejected. The SDK owns explicit runtime operations and the narrow authorized application preparation contract; templates and the CLI own build/deploy behavior.

## Dependencies

The companion records below target `main`. Each link becomes available when that owner's planning PR merges; publishing a plan does not establish product delivery.

| Owner | Dependency and delivery order |
| --- | --- |
| [nodejs-sdk plan](https://github.com/Alibaba-Agent-Sandbox/nodejs-sdk/blob/main/.agents/notes/proposed/architecture/2026-11-27-unified-design-plan.md) | Consume PY-01 fixtures; provide the CLI-independent Node runtime/host and supported platform artifacts. Native Python work does not wait for Node-only packaging; that branch cannot be accepted until the real host artifact works. |
| [awesome-providers plan](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/blob/main/.agents/notes/proposed/architecture/2026-11-27-unified-design-plan.md) | Catalog Provider package metadata and implementations supply complete declared operations, identity, endpoint, and access behavior. Agree common behavior first, then validate each selected implementation. Native Express remains owned by the Python and Node SDK repositories rather than being moved here. |
| [awesome-templates plan](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/.agents/notes/proposed/architecture/2026-11-27-unified-design-plan.md) | Own template/Registry YAML specifications and author examples; consume Server SDK export and helper-source contracts. Author code supplies the static application description used by SDK-only examples. |
| [agent-sandbox plan](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/.agents/notes/proposed/architecture/2026-11-27-unified-design-plan.md) | CLI consumes the Node implementation of these contracts. CLI availability is not a Python runtime or installation prerequisite. |
| [registry plan](https://github.com/Alibaba-Agent-Sandbox/registry/blob/main/.agents/notes/proposed/architecture/2026-11-27-unified-design-plan.md) | Index and display fixed helper sources after the metadata contract exists. Local/fixed-Git installation and runtime calls remain usable without Registry access. |

Land neutral contracts and fixtures before dependent consumer implementations. Any packaging dependency on a new Provider or Node-host release must use an actually available artifact before advertising the dependent installation path. Do not close a cross-repository acceptance item when only this repository has merged its part.

## Test Strategy

For this planning record, validate ADR structure, links, repository health, and hygiene when the record lands. Do not run cloud workloads merely to validate prose. Future executable changes use the repository definition of done: `make test`, `make lint`, `make typecheck`, applicable `make ci`/distribution checks, `bash scripts/check-repo-health.sh`, `make hygiene`, and real-component E2E recorded separately. CI's supported-Python matrix is additional evidence, not replaced by one local interpreter.

Use conformance tests for native and Node-host results, malformed private/public results after submission, field preservation, provenance, and cancellation. Test real package installation in a fresh Python environment with no CLI and no CLI configuration. Exercise native Express and a supported Node-only Provider separately; inspect the actual packaged dependency closure and prevent package-manager execution during import or calls.

Run real HTTP components for both Server SDK languages, named calls, OpenAPI, file upload/download, and helper composition. Validate operation errors alongside cleanup errors, failure followed by deletion retry, close during late initialization, sibling-client independence, and synchronous callback/self-wait protection. MCP tests must cover fixed tools, explicit private-instance connection, permitted file roots, cancellation after upload, and failed cleanup followed by a successful retry.

Real platform acceptance uses a controlled resource set, independently verifies business outputs and deletion, and records exact SDK/Provider/server versions. Anonymous/private/unknown ingress, short-lived access material, default/custom application authentication, new-machine reconnection, and snapshot identity changes are separate cases. Unsupported or unrun branches remain explicitly unaccepted; passing schemas or local substitutes do not establish cloud support.

## Acceptance criteria

- [ ] PY-01 has one versioned neutral contract source and language-independent fixtures consumed by Python, Node, and Provider tests; no duplicated schema silently overrides it.
- [ ] PY-02 installs and runs supported native and Node-only paths without `abx`, a user-started engine, or runtime installation; selected configuration and implementation remain stable throughout cleanup.
- [ ] PY-03 preserves private create/connect access material while public results remain secret-free; explicit connection on a new machine can call a supported private instance, and missing information fails without an implicit write.
- [ ] PY-03 exposes the declared E2B/helper/HTTP methods with their actual inputs, return values, errors, cancellation, and ownership behavior; the same application behaves identically with and without unrelated CLI state.
- [ ] PY-04's author export, static client import, one-create preparation, and same registered business operation form a complete observed chain. Preparation failure or cancellation after creation triggers a bounded independent delete attempt; the error preserves the created ID, original cause, and actual cleanup outcome without losing a retryable identity. An unknown or conflicting startup/authentication requirement is never reported as ready.
- [ ] PY-05 installs an unpublished source helper into a portable Python project, performs a real file-to-report call, and exposes the same operation through Python MCP with fixed credentials/targets and recoverable owned-resource cleanup.
- [ ] PY-06 includes required checks, real integration evidence, resource-cleanup confirmation, both documentation languages, accurate exports/package metadata, and a changelog. Merge, release availability, and real acceptance are recorded as separate facts.

## Evidence

Planning basis: the unified target design reviewed on 2026-11-27 and this repository's contributor, ADR, and definition-of-done rules. This document is an implementation plan only. It records no new product tests, cloud deployment, published package, or completed task. Implementation evidence must be added in this repository under its normal verification convention without changing historical records.

Document validation and review disposition: [verification](../../../evidence/verify/2026-11-27-unified-design-plan.md).
