# Template System

Templates use specification 5. A template defines the complete sandbox contents,
its startup/readiness commands and every service it provides. Starting a template
never selects a subset by workflow, operation or application/exec/interpreter type.

## Responsibilities

The template owns application source, dependencies, configuration and startup.
The Provider owns image upload/registration, platform identifiers, sandbox creation
and endpoint resolution. The CLI prepares source and starts the complete template.
Python consumes a prepared reference or connects to an existing sandbox; it does
not acquire Docker/source-build responsibilities.

## Launch and use

Use `abx --provider PROVIDER template launch TEMPLATE_REF` or Python
`launch_template(manifest, provider=..., reference=...)`. The launcher checks only
operations needed to create, start, inspect readiness and clean up. Missing interpreter
operations never prevent an unrelated application from starting. Actual operations
remain guarded by the Provider and server policy at invocation time.

Every `provides` service is retained. SandboxServer protocol v2 endpoints receive protocol checks;
unknown protocols are returned and use the author's readiness command. A multi-service
template starts once. Calling one endpoint later does not start a different template.

## Manifest and migration

See [the field reference](../reference/template-yaml-spec.md) and the authoritative
[template-v5 schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v5.schema.json).
Remove `workflow_contract_version`, `default_workflow` and `workflows`; keep
`spec_version: 5`, `provides`, `start_cmd`, `ready_cmd` and application metadata.
Old running manifests require explicit migration. Source locations, prepared image
references and native template IDs are preparation details, not user-selectable flows.

## Ownership and verification

The launcher records creation intent and owned IDs. Uncertain creates are not replayed;
cleanup attempts every owned client and sandbox, retaining failures for reconciliation.
Connecting to an existing sandbox does not confer deletion ownership.

Catalog membership or a static supported plan is not a test pass. Historical workflow
receipts remain readable history; they do not certify specification 5. A template's
metadata version is not a registry storage/versioning service. Use actual Git revisions
and recorded inputs to reproduce a run.

See [Python launch examples](../guide/template-workflows.md),
[authoring templates](../guide/authoring-templates.md), and
[the server API](../guide/template-server-api.md).
