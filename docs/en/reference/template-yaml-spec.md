# template.yaml resources and Python runtime

Keep one local `template.yaml` with `specVersion: 1`. The authoritative fields are in
the [template specification](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/template-spec.md)
and [schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v1.schema.json)
for the matching template/CLI revision. Publication metadata and initialization questions
belong to `registry.yaml`; local execution does not depend on that file.

| Field | Meaning |
| --- | --- |
| `specVersion` | Integer `1` |
| `name` | Project/application name |
| `vars` | Optional reusable values with author-defined keys |
| `sandbox.<name>.provider` | Resource's Provider |
| `sandbox.<name>.template` | Template properties, including its region and image/reference/build declaration |
| `sandbox.<name>.template.buildConfig` | Dockerfile with optional context, or native Steps |
| `sandbox.<name>.volumes` | Named static Volumes, when supported by the selected Provider |
| `sandbox.<name>.actions` | Resource lifecycle actions |
| `serving.<name>.component` | Component source and pinned version |
| `serving.<name>.props` | Component-native properties |
| `serving.<name>.actions` | Resource lifecycle actions |

The CLI evaluates native Devs expressions and prepares/deploys these resources. This
file does not declare each dynamic Sandbox instance or a universal application process.
The selected template supplies its runtime startup code. Native template
`startCommand`/`readyCommand` retain their Provider preparation semantics; they are not
a replacement for an application's create-time authenticated startup.

## Use resources from Python

Take the prepared template ID returned by deployment and follow the template's
`run.py` instructions, or call `ProviderSandbox.create` and explicitly start the
application. TTL, model credentials, runtime environment and dynamic mounts belong
to the instance or application runtime policy. Existing mounted Volumes remain owned
by whoever supplied them; deleting an instance does not delete those Volumes.

The SDK's existing `launch_template`/`TemplateSession` interface accepts an earlier
prepared snapshot shape. Its YAML parser and discovery projection have not migrated
to the current named-resource source format. Resolving `${...}` first does not make
that source shape acceptable. Use the direct runtime path above; the current source
file must not be passed to that older snapshot interface. See
[launching and cleanup](../guide/template-workflows.md).

<a id="capability-declarations"></a>
## Application endpoints and server policy

An open port does not start a process, grant a Provider operation or define a business
protocol. Use `await sandbox.application_endpoint(port)` for the selected Provider's
actual endpoint descriptor, or `application_client` for a running SandboxServer.
Gateway headers remain distinct from the application token.

SandboxServer API permissions are independent runtime policy. Load the documented
policy file or `ABX_SERVER_POLICY_FILE` / `ABX_SERVER_POLICY`. Named commands are real
Python functions registered with `@command`; YAML does not create them. See
[fine-grained capabilities](../design/fine-grained-capabilities.md).
