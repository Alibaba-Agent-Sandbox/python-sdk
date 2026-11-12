# template.yaml Specification

Use `specVersion: 1` and one local `template.yaml`. The complete field types and Provider subsets belong to the [template v1 schema](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v1.schema.json) and [template specification](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/docs/template-spec.md). Publication metadata and initialization questions belong to optional `registry.yaml`; local runs do not require it or `parameters`.

Template files use YAML1.2 Core with strict UTF-8 and a 1 MiB limit. Plain `on` and dates such as `2026-11-12` remain strings. Duplicate keys, aliases, unsupported tags, non-string mapping keys and non-finite/non-JSON values are rejected before resource creation.

| Field | Meaning |
| --- | --- |
| `specVersion` | Integer `1` |
| `name` | Resource name |
| `sandbox.provider` | Selected Provider ID; Python's explicit Provider context can fill it |
| `sandbox.template` | Exactly one `source`, `image` or `reference`; optional preparation `props` and `aliases` |
| `sandbox.instance` | Runtime TTL, environment, metadata and Provider-supported instance settings |
| `sandbox.start`, `sandbox.ready` | Whole-sandbox startup and readiness commands |
| `sandbox.ports` | Optional additional port numbers; no inferred protocol or automatic service start |
| `sandbox.services` | Endpoint map: protocol, integer version, port and optional operations |
| `deployment` | Native Serverless Devs project; `resources.*.component` and native `props` |
| `application` | Explicit supported application coordinator, currently `type: agents-api` |

Preparation properties under `sandbox.template.props` do not become instance overrides. Existing template references cannot take preparation properties. Python consumes instance CPU/memory/disk/GPU, existing Volume-name mounts, environment, metadata and TTL when supported by the selected schema and Provider. It accepts the fixed `lifecycle: {onTimeout: kill, autoResume: false}` policy; pause/resume lifecycle orchestration is unavailable in this launcher and fails before creation. The independent `ProviderSandbox` lifecycle APIs retain their own contract.

Generic instance TTL defaults to 300 seconds; Managed Agents API uses 3600. Explicit Python `timeout`, `cpu`, `memory`, `disk`, `gpu` and `volume_mounts` replace the corresponding instance values. Explicit `envs` and `metadata` merge by name; the launch ownership metadata is reserved. Memory/disk units and availability follow the Provider, not a universal cloud quota promise. Express's high-level schema uses integer MB values.

Native `${...}` expressions require the real Devs parser. Python's prepared launcher accepts literals or an already resolved v1 snapshot and explicitly rejects unresolved expressions. Environment values are literal; empty strings do not implicitly read the host environment. Resolve secrets in the caller and pass them through `envs` or the resolved snapshot. Python does not construct source images or turn arbitrary component properties into cloud support. Custom Providers without actual v1 validators are refused by the prepared launcher; their independent Provider APIs remain available.

<a id="capability-declarations"></a>
## Services and server policy

`sandbox.services` describes endpoints; it does not enable server APIs or grant Provider operations. The launcher starts the entire template once. SandboxServer protocol v2 services receive health/discovery checks. Other protocols use `sandbox.ready` and are returned without inferred routes.

The root `server` key is not a v1 resource field. SandboxServer endpoint policy remains its own runtime configuration, loaded through the documented policy file or `ABX_SERVER_POLICY_FILE` / `ABX_SERVER_POLICY`. `validate_server_block` remains a standalone structural validator; the real server validates policy values. See [fine-grained capabilities](../design/fine-grained-capabilities.md). Named commands are Python functions registered with `@command`; YAML does not create them.

## Prepared reference example

The referenced template must already contain the application and server dependencies. The existing Volume must be accessible to the selected Provider/account. Python creates and owns only the Sandbox; it never deletes the borrowed Volume.

```yaml
specVersion: 1
name: python-hello
sandbox:
  provider: alicloud-express
  template:
    reference: base
  instance:
    timeout: 600
    cpu: 2
    memory: 2048
    envs:
      APP_MESSAGE: hello
    metadata:
      purpose: example
    volume_mounts:
      /data: existing-volume-name
  start: python /home/user/app/commands.py
  ready: agent-sandbox-server healthcheck --port 9000
  services:
    app:
      protocol: agent-sandbox-server
      version: 2
      port: 9000
      operations: [commands.list, commands.run]
```

For source preparation, replace `reference` with `source: {dockerfile: Dockerfile, context: .}` and use the CLI; Python still requires its prepared reference. Choose one startup owner so the image's native entrypoint does not launch the same application twice. See [launch and cleanup](../guide/template-workflows.md).

Provider authors can override the optional synchronous `Provider.validate_template_input(stage, value)` with their version's actual schema. Stages are `template.prepare` (template object) and `sandbox.create` (instance object). Return `False` or raise to reject. The inherited default is not a validator; asynchronous validation is rejected. Admission does not grant operations or forward instance fields that the high-level creation API has not implemented.

`sandbox.ports` preserves optional extra ports such as browser debugging or a database port. The compiled port list is the sorted union with service ports. `session.endpoints[port]` returns the Provider descriptor for extra ports outside `sandbox.services`, including gateway headers only in memory. It creates no ServerClient and sends no health/discovery request. A declared port does not guarantee native TCP or public connectivity; use the Provider's actual addressing/protocol. `await sandbox.application_endpoint(port)` provides the same descriptor independently. Existing service clients remain in `session.services`.
