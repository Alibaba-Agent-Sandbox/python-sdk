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

### Follow-up contract clarification

PY-01/03 define result and service-identity contracts; PY-04 owns server identity acceptance; PY-05 owns MCP projection. These refinements stay within the existing tasks; no additional subsystem or completed implementation is implied.

A received upload identity remains observable when a later helper stage fails. Preserve the original exception/HTTP details and recognizable cancellation, with safe progress containing the completed stage, known file ID and actual cleanup state. An unknown submission is not safe to replay or automatically delete. Explicit file deletion affects only the caller's selected upload, never a borrowed instance. MCP cancellation/disconnection cannot guarantee delivery of a final error or identity; do not add a recovery daemon or claim durable recovery from exception fields.

Raw HTTP request/invoke keeps its status, allowed headers and body, including non-2xx. CLI and MCP adapters use actual HTTP executor metadata to report non-2xx as failure, not the presence or absence of an exception or an arbitrary business `error` field. A submission returning 202 is accepted, not completed; a completion-promising helper must observe its actual terminal contract. Successful tool output schemas do not constrain error content. Keep native E2B/OpenSandbox exception and process-result semantics intact.

Default MD5 application authentication requires both sides to know the same real instance and historical cloud-template identity. Native connect may obtain platform traffic credentials without recovering that association. A Provider-verified mapping or an explicit caller assertion based on original creation facts may supply it; current Registry aliases, downloaded source and unverified runtime fields may not. The optional shared service binding `template_id` fills an unknown association only, never overwrites a confirmed identity or changes server-side identity, and is distinct from a platform-verified mapping. Compare only identifiers with the same confirmed semantics. Missing identity disables that authentication branch, with no alias guessing or authentication downgrade. The derived value is not strong authentication.

The existing service binding gains optional `template_id` for an explicit non-secret historical identity assertion, shared by named calls, HTTP views and helpers. Python cancellation must remain recognizable as CancelledError; adding progress must not convert it to success or hide the original cause. External custom Bearer is application-provided; native connect and CLI initialization do not manufacture or recover it.

### Detailed delivery contract refinement

The detailed review adds finite parameter, response and capability contracts to the existing tasks. These remain proposed implementation requirements, not new released APIs. Record four independent states for each item: implementation, contract tests, real-backend acceptance (including exact platform/runtime combination), and release artifact. A passing documentation check completes none of the runtime states.

Shared operation rules are fixed before consumer code:

- Standard create accepts only the declared source and optional fields. Omitted TTL stays omitted; null is accepted only by a declared no-expiration source. Express has no supported direct-image or instance CPU/memory/disk/GPU override in this target; template specifications remain available. Unknown fields fail before submission.
- `sandbox.connect` has optional positive finite `ttl_seconds`, only when `connect_support.ttl_seconds` explicitly declares it; supported constraints are minimum, maximum and integer. Omission sends no value. `may_resume` and `may_change_expiry` remain explicit. A separate timeout operation changes expiry without implicitly connecting; resume has no TTL override.
- Standard list input is `{cursor?,limit?,status?:string[],metadata?:map<string,string>}` and output is `{items:SandboxInfo[],next_cursor?}`. Do not merge page-number and cursor contracts or automatically enumerate all pages.
- Lifecycle `ActionResult` is `{id,outcome:accepted|completed|not_found,observed_status?,observed_at?}`. Only deletion may report confirmed not_found; 202 is accepted, and 204 is interpreted using the actual endpoint contract. Unknown submissions are errors with progress, never successful completed results.
- Common SDK requests default to 60 seconds; create with application preparation uses a 600-second total budget and an independent 30-second cleanup budget. No create replay on an uncertain result. E2B native request/connection timeout zero retains its documented unlimited meaning but cannot override an explicit host deadline.
- SDK options follow language naming; operation JSON retains its declared keys. Preserve null, omission, false, zero and empty values. Exact int64 values use decimal strings in the public contract; query/path encode text, while native JSON integer/number fields require lossless unquoted numeric literals and native string fields remain strings. Never round through JavaScript numbers or change the declared wire type. Dynamic map keys are not recursively renamed.
- HTTP request/invoke retains the actual response; typed convenience and named command methods retain their declared success/error semantics. CLI/MCP project non-2xx as failure and 202 as accepted. Helper failure preserves actual stage, known resource IDs and cleanup status without forcing operation-specific progress into a different wrapper.
- Ordinary file output uses the same sensitive-field projection as ordinary terminal output. Only an explicitly requested secret export may write the secret; safe exclusive creation and post-submission failure rules still apply.

The 2026-11-27 fixed official Sandbox/2026-08-20 metadata has 41 management operations (SHA-256 `f52311d5a814d14f62717be118d76ecd7e046a395cb6aa644090f9ca817af0c1`). The earlier 29 already included four template-cache operations; additions are five custom-domain, five warm-pool and two observation queries. Names alone are not coverage: native request/response nested fields, defaults, omission/update behavior, public projection and sensitive fields must all be checked. Use the [official metadata](https://api.aliyun.com/meta/v1/products/Sandbox/versions/2026-08-20/api-docs.json) and record its actual hash; a later response may change.

The required Express groups are template CRUD (5), template cache (4), volume CRUD (5), API Key (6), Team (5), Quota (4), custom-domain (5), warm-pool (5), metrics/usage (2). Instance E2B HTTP operations, networking, append-mounts and envd data operations are separate from that 41-operation count. Cache and warm-pool item identity is Team plus real template ID; do not invent Cache/Pool IDs. Account objects stay under the Provider. Snapshot create targets an instance, while snapshot list/delete target the snapshot resource under the host's fixed sandbox snapshot route.

Express instance logs and metrics remain required target capabilities, with implementation/platform acceptance blocked until the actual route and behavior pass. Logs use the verified v2 cursor (Unix milliseconds), limit 0..1000, direction, minimum level and case-sensitive search, not guessed since/tail mappings. Metrics use native Unix-second start/end and actual sampling, with no synthetic step. Follow must report an incomplete boundary when same-millisecond saturation prevents reliable progress; timestamp+1 is not proof of complete delivery. Placeholder metric values must not become measured zero. Do not register these capabilities as supported based only on the old CLI method.

E2B helper compatibility is the declared envd files/commands/PTY surface, not the entire E2B cloud product. Pin Python `e2b==2.31.0` and Node `e2b@2.31.0` source/interface evidence separately. The Python wheel hash is `532631b1b5d13d3bc6b7f8a81730f4c54e021b724cc3ec21efd000c84f58a87a`; Node tarball hash is `07fbc1254230790ccfc109d1b95096359e4abc008c9eb596d4250b4def70fcbc`. Read-only package inspection does not establish ABX compatibility. Metadata requires envd 0.6.2; advanced watch entry/network-mount options require 0.6.3/0.6.4; old runtimes reject them before side effects.

Required file methods are read, write, write_files/writeFiles (including the Node overload), list, get_info/getInfo, exists, make_dir/makeDir, rename, remove, watch_dir/watchDir and handle/stream closure. Required process methods are run, list, connect, send_stdin/sendStdin, close_stdin/closeStdin, kill and handle wait/disconnect/kill/stdin; PTY includes create/connect/input/resize/kill. Preserve native result/exception differences, real bytes and cancellation semantics. File-like objects provided by callers remain caller-owned.

Legacy envd multipart upload in the pinned upstream SDK buffers file-like input. Merely wrapping it is insufficient. Known-length regular-file upload requires a bounded multipart implementation and actual old-runtime memory tests; unknown-length/non-seekable streams are accepted only after the server's streaming support is verified, otherwise rejected before consumption or submission. No silent unbounded buffer, spool subsystem or write replay. Command capture defaults to 16 MiB combined stdout/stderr, explicitly adjustable in SDK style options; stop local reception with a typed capture-limit error and the known PID/partial output, never pretend completion or kill the remote process implicitly. Bound the upstream accumulator as well as wrapper queues.

New-machine SDK-only and separate-process CLI acceptance must cover explicit create/connect, actual private access material, public/protected/unknown ingress and identity requirements. No CLI state may affect application style selection. Installation, fixed source dependencies, regular imports, static help and same-language helper reuse remain separate phases. No runtime package installation or remote metadata-driven local code loading is added.

#### Python owner completion checklist

PY-01 owns the neutral schemas, complete response models, parameter/default tables and conformance fixtures. Map each public method to its implementation owner and retain an explicit disposition for existing independent domains; CLI renaming cannot delete Template, Volume, Git, Code Interpreter, declarative execution, sessions or managed Agents APIs. Preserve their real fixed contracts rather than pretending the E2B data-helper subset is the entire SDK.

PY-02 must deliver native Express required operations without abx. The only SDK Provider preparation command is `python -m agent_sandbox.providers install SOURCE --manager uv|pip [--requirements FILE]`; update/removal use ordinary project dependencies, not another SDK management tree. Optional Node-only Provider preparation is an installation concern and must have a real independently installable host artifact. Native management operations, raw transport credentials and public resource projections are distinct contracts. Ordinary networking rules use the closed headers transformation model; unsupported OAuth/STS control keys and unverified creation parameters are rejected rather than accepted as an arbitrary map.

PY-03 provides explicit ProviderClient/AsyncProviderClient constructors; target/sandbox/describe/supports/operations; call/stream/close; and typed sandboxes create/get/connect/list/delete. SandboxHandle/AsyncSandboxHandle provide style, bind, discover, call and close. A no-I/O local handle is not a successful remote get. Default-style convenience methods forward to exactly one application-selected view.

Retain ServerClient as asynchronous. The new standalone synchronous entry is SyncServerClient, with no redundant AsyncServerClient alias. Both provide request/invoke/named call, contract loading/description/support checks, file helpers and lifecycle methods; request/invoke preserve HTTP responses, while post_json and upload_file keep their declared JSON-result/error behavior. upload_file sends the declared binary body, not an invented multipart default. Contract-not-loaded is an error, not supports=False. Existing Server tools files/process/PTY/system/devtools/browser remain separately typed from E2B files/commands.

PY-04 completes CommandRegistry registration, lookup/visibility/export and typed command metadata; SandboxServer serve/start/shutdown/export; RouteTable, request/response/SSE and PTY author APIs; and explicit ServerPolicy models. Authentication may derive from an already explicit policy; do not require a duplicate authentication object in the five existing cases. The default health probe only establishes server readiness, not all application dependencies. Applications with dependencies supply the actual readiness check. Build export and running routes come from the same registry and cannot start cloud/model work while exporting.

PY-03/04/05 acceptance covers synchronous and asynchronous resource/HTTP/style contracts, Python Server with Node client and Node Server with Python client, explicit application startup/readiness failures, helper composition progress, import/installation portability and fixed MCP tools. Raw/typed/named HTTP errors and native E2B errors retain their different documented semantics. Type models must include optional/null fields and exact units, not just method names or an untyped response dict.

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

Follow-up acceptance also requires:

- Verify raw 401/500 responses remain inspectable while named errors preserve their exceptions; 202 is never decoded as a completed report.
- Exercise received upload identity followed by HTTP error or cancellation, explicit single-file deletion, unknown outcomes and MCP cancellation without claiming final-response delivery.
- Test the shared template_id binding against confirmed identities, unverified aliases and missing identity; SDK-only use must not read CLI private configuration.


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

Follow-up review and verification: [failure and authentication contracts](../../../evidence/verify/2026-11-27-feedback-contracts.md).

Detailed delivery-contract verification: [parameter and capability review](../../../evidence/verify/2026-11-27-delivery-contracts.md).
