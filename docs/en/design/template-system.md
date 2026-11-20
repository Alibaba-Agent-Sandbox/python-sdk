# Template System

Templates define reusable application source and named Sandbox/Serving resources.
Use `specVersion: 1`, optional author-defined `vars`, `sandbox.<name>.template`
and component-native `serving.<name>.props`. The [field reference](../reference/template-yaml-spec.md)
links the owning specification and explains Python's current consumer limits.

## Responsibilities

The template owns application source, dependencies and runtime startup code. The
Provider owns native preparation, instance lifecycle and endpoint resolution. The
CLI handles resource expressions, builds and deployment; deploying a Sandbox
resource does not create every future runtime instance.

Python consumes prepared IDs through ProviderSandbox or connects to an existing
instance. Template runners create dynamic instances and start their applications
with the required private values. Managed Agents API uses Worker-owned Session
instances; its clients call one Gateway endpoint.

## Runtime and source configuration

Current named-resource template.yaml files are consumed by the CLI. The SDK's
older launch_template/TemplateSession snapshot interface and discovery projection
have not migrated to those source files. Keep their independent supported contract
separate; do not infer current source support from a shared version number.

The direct runtime path does not require another YAML parser or a Python deployment
engine. Native Devs owns expressions. Application runtime configuration and server
policy are separate from reusable resource preparation.

## Ownership and cleanup

Delete only instances/resources created by the owning application. Closing a local
connection does not delete a borrowed instance. Managed Sessions expose close and
cleanup Operations separately from public deletion; inspect their outcome before
considering compute released.

See [Python runtime examples](../guide/template-workflows.md),
[authoring templates](../guide/authoring-templates.md), and
[the server API](../guide/template-server-api.md).
