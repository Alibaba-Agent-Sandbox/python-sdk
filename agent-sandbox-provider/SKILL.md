---
name: agent-sandbox-provider
description: Write an Agent Sandbox provider plugin so ProviderSandbox.create(provider=...) can talk to a new sandbox backend. Use when the task is abx-provider.toml, a rest, exec, or node provider, feature ids, or E8004. Do not use this to call an existing sandbox; that is agent-sandbox-sdk.
---

# Write an Agent Sandbox provider

This file is instructions for a coding agent. It is not executed by the SDK.
Calling `Sandbox.create` against a backend that already exists is
`agent-sandbox-sdk`. This skill only covers the provider you add.
The client distribution is `agent-sandbox-client` (import `agent_sandbox`).
Install the verified public alpha pair; the client installs its matching server dependency:

```bash
python -m pip install 'agent-sandbox-client==0.3.1a5'
python -m pip check
```

The image needs only `agent-sandbox-server==0.3.1a5`. Installing that package on the host does not update an existing image. Development source installations must use a matching client/server revision.
Do not install `agent-sandbox`; that PyPI project is unrelated.

Only `alicloud-express` is built in. Do not reinstall it and do not reuse
its id. `opensandbox`, `cubesandbox`, `e2b`, and `alicloud-container` are
official catalog ids in `awesome-providers`. Install those with
`registry:<id>`. Do not reuse them for a new backend. A new id matches
`^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, length 2-40, and must not start with
`abx-`, `alicloud-`, or `shortcuts`.

The CLI loads `alicloud-express` plus installed `rest`, `exec` and `node`
plugins. It rejects `kind = "python"`. An in-code `Provider` subclass still
works from the Python SDK. Catalog providers (`opensandbox`, `e2b`,
`cubesandbox`, `alicloud-container`) are all `node` (an ES module,
`provider.mjs`): install with
`abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes` (or
`python -m agent_sandbox.providers install registry:<id> --yes`), then
`abx --provider <id>` or `ProviderSandbox.create(provider="<id>")`. The Python SDK
reaches `node` plugins through the local engine (`abx provider engine serve`,
started on demand; `abx` must be on `PATH` or in `ABX_BIN`) using
`EngineProvider`. Python `exec` and `rest` manifests still run in the Python
process. The catalog guide is
`awesome-providers/docs/zh/principle.md`. The official site is
https://www.agent-sandbox.cn. The registry website is
https://registry.agent-sandbox.cn. The installer index is
`https://registry.agent-sandbox.cn/providers/index.json`.

## Pick a kind

| Kind | Write | Use when |
|---|---|---|
| `rest` | only `abx-provider.toml` | The backend speaks the E2B HTTP shape: `POST /sandboxes` with `templateID`, header `X-API-Key` or bearer, envd on `https://{port}-{id}.{domain}` |
| `exec` | the manifest plus a process that speaks EPP/1 on stdin/stdout | The API is not E2B-shaped. Any language. Default installation verification starts the process after trust confirmation |
| `node` | `provider.mjs` with `export default create(kit)` | The backend is E2B-shaped but needs a tweak (proxy dial, optional token, other paths). Loaded in the host process; one implementation serves the CLI and Python ProviderSandbox through the local engine |

Installation verification and doctor may execute trusted plugin code (`exec` starts a process;
`node` imports the module and calls its factory). Download/extraction alone does not execute it.
Node doctor requires an engine with the initialization route; upgrade and restart an older
CLI if it reports that initialization cannot be verified. Doctor never creates a sandbox,
and a successful initialization does not prove cloud credentials or backend availability.
The Node.js SDK currently provides the in-sandbox HTTP `ServerClient`, not provider lifecycle.

Do not start from the Express engine. Do not copy the Express `ABX_SANDBOX_API_KEY` or its standard-entry `E2B_API_KEY` setting into the new provider. Credentials belong to their selected backend.

## Credentials

Name the key `api_key` in the manifest. The environment variable is
`ABX_<ID>_API_KEY`, with `-` turned into `_` and the id uppercased.
`my-cloud` reads `ABX_MY_CLOUD_API_KEY`.

`[core] inherit` shares `sandbox_api_key`, `sandbox_base_url`, or
`sandbox_domain` with the plugin. Inherit is opt-in. It asks the user to
consent, and it is how an Express key would leak into another backend. Leave
`inherit` empty unless the user explicitly wants that sharing.

Never print a key. Examples use `REPLACE_ME`.

## Features

`[features] supported` may contain only these ids. An unknown id is rejected
at install. A call whose id is absent raises `ProviderFeatureNotSupportedError`
(`E8004`) before any HTTP request.

```
sandbox.lifecycle   create, list, get, connect, kill
sandbox.timeout     set_timeout
sandbox.pause       pause and resume
exec.run            commands.run
exec.stream         commands.stream
process.manage      process list, stdin, signal
pty                 get_terminal
files.rw            read, write, list, move, remove
files.watch         files.watch
files.transfer      upload_url / download_url
templates.read      template list
templates.build     legacy template build
templates.deploy    opt-in image deployment via a provider template factory (CLI owned)
ports.url           network.resolve_url
ports.domain        a separate domain feature
storage.mount       volume mount
network.vpc         VPC
sessions            named commands on the in-sandbox server
```

Interpreter and workflow calls use the separate exact `[operations]` contract, with `operation_contract_version = 1` and explicit `cli`/`python` arrays. `code.interpret` is not an accepted feature id. Declare `code.execute`, `code.default-context.execute` or context/stream operations only for implemented consumer paths. Python exec/rest bridges do not implement interpreter operations. `[workflow]` declares supported input/startup kinds; declarations do not implement the transport. See the [shared contract](https://github.com/Alibaba-Agent-Sandbox/python-sdk/tree/main/contracts).

Declare a feature only when the backend actually implements that call. A
declared feature that 404s is worse than `E8004`, because the caller thinks
the call was attempted for real.

An API that is not one of those feature ids is an extension, not a new feature id.
On a Python `Provider`, set `extensions` to `Extension(id, summary, summary_zh, implemented, when)`.
`when` is `sandbox`, `code_interpreter_image`, `egress`, or `command`.
`extensions_for(sandbox_id=...)` is empty until a sandbox id is passed.
`implemented=False` still raises `E8004` from `require_extension`. Manifest
`[features.extensions.*]` is documentation; the installer does not parse it.

## rest manifest

Copy `examples/providers/e2b-compatible/abx-provider.toml` and change the id,
URL, and feature list. Drop `[core] inherit` unless the user asked for it.

```toml
manifest_version = 1
operation_contract_version = 1

[operations]
cli = ["sandbox.create", "sandbox.get", "sandbox.list", "sandbox.delete", "exec.run", "files.read", "files.write", "files.list", "files.stat", "files.remove", "files.move", "ports.resolve"]
python = ["sandbox.create", "sandbox.get", "sandbox.list", "sandbox.delete", "exec.run", "files.read", "files.write", "files.list", "files.stat", "files.remove", "files.move", "ports.resolve"]

[workflow]
inputs = ["managed"]
startups = ["exec", "none"]

[provider]
id = "my-cloud"
name = "My Cloud"
name_zh = "我的云"
version = "0.1.0"
description = "What this backend is."
license = "Apache-2.0"

[compat]
protocol = "e2b-rest/1"
requires = { sdk = ">=0.3", cli = ">=0.3" }

[runtime]
kind = "rest"

[endpoint]
base_url = "https://api.example.com"
domain = "sandboxes.example.com"
auth = { scheme = "header", header = "X-API-Key" }

[features]
supported = [
  "sandbox.lifecycle", "sandbox.timeout", "exec.run", "exec.stream", "files.rw", "ports.url",
]

[security]
network = ["api.example.com", "sandboxes.example.com"]

[auth]
any_of = [["api_key"]]

[config.fields.api_key]
type = "string"
secret = true
credential = true
description = "API key. Set ABX_MY_CLOUD_API_KEY."
description_zh = "API 密钥。设置 ABX_MY_CLOUD_API_KEY。"
```

`domain` is the suffix in `https://49983-{sandboxID}.{domain}`. If the
backend returns `envdUrl`, that value wins. If it does not, the SDK builds
the host from `domain` and port 49983.

Install and check:

```bash
python -m agent_sandbox.providers install ./my-cloud --yes
python -m agent_sandbox.providers doctor my-cloud
python -m agent_sandbox.providers test my-cloud
```

```python
import asyncio
from agent_sandbox import ProviderSandbox as Sandbox

async def main() -> None:
    async with await Sandbox.create(
        provider="my-cloud",
        template="base",
        timeout=300,
        provider_options={"api_key": "REPLACE_ME"},
    ) as sb:
        print((await sb.commands.run("echo ok", timeout=30)).stdout)

asyncio.run(main())
```

`timeout` on create is the sandbox lifetime, not the HTTP timeout.

## exec plugin

Use `examples/providers/local-process/` when the API is not E2B-shaped.
`[runtime] kind = "exec"`, `protocol = "epp/1"`, and `command` is the
process. The process speaks JSON-RPC 2.0 on stdin/stdout. It must not read
the parent environment; secrets arrive only in `initialize`.

Declare the same feature ids. A method you did not implement must not be
listed, or the host will call it and surface your error instead of `E8004`.

## node provider

```js
export default function create(kit) {
  return {
    async buildInfra(ctx) {
      const http = ctx.http({
        base_url: String(ctx.options.base_url),
        domain: "example.app",
        auth: ctx.headerKeyAuth(String(ctx.options.api_key), "X-API-Key"),
      });
      return {
        auth: ctx.headerKeyAuth(String(ctx.options.api_key), "X-API-Key"),
        http_client: http,
        endpoint: { base_url: String(ctx.options.base_url), domain: "example.app" },
        sandbox_protocol: new kit.SandboxProtocol(http),
        process_protocol: new kit.ProcessProtocol(http),
        filesystem_protocol: new kit.FilesystemProtocol(http),
      };
    },
  };
}
```

The manifest sets `[compat] protocol = "node/1"` and `[runtime] kind = "node"`,
`entry = "provider.mjs"`. The host gates every protocol by the declared
features, so undeclared methods raise `E8004` before I/O. See
`awesome-providers/e2b/provider.mjs` and `cubesandbox/provider.mjs`. The host kit does not supply an interpreter implementation; provide one explicitly only when declaring its exact operations.

## Before you say it works

1. A fake TCP server, or the contract kit, must show the request path, the
   auth header, and that `E2B_API_KEY` is not sent.
2. Every id in `supported` is one the backend documents. Everything else is
   `E8004` or an extension with `implemented=False`.
3. Create, one command, one file round-trip, and kill are the minimum live
   check. Skip that check when the user has not provided the backend, and say
   which variable is missing. Do not borrow another provider's key to try.
