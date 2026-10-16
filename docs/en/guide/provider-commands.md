# Provider management commands

Provider commands manage resources owned by a selected cloud backend, such as volumes or
custom domains. They are separate from sandbox shell execution and the named commands
registered in `agent-sandbox-server`. A provider can declare its own operations without
adding top-level CLI commands or changing another provider's command set.

The default provider does not advertise `storage.mount`, `ports.domain` or `network.vpc`: the standard sandbox protocol has no callable operation for those tokens. Provider resource management uses declared commands; a volume management command does not imply live sandbox mounting.

## Mount an existing Volume when creating a sandbox

The built-in provider accepts `volume_mounts` in `Sandbox.create()` (and `create_sync`):

```python
from agent_sandbox import Sandbox

async with await Sandbox.create(
    provider="alicloud-express",
    template="my-template",
    volume_mounts={"/mnt/data": "existing-volume-name"},
) as sandbox:
    print(await sandbox.files.list("/mnt/data"))
```

The dictionary maps absolute sandbox paths to existing **Volume names**, not IDs. The Volume
and API key must use the same Team and region. For OSS, configure the Volume's RAM role;
`metadata["fc.sandbox.auth.role"]` overrides that role when supplied. Check the
[official mount guide](https://help.aliyun.com/zh/agent-sandbox/mount-oss-volume-1)
for storage permissions, template/runtime prerequisites and storage-specific limits.
Volume currently requires invitation access through an Alibaba Cloud support ticket;
confirm access for the target account, region and Team before preparing storage, as
described in the [official OSS Volume guide](https://help.aliyun.com/zh/agent-sandbox/user-guide/create-oss-volume).
An empty successful Volume list does not prove create or mount access.
Custom MicroVM source images must include ossfs2 2.0.10 or newer. Select a template
that meets the official mount guide's runtime prerequisites before running acceptance.

Paths must be normalized absolute Unix paths other than `/`, with no trailing separator,
empty or hidden component, `.`/`..`, NUL or surrounding whitespace. `/bin`, `/opt`, `/var`,
`/dev` and their descendants are rejected. Names must be nonblank strings without surrounding
whitespace or NUL. Invalid hints fail before provider construction or engine I/O. Nonempty
hints for other providers fail with E8004 before loading their implementation. Omitted/empty
dictionaries preserve existing request payloads.

This creation hint is separate from management commands and does not add a portable
`storage.mount` protocol or runtime attach API. Python's built-in lifecycle retains its local
gRPC engine: additive `CreateRequest.volume_mounts` carries the dictionary, and the existing
Python protocol serializes `POST /sandboxes` as
`"volumeMounts": [{"name": "existing-volume-name", "path": "/mnt/data"}]`.
For nonempty hints, the client first checks `Health.supported_create_options` contains
`volume_mounts`. An older live engine fails with E8004 and an upgrade/restart suggestion,
before `Create`; it is never replaced automatically. This prevents older protobuf handlers
from silently ignoring a mount request. Calls without mounts retain the existing behavior.
Provider management commands continue using the shared Node HTTP engine. Mount wiring is
covered by local gRPC/HTTP regression tests and real OSS mount/read/write/cleanup acceptance
on the base template in cn-hangzhou. The opt-in Volume E2E suite also checks that data survives
sandbox destruction and recreation.

## Python API

```python
from agent_sandbox.providers import commands

provider = "alicloud-express"
operations = await commands.list_commands(provider)
for operation in operations:
    print(operation["id"], operation["effect"], operation["input_schema"])
```

After choosing a declared command and building `payload` according to its schema, call
`await commands.get_command(provider, command_id)` to inspect it and
`await commands.run_command(provider, command_id, input=payload, confirm=False)` to run it.

All functions are asynchronous and require an explicit provider id. Discovery (`list_commands`
and `get_command`) takes only IDs and never resolves or forwards credentials. Invocation
(`run_command`) accepts `provider_options={...}` and canonical overrides accepted by `load_config`,
including `sandbox_api_key`, `sandbox_base_url`, `region` and `access_key_id` where applicable.
The resolved connection always names the same provider as the URL. Only declared provider
configuration fields and consented generic credentials are forwarded.

`list_commands` returns descriptor dictionaries, `get_command` returns one descriptor,
and `run_command` returns the command's JSON result. Read the schema before supplying input.
Unknown or unavailable operations fail through the engine's typed error contract, including
E8004 for unsupported commands. The SDK does not create or connect a sandbox for these calls.

Writes and deletes require `confirm=True`, while the default is `False`. Set it only after
reviewing the selected operation and resource identifiers. This requirement is enforced by
the engine. No interactive prompt is opened by the SDK.

**The SDK never retries a provider-command POST**, even for an idempotent operation, a lost
connection or HTTP 401. If the response is lost, inspect provider state before deciding to
call again. The `idempotent` descriptor is information for the caller, not permission for
transport replay. GET discovery retains the existing engine reconnection behavior.

## Manifest contract

Only `node` and `exec` plugins can declare nonempty command sets. Existing manifests without
a `[commands]` section retain an empty set. An explicit empty section must contain
`protocol = "provider-commands/1"` and `entries = []`; a `rest` provider may use that form.

```toml
[commands]
protocol = "provider-commands/1"

[[commands.entries]]
id = "volumes.list"
description = "List provider volumes"
description_zh = "列出提供方存储卷"
input_schema = { type = "object", properties = {}, additionalProperties = false }
output_schema = { type = "object" }
effect = "read"
idempotent = true
```

This is a descriptor example, not a promise that a particular installed provider implements
`volumes.list`. IDs use `^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$` with at most 80 characters;
duplicate IDs and unknown descriptor fields are rejected. Both descriptions are required.
`effect` is `read`, `write` or `delete`, and `idempotent` is an explicit boolean. A manifest
has at most 128 commands; each entry is limited to 64 KiB of compact UTF-8 JSON and depth 16.

Schemas use JSON Schema draft 7. Input roots must specify `type = "object"` and
`additionalProperties = false`; output schemas must be schema objects. Schema references,
`$id`, `$async`, `pattern`, `patternProperties` and `format` are excluded as schema
keywords. Business property names such as `format` remain valid. JSON keys
`__proto__`, `prototype` and `constructor` are excluded at every depth. Finite JSON values
are required. Python validates this structural contract when loading a manifest; the Node
host performs the authoritative strict schema compilation and validates input and output.
The SDK does not maintain another implementation of cloud business logic or schema evaluation.

Command descriptors, including effects and schemas, are part of the install consent summary.
Changing them during update requires renewed consent. Old receipts without a `commands`
field mean an empty list, so unchanged legacy plugins do not acquire an extra risk change.

## Engine protocol

The shared local engine exposes these authenticated routes:

| Method | Route | Result / body |
| --- | --- | --- |
| GET | `/v1/providers/:id/commands` | `{ "commands": [descriptor, ...] }` |
| GET | `/v1/providers/:id/commands/:command` | One descriptor |
| POST | `/v1/providers/:id/commands/:command` | Body `{ "input": {}, "confirm": false }`; returns command result |

Every request carries the existing bearer token and `X-Abx-Connection` header. The provider
in that connection must match the route. Existing commands and features remain independent.
A `node` plugin returns `provider_commands.run(commandId, input, signal)` from `buildInfra`;
an `exec` plugin dispatches EPP `provider.commands.run` with `{command, input}`. Hosts dispatch
only manifest-declared IDs. A missing handler remains unsupported.

The CLI owns the implementation and the command surface. See the
[shared engine specification](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md)
and [provider architecture](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/design/node-provider-architecture.md).
Install a compatible `abx` on `PATH`, or set `ABX_BIN`; older engines without these routes
cannot execute provider commands. Plugin code still runs with the documented host privileges.
