# Template System Design

Templates use specification 4 and explicit workflow contract 1. A template describes supplied software and named ways to use it. Provider adapters, the selected SDK/CLI consumer, local configuration and trusted verification are separate inputs; installing Python or an HTTP server does not implement a provider interpreter operation.

The current specification is [template.yaml Specification](../reference/template-yaml-spec.md), the publishing authority is [template-v4.schema.json](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v4.schema.json), and execution guidance is [Explicit template workflows](../guide/template-workflows.md). The Node.js CLI is maintained in [agent-sandbox](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox); Python owns its client, in-sandbox server and the shared [workflow contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts).

## 1. Official Core Templates

The source of current template inventory is [awesome-templates](https://github.com/Alibaba-Agent-Sandbox/awesome-templates). Catalog membership, author smoke commands and historical acceptance do not guarantee that every provider/client can run every workflow. Use the actual manifest and selected workflow, rather than a fixed list of promised launch environments.

<a id="tier-1--launch-templates-5"></a>
<a id="tier-2--extension-templates-5"></a>
The earlier launch/extension lists are replaced by the source-owned catalog. This page does not promise template release dates, installed package versions or an automatic security certification.

<a id="base"></a>
<a id="python-base"></a>
<a id="python-data-science"></a>
<a id="node-web"></a>
<a id="code-interpreter"></a>
<a id="browser-automation"></a>
<a id="full-stack"></a>
<a id="go-dev"></a>
<a id="java-dev"></a>
<a id="ml-gpu"></a>

## 2. Template Sources and Distribution Mechanism

### 2.1 Template Name Resolution Rules

A source index entry locates one authoritative `template.yaml`; it cannot override its workflow or startup commands. A provider-managed entry embeds a complete strict manifest and belongs to that provider. Local source paths, Git revisions, image references and managed IDs represent different input kinds, not interchangeable aliases.

| Workflow input | Meaning |
| --- | --- |
| `source` | A project snapshot requiring an implemented preparation path and explicit build configuration |
| `image` | A prepared image; the Python launcher requires an immutable SHA256 reference |
| `managed` | A provider-owned reference; launching requires a provider-resolved immutable identity |
| `service` | An existing application HTTP service with an explicit binding and `startup: none` |

Unknown references grant no default operations. Python's standalone launcher does not prepare source projects, and unresolved managed IDs fail before create. Source Dockerfiles are never rewritten from `base` metadata or replaced by a guessed fallback image.

### 2.2 Usage from Different Entry Points

For an existing sandbox, use `ProviderSandbox.connect(...)` and `await sandbox.application_client(port, token=...)` to reach its application service. This resolves an independent provider port endpoint; the provider's internal control or execution endpoint is not the application URL.

For a new prepared-image workflow, `agent_sandbox.api.launch_workflow(...)` takes the actual manifest, workflow ID, provider and immutable reference. It checks requirements before sending application payloads. See [the complete Python examples and limitations](../guide/template-workflows.md#python-application-consumption).

The CLI catalog guidance uses `abx template launch SOURCE --workflow ID`; a portable source build additionally selects `--build-profile portable` when that profile exists. The selected CLI/provider must actually support its input and startup path. Express currently declares only managed input and entrypoint/none startup; that says what this project implements, not whether its platform can build images through other native APIs.

### 2.3 GitHub Tarball Resolution Flow

Source acquisition and execution are separate phases: resolve the requested source revision, safely acquire the project, parse its one manifest, freeze the eligible source snapshot, then plan the selected workflow. A downloaded archive or a cache hit proves neither provider support nor runtime verification. Remote authentication failures must not silently retry as anonymous requests or change the source identity.

### 2.4 Template Package Structure (Repository/Subdir Contents)

```text
my-template/
├── template.yaml       # spec_version: 4, workflow_contract_version: 1
├── Dockerfile          # explicit native image build
├── Dockerfile.portable # optional explicitly selected build profile
├── commands.py         # application commands, if this service uses them
└── requirements.txt    # application dependencies, if needed
```

Optional `AGENTS.md` is an instruction file consumed by external agent tools. Its presence does not add a runtime operation. Snapshot identity excludes unsafe secret/ignored paths and rejects unsupported symbolic-link inputs; evidence must be written outside the frozen snapshot to avoid self-reference.

### 2.5 Official Template Repository

[awesome-templates](https://github.com/Alibaba-Agent-Sandbox/awesome-templates) owns source manifests, Dockerfiles, publishing schema and catalog. [awesome-providers](https://github.com/Alibaba-Agent-Sandbox/awesome-providers) owns installable provider adapters. The built-in Express descriptor belongs to the CLI. Registry and website consume these sources and do not grant missing handlers.

### 2.6 GitHub Token Configuration (Private Repositories & Rate Limits)

Source-download credentials belong to acquisition, provider credentials to the control plane, gateway headers to the resolved endpoint, and an application token to the application. They must not be copied across these audiences. Consult the owning CLI documentation for its actual token configuration; never put credentials or signed endpoint URLs into manifests, receipts or public diagnostics.

### 2.7 Local Cache Management

A cache is an acquisition optimization. Reuse requires the expected identity and must not skip current manifest validation, operation planning or verification qualification. A mutable branch name is not the immutable source/build/artifact identity required by a current receipt.

## 3. Custom Template Methods

<a id="method-1-cli--dockerfile"></a>
### Dockerfile and an explicit build profile

Put real dependencies, users, files and entrypoint settings in the selected Dockerfile. A portable profile is an explicit alternative, not a silent rewrite of the provider-native build. The source-root context is the quoted string `'.'` so YAML consumers agree on its type.

<a id="method-2-sandboxyaml-declarative"></a>
### A strict manifest

`template.yaml` carries template metadata and named workflows. A separate `sandbox.yaml` client configuration is not a metadata alias. Named application functions are registered in the in-sandbox server (`@command`); a YAML key does not generate those functions. See [authoring templates](../guide/authoring-templates.md).

<a id="method-3-publish-to-github-fetch-by-tagbranchsha"></a>
### Publishing source

Publish the real source revision and preserve its manifest/build inputs. A mutable ref can locate it, but verification must bind resolved content. Publishing source does not publish a provider-managed reference or make a workflow verified.

## 4. Template Specification (template.yaml)

### Complete Field Definitions

Use the complete [specification reference](../reference/template-yaml-spec.md#complete-field-definitions) and source-owned schema rather than a second independent field list. Required publishing metadata includes name, version, description, author and license. `spec_version` is integer `4`; `workflow_contract_version` is integer `1`.

### Field Classification

| Declaration | Responsibility |
| --- | --- |
| `provides` | Service protocol/version/port and application operations actually supplied by the template |
| `workflows` | Named kind, input, startup, binding, operation, service and additional requirements |
| `default_workflow` | Exactly one declared workflow selected when no other ID is given |
| `start_cmd` / `ready_cmd` | Explicit startup/readiness commands; a nonempty readiness command requires execution even with entrypoint/none startup |
| `build_profiles` | Explicit Dockerfile/context selections; no implicit portability rewrite |
| `server` | In-sandbox endpoint policy, which must actually be installed and applied by the chosen build/startup flow |

Old `capabilities`, `tested_on`, handwritten `providers` compatibility claims and unknown workflow keys are rejected. No omitted field grants `{shell, files, code}`. `base` remains valid metadata; it does not silently rewrite Dockerfile `FROM` or construct an inheritance chain.

### Key Design Points

1. The template supplies software and application protocols. It cannot implement a platform adapter or consumer handler by declaration.
2. The provider operation contract declares exact operations separately per consumer and its supported input/startup modes. For example, `exec.run`, `ports.resolve` and `code.context.execute` are distinct operations.
3. Planning is three-valued: T permits subsequent local checks, F names an explicit mismatch/missing implementation, U means unresolved information. F dominates U. Missing project adapter support does not establish that the native platform lacks the capability.
4. An application server can use shell startup plus a resolved HTTP port without any unified interpreter. Missing interpreter support blocks that interpreter workflow alone.
5. SDK/CLI transport and network binding must match the selected operation. Server policy can further deny an application endpoint even if its handler exists. Unknown discovery is denied; application payloads follow protocol and policy checks.
6. Maturity, local environment checks and current trusted verification remain independent. A Stable label or historical test cannot certify this manifest, consumer and binding.

### Example: Extension Based on a GitHub Template

Extend a source project by editing its actual Dockerfile and strict manifest, rather than relying on a remote `base.from` inheritance rule. The source-owned [python-hello manifest](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/python-hello/template.yaml) declares distinct source and prepared-image application workflows for the same `app` service. Its portable build profile is selected explicitly. Copying this pattern still requires actual provider/client support and local credentials; it is not a readiness guarantee.

## 5. Template Version Management

### Semantic Versioning

A template's `version` is metadata. Specification version, workflow contract version, resolved source revision, manifest digest, artifact digest and consumer revision have separate meanings. A SemVer label never substitutes for these identities.

### Version Selection

Select the source revision and declared workflow explicitly. A prepared image launch requires a digest-pinned image; a managed launch requires an immutable provider resolution. The Python launcher does not expand invented template SemVer ranges or automatically translate a repository reference into a cloud template.

### Version Listing

Read available source versions and manifests from the owning catalog/repository. Current verification is qualified only for matching source, manifest, build, artifact, provider code, consumer, workflow, binding and contract identities. Content changes invalidate reuse even when the human-readable name stays unchanged.

## 6. Template Marketplace Architecture

Registry ingests source-owned metadata, computes scoped plans and presents qualified evidence. Website presents its accepted strict catalog snapshot. Neither executes visitor workloads or obtains visitor cloud credentials while building catalog pages.

### CLI Command Overview

The current command surface belongs to [the CLI's Using Templates guide](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md). Catalog workflow launch uses explicit source and workflow IDs. Provider-native deployment, application deployment topology and workflow launch have their own explicit operation requirements.

### Template Security

Trust requires independent approved CI provenance and matching artifacts. A template may add required checks but cannot remove a verification profile minimum. Missing, failed or skipped required checks do not qualify. Author-authored PASS JSON, a runner name or historical smoke output cannot certify itself. Signatures and security audits must be supported by actual evidence rather than assumed for every catalog item.

## 7. Note: Session Management and Templates

A workflow plans a selected use of the static source/artifact and owns only the runtime resources it creates. Creation intent and returned resource IDs must be durably recorded; an uncertain create is not replayed automatically. Cleanup attempts owned deletion even if journal writes or connection close fail, and unresolved resources remain visible for reconciliation. Closing a connection to an existing sandbox does not transfer ownership or delete it.

Application HTTP binding preserves sandbox proxy prefixes and signed query values, separates gateway headers from application tokens, checks endpoint lifetime, and rejects redirects, authority overrides and encoded namespace traversal. The in-sandbox HTTP server remains a separate protocol with endpoint policy and token scopes; see [Server API design](server-api.md).

## Related: the abx CLI

See the CLI's [Using Templates](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/guide/using-templates.md), the current [Python workflow guide](../guide/template-workflows.md), [template specification](../reference/template-yaml-spec.md) and [server application API](../guide/template-server-api.md). The pinned standard clients keep their independent public contract; project provider adapters currently give Express/E2B/REST no unified interpreter operations and CubeSandbox/container only the persistent default-context operation.
