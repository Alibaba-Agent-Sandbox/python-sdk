# Builtin sandbox data plane

The builtin `alicloud-express` provider uses the SDK's HTTP transport directly:
`Sandbox.create` posts to the platform, and commands, files and terminals use
the returned envd endpoint and credentials. Create and connect share the same
protocol implementations. No local session daemon, gRPC socket, `grpcio` or
`protobuf` package is required for this builtin path.

The platform response remains authoritative for sandbox ID, template ID/alias,
metadata, resources, expiry and envd version. The latter selects raw JSON
stream requests for envd0.5 and Connect envelopes for envd0.6. The sandbox TTL
and the create HTTP request timeout remain separate options.

```python
from agent_sandbox import Sandbox

async with await Sandbox.create("base", timeout=300, request_timeout=30) as sb:
    result = await sb.commands.run("echo ready")
    print(result.stdout)
```

Set `ABX_SANDBOX_API_KEY` and your configured platform endpoint/domain as described
in [authentication](../guide/authentication.md). `close()` releases local HTTP
connections while leaving the sandbox alive; `kill()` destroys it. Reconnect
with `Sandbox.connect(id)` from another process without a held local session.
An interrupted create can have an unknown remote outcome; do not blindly repeat
mutations. Identify owned resources using metadata and reconcile them first.

## Migration from the Python engine slice

The experimental deep import `agent_sandbox.engine.Engine`, its command-line
module and `ABX_ENGINE_SOCKET` are retired. Replace direct bridge calls with
`Sandbox.create/connect`, `commands`, `files` and `open_terminal`. Old engine
sockets are not consulted. Stop any separately managed legacy daemon yourself;
this SDK does not delete another process's socket or kill its resources.

Installed `node` provider plugins still use the CLI's **Node** engine and
`~/.abx/engine.json` through `providers.engine_client`. That engine and the EPP
process adapter are separate active contracts; neither is removed. See the
[Node engine API](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md).
The [old Python engine](provider-engine.md) and [plan](provider-engine-plan.md)
are historical records, not setup instructions.

The native controller also passed a real Droid0.241.1 background install and independent SDK/HTTP verification, with owned cleanup confirmed. See the [exact source-runtime evidence](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/aaef5b63ee11b6b76b93b7ebbc8ad2530b21f576/.agents/evidence/verify/2026-10-18-droid-native-runtime.md). This is separate from Dockerfile/template deployment and model certification.
