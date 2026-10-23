# template.yaml Specification

Current templates use `spec_version: 4` and `workflow_contract_version: 1`. The complete publishing authority is [awesome-templates/template-v4.schema.json](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/main/spec/template-v4.schema.json); the shared workflow contract lives in [contracts](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts). The full schema retains application deployment topology, hooks and durable state.

## File Location

Each source template has one `template.yaml` at its root. Source catalog rows locate that file rather than repeating workflows; managed entries embed the entire declaration. Dockerfiles, command modules and dependency files form the source input alongside the manifest.

## Complete Field Definitions

### Basic Information

The publishing schema requires metadata including `name`, `version`, `description`, `author` and `license`; consult it for `tags`, `priority`, `wave` and `smoke`. The SDK runtime model does not replace the complete publishing schema.

### Runtime Configuration

`env` is a string map and `ports` lists application ports. `start_cmd` and `ready_cmd` participate in explicit startup behavior. The actual service must listen on the declared port. Parsing SDK metadata never rewrites a Dockerfile.

### Resource Specifications

Published source manifests use `resources.cpu` and `resources.memory`; the SDK runtime configuration can also carry `cpu_count` and `memory_mb`. Application resources and topology follow the full schema. Planning a sandbox workflow does not execute an application deployment.

### Sandbox Generation

`generation` belongs to the selected template/provider startup configuration; the catalog source schema currently requires `2`. Creation still requires the provider to implement the declared input and startup mode.

<a id="capability-declarations"></a>
### Workflow Declarations

| Field | Meaning |
| --- | --- |
| `spec_version` | Required integer `4` |
| `workflow_contract_version` | Required integer `1` |
| `provides` | Services, each with `protocol`, `version`, `port`, `operations` |
| `default_workflow` | Required identifier of one declared workflow |
| `workflows` | Named `application`, `exec` or `interpreter` paths |

Every workflow explicitly supplies `kind`, `input` (`source/image/managed/service`), `startup` (`exec/entrypoint/none`), `binding`, `operation` and `required_operations`. An application also names a `service` from `provides`. Binding fields are `transport`, `endpoint`, `caller`, `authentication`. Unknown workflow fields are rejected.

`startup: exec` requires a nonempty `start_cmd` and `exec.run`. Native startup uses `entrypoint` without running the start command again. A `service` input requires `startup: none`. A declared nonempty `ready_cmd` requires execution support and must actually be checked, regardless of startup mode. Managed references belong to one provider. Templates may add `required_operations` and `required_checks`, never remove derived requirements or minimum profile checks.

Template `capabilities`, `tested_on` and handwritten `providers` compatibility tables are rejected. There is no default `{shell, files, code}` grant. Providing Python or HTTP does not imply provider interpreter operations. See [explicit template workflows](../guide/template-workflows.md).

### Removed key: `custom_commands`

`custom_commands` is rejected. Register named functions with `@command` in the server's `commands.py` and invoke them through application HTTP; YAML does not generate functions.

### Server Policy (`server`)

Optional. Declares which SandboxServer endpoints the template exposes and under which restrictions
(design: [fine-grained-capabilities](../design/fine-grained-capabilities.md)). Absent = the server's default
behaviour. The block is validated structurally by `SandboxTemplate` (unknown keys are errors); values are
validated by `agent-sandbox-server check-config`. The server loads `/etc/agent-sandbox/server-policy.json` or the explicit `ABX_SERVER_POLICY_FILE`/`ABX_SERVER_POLICY` input. Ensure the chosen build/startup flow actually installs that policy; declaring YAML alone does not apply it.

| Key | Type | Description |
|-----|------|-------------|
| `preset` | `str` | `default`, `transfer-only`, `read-only`, `hardened`, `locked` |
| `base_dir` | `str` | Root for relative paths and the default path boundary |
| `groups` | `list[str]` or `map[str, bool]` | Turn capability groups on (`[agents, dev_tools]`) or on/off (`{process: false}`). A group is an alias for its endpoint ids |
| `defaults` | rule | Rule applied to every endpoint before its own rule |
| `endpoints` | `map[str, rule]` | Per-endpoint rules keyed by endpoint id (`files_download_stream`, `shell`, ...) |
| `auth` | map | `tokens` (`id`, `scopes`, `token_env` or `token_sha256`), `allow_anonymous`, `anonymous_scopes` |

A rule has `enabled`, `scopes`, `paths` (`allow`, `deny`, `read_only`, `symlinks`), `limits` (`max_bytes`, `max_request_bytes`, `timeout_seconds`, `rate_per_minute`, ...), `params` (`overwrite`, `deny_extensions`, `allow_commands`, ...) and `audit`.

```yaml
server:
  preset: transfer-only
  endpoints:
    files_download_stream:
      paths: { allow: [/home/user/out] }
      limits: { max_bytes: 5MB }
    files_upload_stream:
      paths: { allow: [/home/user/in] }
      params: { overwrite: false }
```


## Complete Example

This source-publishing example includes required metadata. Resolve its base-image placeholders through an explicit configuration before building.

```yaml
name: my-python-template
version: "1.0.1"
description: "Scaffold for a new Agent Sandbox template. Not a catalog entry."
author: "alibaba-agent-sandbox"
license: Apache-2.0
spec_version: 4
base: "fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>"
generation: 2
start_cmd: "agent-sandbox-server serve --port 9000 --commands /home/user/app/commands.py"
ready_cmd: "agent-sandbox-server healthcheck --port 9000"

resources:
  cpu: 2
  memory: 2048

ports:
  - 9000

tags:
  - example
  - skeleton

priority: P2
wave: other


env:
  ABX_SERVER_TOKEN: ""

smoke:
  - command: hello
    args:
      name: Express
    expect: "Hello, Express!"
workflow_contract_version: 1
provides:
  app:
    protocol: agent-sandbox-server
    version: 2
    port: 9000
    operations:
    - commands.list
    - commands.run
default_workflow: application
workflows:
  application:
    kind: application
    input: source
    service: app
    startup: exec
    binding:
      transport: http
      endpoint: provider-port
      caller: host
      authentication: service-token
    operation: commands.run
    required_operations: []
```

## Build Notes

`base` is valid source/template metadata. Builds use the selected effective Dockerfile and explicit build configuration; they never silently replace `FROM`, users, copy paths or entrypoints. Install dependencies through native files in the image. The Python launcher does not prepare source; select a prepared `image`/`managed` reference or explicit `service` path.
