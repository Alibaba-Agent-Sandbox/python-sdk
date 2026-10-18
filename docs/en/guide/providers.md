# Providers

This guide describes asynchronous `ProviderSandbox` provider extensions. Root `Sandbox` and `AsyncSandbox` follow the pinned standard migration contract; see [Migrate from E2B](migrate-from-e2b.md).

> **Note:** The `abx provider ...` commands on this page are provided by the Node.js CLI in the `cli` repository. Python-only users get the same operations from `python -m agent_sandbox.providers ...`. Both use the same install directory, the same receipts and the same tree digest.

A **provider** is a sandbox backend. The SDK and the CLI ship only `alicloud-express`. The others install with `python -m agent_sandbox.providers install registry:<id> --yes` from `https://registry.agent-sandbox.cn/providers/index.json`. A background check writes newer versions to `~/.abx/providers/updates.json`. `ABX_PROVIDER_UPDATE_CHECK=0` turns the check off. `ABX_PROVIDER_REGISTRY` changes the index URL. The official site is <https://www.agent-sandbox.com>. The registry website is <https://registry.agent-sandbox.com>.

| Id | Name | Kind | Default |
|---|---|---|---|
| `alicloud-express` | Alibaba Cloud Express Edition (阿里云极速版) | built-in | yes |
| `alicloud-container` | Alibaba Cloud Agent Sandbox, container edition | catalog plugin, `node`; CLI and every SDK after install | no |
| `cubesandbox` | CubeSandbox | catalog plugin, `node`; CLI and every SDK after install | no |
| `e2b` | E2B | catalog plugin, `node`; CLI and every SDK after install | no |
| `opensandbox` | OpenSandbox | catalog plugin, `node` (ES module, EPP methods run in the host process); CLI and every SDK after install | no |

The four non-default ids live in `awesome-providers`. Install with `abx provider install alibaba-agent-sandbox/awesome-providers//<id> --allow-unpinned --yes` or, once the public index is published, `python -m agent_sandbox.providers install registry:<id> --yes` (the `abx` CLI has no `registry:` form), then select with `Sandbox.create(provider="…")` or `abx --provider <id>`. All four are `runtime.kind = "node"` (an ES module, `provider.mjs`), written once in Node.js. The CLI loads them in-process. The Python SDK reaches them through the local Node engine (`abx provider engine serve`, started on demand, so `abx` must be on `PATH` or in `ABX_BIN`) using `EngineProvider` (`engine://<provider>/<sandbox-id>`). A third-party `exec` or `rest` manifest still runs in the Python process. The built-in `alicloud-express` is the Python builtin provider. There is no installable `python` kind. See the CLI's [Engine HTTP API](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/docs/en/reference/engine-api.md).

| Id | How to use it |
|---|---|
| `opensandbox` | [OpenSandbox provider](../design/provider-opensandbox-mapping.md). HTTP is made from the Node host process that loads `provider.mjs`. `ABX_OPENSANDBOX_BASE_URL` defaults to `http://127.0.0.1:8080`. |
| `alicloud-container` | [Container edition](../design/provider-alicloud-container.md). Needs `ABX_ALICLOUD_CONTAINER_DOMAIN`. Does not read `ABX_SANDBOX_API_KEY`. |
| `cubesandbox` | [CubeSandbox provider](../design/provider-cubesandbox.md). Default origin `http://127.0.0.1:3000`. |
| `e2b` | [E2B provider](../design/provider-e2b.md). Key is `ABX_ABX_SANDBOX_API_KEY`. Does not read `ABX_SANDBOX_API_KEY` or `ABX_SANDBOX_API_KEY`. |

The logical readiness of the three providers that have no backend here is [provider readiness](../design/provider-readiness.md). A coding agent that is adding a provider loads the `agent-sandbox-provider` skill (`agent-sandbox-provider/SKILL.md`).

If you never touch providers, nothing changes: every command, every output and every environment variable behaves as before. The id `alicloud-express` is stable. Only the display name may change.

---

## Engine recovery and uncertain results

For Node provider plugins, the Python SDK rediscovers the local engine once after a
transport failure only for `GET` and `HEAD`. A read stream can recover only before
it yields its first event. Creation, execution, uploads and other mutations are
never automatically replayed after a connection failure, even if no response or
SSE event arrived. The engine may already have performed the operation.

Such a failure raises `ProviderProtocolError` (E8020) with an unknown-outcome
message. Inspect the selected provider's sandbox list or command state before
retrying; a blind retry can create duplicate resources or repeat a command.
A confirmed engine HTTP 401 rejection can still refresh discovery once because
authentication rejects the request before dispatch. No idempotency or automatic
rollback guarantee is implied.

## Choosing a provider

Highest priority first:

| Where | Example |
|---|---|
| SDK argument | `await Sandbox.create(provider="my-cloud")` |
| CLI flag | `abx create --provider my-cloud` |
| Process environment | `export ABX_PROVIDER=my-cloud` |
| `./.env` | `ABX_PROVIDER=my-cloud` |
| `~/.abx/.env` | `ABX_PROVIDER=my-cloud` |
| `~/.abx/config.toml` | `[core]` `provider = "my-cloud"` (written by `abx provider default my-cloud`) |
| Built-in | `alicloud-express` |

```python
from agent_sandbox.api.sandbox import Sandbox

sb = await Sandbox.create(template="base")                          # alicloud-express
sb = await Sandbox.create(template="base", provider="local-process")
sb = await Sandbox.create(provider="my-cloud", provider_options={"cluster": "prod"})
print(sb.provider)                                                  # "my-cloud"
await sb.kill()
await sb.close()                                                    # releases the provider process
```

`Sandbox.connect`, `Sandbox.list` and `Sandbox.kill_by_id` accept the same `provider=` argument. A sandbox id belongs to the provider that created it. Pass a qualified reference such as `my-cloud:sbx-1` to `connect` and the provider is taken from the prefix. Conflicting `provider=` and prefix raise `ProviderMismatchError` (E8030).

Default provider management:

```bash
abx provider list
abx provider default my-cloud       # persist in ~/.abx/config.toml
abx provider default                # show the current default
abx provider default alicloud-express
```

---

## Installing a provider plugin

```bash
abx provider install ./my-provider                          # a local directory
abx provider install https://github.com/acme/abx-provider-acme.git --ref 3f2c...   # a full commit
abx provider install git@github.com:acme/abx-provider-acme.git --ref v1.2.0 --allow-unpinned
abx provider list
abx provider info my-cloud
abx provider update my-cloud --check
abx provider uninstall my-cloud
```

Without the CLI:

```bash
python -m agent_sandbox.providers install ./my-provider
python -m agent_sandbox.providers list --json
python -m agent_sandbox.providers update my-cloud --check
python -m agent_sandbox.providers doctor my-cloud
python -m agent_sandbox.providers test my-cloud       # the contract suite (needs pytest)
```

### What install does and does not do

- **Nothing from the plugin is executed at install time.** There is no `setup.py`, no postinstall hook and no `git checkout`. Git sources are fetched without a checkout, every entry is validated (regular files only, no symlinks or submodules, size and count limits) and the installer writes the files itself.
- The install shows a **consent screen**: id, version, source, resolved commit, content digest, the command that will run, the declared security block, the features, and the configuration fields. A non-interactive run needs `--yes`.
- A source is **pinned** when you give a full 40-hex commit (`--ref`) or `--sha256 <tree digest>`. A tag or branch is **unpinned**: it could move between your review and the install. An unpinned source is accepted only after a person read the consent screen in a terminal (no `--yes`), or with `--allow-unpinned`. `--yes` on its own never accepts a moving ref: the install fails with `ProviderTrustError` (E8012) and prints the commit to pin. `provider update` follows the same rule.
- Only `https://` and `ssh` git URLs are accepted. URLs with embedded credentials are rejected; use an SSH agent or install from a directory you cloned yourself. `--allow-insecure-transport` enables `file://`, `http://` and `git://` (for tests and development).
- The installed files are recorded in a receipt (`.abx-install.json`) with a SHA-256 tree digest. The digest is **verified every time the plugin starts**. If a file changed, the command fails with `ProviderIntegrityError` (E8011); reinstall or run `provider update`.
- `--link` makes a development symlink install with no integrity check. It needs confirmation, and every use prints a warning on stderr.

### Update and uninstall

`provider update` re-fetches from the recorded source. If the command, the security block, or the feature list changed, you must consent again. Installs that are **pinned** (a 40-hex commit or `--sha256`) do not move: `update` reports `pinned` and does nothing unless you pass a new `--ref`. `update` takes the same transport and verification flags as `install`: `--ref`, `--check`, `--yes`, `--allow-unpinned`, `--allow-insecure-transport` (the receipt does not remember that you used it; a `file://`, `http://` or `git://` source needs it on every update) and `--no-verify` (skip the post-update handshake). The previous version stays in a trash directory until the new one starts successfully, then it is dropped. If the new version fails (for example its handshake), the previous files **and its `data/` directory** are restored exactly. `provider uninstall` removes the directory; stored settings (`[providers.<id>]`, `ABX_<ID>_*`) stay unless you pass `--purge`. Uninstalling the default provider resets the default to `alicloud-express`.

### Where things live

```text
~/.abx/providers/
  <id>/
    abx-provider.toml     # manifest
    ...                   # plugin files
    .abx-install.json     # receipt: source, commit, digest, consent
    data/                 # the plugin's working and state directory (not hashed)
```

Everything outside `data/` is hashed into the digest, **including a `tests/` directory**: tests you ship are installed and change the digest, so keep large test suites out of the repository path you install (use `--subdir`) or accept the extra files.

---

## Provider kinds

| Kind | What it is | Installable | Works from |
|---|---|---|---|
| `builtin` | `alicloud-express` | n/a | SDK and CLI |
| `rest` | A manifest only: an E2B-protocol endpoint with its own base URL and key | yes | SDK and CLI |
| `exec` | A program that speaks EPP/1 (JSON-RPC 2.0, one JSON object per line, over stdin/stdout) | yes | SDK and CLI |
| `node` | An ES module (`provider.mjs`, `export default create(kit)`) that the Node.js host loads in-process. `opensandbox`, `e2b`, `cubesandbox` and `alicloud-container` are this kind | yes | SDK (through the engine) and CLI |
| `python` | A `Provider` subclass in code, registered with `register_provider` or a pip entry point. A manifest with `kind = "python"` cannot be installed | no | SDK only |

The four catalog providers are `node`. `exec` is the extension point for a third-party plugin in any language: one process works for both the Python SDK and the Node CLI. A backend that already speaks the E2B envd data-plane protocol only needs to implement the control plane (create, connect, list, kill) and return the envd URL; commands, files and terminals then use the fast native transports. A backend without envd implements the data-plane methods (`exec.run`, `files.*`) as well.

### Capability matrix

A provider declares the features it implements. Calling something it lacks raises `ProviderFeatureNotSupportedError` (E8004, also a `CapabilityNotSupportedError`), never an `AttributeError` or HTTP 404.

| Feature | What it covers |
|---|---|
| `sandbox.lifecycle` | create, connect, list, info, kill |
| `sandbox.timeout`, `sandbox.pause` | change TTL; pause and resume |
| `exec.run`, `exec.stream`, `process.manage` | buffered commands; streamed output; list, kill and signal processes |
| `pty` | interactive terminal |
| `files.rw`, `files.watch`, `files.transfer` | read, write, list, move, remove; watching; signed upload and download URLs |
| `code.interpret` | stateful code contexts |
| `templates.read`, `templates.build` | list and inspect templates; legacy image build, deploy and delete |
| `templates.deploy` | opt-in deployment from an existing image through a provider template factory |
| `ports.url`, `ports.domain` | public URL for a port; custom domains |
| `storage.mount`, `network.vpc` | object-storage mounts; VPC attachment |
| `sessions` | the sandbox survives the process and can be re-attached by id |

`templates.deploy` is an independent manifest declaration; `templates.build` does not imply it. The built-in `alicloud-express` retains its existing 18 declarations and does not declare `templates.deploy`. This SDK accepts the metadata but adds no Python template deployment method; the CLI owns factory dispatch. `abx provider list` shows the declared features of every provider on one line (`sandbox(lifecycle,pause) exec(run,stream) files(rw) ...`; `python -m agent_sandbox.providers list` prints the same), and `abx provider info <id>` shows the full list.

The manifest flag is enforced at run time, for every provider kind:

| Kind | Where an undeclared feature is stopped | Result |
|---|---|---|
| `exec` | the EPP adapters, before the request is written to the plugin | E8004 |
| `rest` | `feature_gate` around the built-in protocol classes, before any HTTP request | E8004 |
| `node` | `EngineProvider` before the engine call; the CLI gates the same call in-process | E8004 |
| `python` | `Provider.require(feature)` in the provider's own code | E8004 |

A feature that is declared but fails inside the backend is not E8004; the backend's error is mapped (see Errors below). Two different "not found" outcomes are kept apart on purpose: an unknown **sandbox id** is `SandboxNotFoundError` (E2009) on every provider and every `sandbox.*` call (`connect`, `info`, `set_timeout`, `pause`, `resume`; `kill` stays idempotent), and a missing template, file or process is E4001/E2001 or, with no `sdk_code`, `ProviderResourceNotFoundError` (E8005).

### What you can call after installing

Installing a provider does not enable every SDK method or every `abx` command. The SDK and the CLI call **the same installed plugin**. Each method and command needs one feature from the table above. If the plugin does not declare it, the call raises `ProviderFeatureNotSupportedError` (E8004) before any request is sent. `node`, `exec` and `rest` plugins work from both hosts. A `python` provider registered in-process works from the SDK only. A manifest with `kind = "python"` cannot be installed.

| Feature | Python SDK | CLI |
|---|---|---|
| `sandbox.lifecycle` | `Sandbox.create`, `connect`, `list`, `kill`, `info` | `create`, `list`, `info`, `kill`, `connect` |
| `sandbox.timeout` | `set_timeout` | `sandbox timeout` |
| `sandbox.pause` | `pause`, `resume` | `sandbox pause`, `sandbox resume` |
| `exec.run` | `commands.run`, `sandbox.run` | `exec`, `run` |
| `exec.stream` | `commands.stream` | `exec --stream` |
| `process.manage` | `commands.list`, `kill`, `send_stdin` | `sandbox process ...` |
| `pty` | `get_terminal` | PTY session |
| `files.rw` | `files.*` | `upload`, `download`, `sandbox files ...` |
| `files.watch` | `files.watch` | — |
| `files.transfer` | signed upload and download URLs | — |
| `code.interpret` | `run_code` | `sandbox code` |
| `templates.read` | template read APIs | `template list`, `template info` |
| `templates.build` | image build and template registration | `template build/push/create/deploy/install/delete`, `deploy`, `install` |
| `ports.url` | `network.get_url` | `sandbox url` |
| `ports.domain` | custom domain configuration | — |
| `storage.mount` | OSS mount | — |
| `network.vpc` | VPC configuration | `--vpc-id` family |
| `sessions` | `Sandbox.connect` on an existing id | `connect <provider:id>` |

### OpenSandbox

OpenSandbox is a catalog plugin, not part of this package. Install it, then create:

```bash
python -m agent_sandbox.providers install registry:opensandbox --yes
```

```python
sb = await Sandbox.create(template="base", provider="opensandbox")
proc = await sb.commands.run("echo hello")
await sb.files.write("/tmp/note.txt", "hello")
print(await sb.files.read("/tmp/note.txt"))
await sb.kill()
```

The capability table is [OpenSandbox provider](../design/provider-opensandbox-mapping.md). The same notes are in `awesome-providers/opensandbox/docs/README.md`.

### Extra capabilities

The feature ids above are the shared tool surface. A provider that has operations outside that list registers them on `Provider.extensions`. They do not appear in `features`, so `provider list` does not print them, and another provider does not gain them.

`describe()["extensions"]` always shows the provider's full registration. `extensions_for(sandbox_id=...)` shows only the entries that match that sandbox: `code` only on a `code-interpreter` image, `networkpolicy` only when egress was requested, `command.logs` only when a command id is known. An entry with `implemented=False` is visible under those rules and still raises `E8004` from `require_extension`. An earlier Python OpenSandbox provider registered `code`, `session`, `command.logs`, `snapshot`, `networkpolicy`, `metadata.patch`, `diagnostics` and `metrics` this way. The current catalog provider is `kind = "node"` (`EngineProvider`); its `extensions` tuple is empty.

---

## Writing a provider

A plugin is a directory with `abx-provider.toml` and the program it runs.

```toml
manifest_version = 1

[provider]
id      = "local-process"
name    = "Local Process"
name_zh = "本地进程"
version = "0.1.0"

[compat]
protocol = "epp/1"

[runtime]
kind    = "exec"
command = ["python3", "./provider.py"]   # argv list, never a shell string; "./" is relative to the plugin directory

[features]
supported = ["sandbox.lifecycle", "exec.run", "files.rw"]

[security]                               # shown at install and recorded; advisory, not enforced
filesystem       = ["data_dir"]
spawns_processes = true

[core]
inherit = []                             # generic keys the plugin wants; needs user consent

[config.fields.workdir_root]             # the plugin's own settings: ABX_LOCAL_PROCESS_WORKDIR_ROOT
type    = "path"
required = false
description = "Directory that holds sandbox working directories"
```

Two working examples are in this repository:

- `examples/providers/local-process/` — an `exec` provider in about 200 lines of Python standard library (lifecycle, commands, files).
- `examples/providers/e2b-compatible/` — a `rest` provider that is only a manifest.

OpenSandbox is a catalog `node` provider (a dependency-free ES module whose EPP/1 methods the host runs in its own process; `node provider.mjs` still serves EPP/1 on stdio) in [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox). It talks to an [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) server from the host process (streaming exec, files, process control, a terminal, pause/resume, port URLs). Install it with `abx provider install alibaba-agent-sandbox/awesome-providers//opensandbox --allow-unpinned --yes` (or the Python module), then `Sandbox.create(provider="opensandbox")` or `abx --provider opensandbox`. For a backend that is E2B-shaped, a `node` plugin is shorter: see `awesome-providers/e2b/provider.mjs`.

### Authoring checklist

1. **Manifest**: `manifest_version = 1` and a valid id. A catalog-style provider is `[compat] protocol = "node/1"` and `[runtime] kind = "node"` with `entry` a relative `.mjs` or `.js` file. An `exec` plugin is `protocol = "epp/1"` and `kind = "exec"` with `command`. A `rest` provider is an endpoint and no program. A manifest with `kind = "python"` cannot be installed. `[config.fields.*]` names every option, with `secret = true` on secrets and `env = [...]` for the vendor's own variable names. Errors are `E8014` with the broken field named. Items 2–6 are the `exec` checklist.
2. **Required methods**: `initialize` (return the features you implement), `shutdown`, and for `sandbox.lifecycle` `sandbox.create|get|list|kill`. Everything else is per feature (see "Methods a plugin answers").
3. **Feature flags**: declare exactly what works and nothing else. The host answers E8004 for the rest without calling you.
4. **Errors**: `-32003` for a feature you lack, `-32002` for a missing sandbox (`sdk_code` `E2009` if you want to be explicit), `sdk_code` on everything that has an SDK class, never a credential in a message.
5. **Conformance**: `python -m agent_sandbox.providers test <id>` (or `abx provider test <id>`) must pass; skipped cases are the features you did not declare.
6. **Publish**: pinned install line with a 40-hex commit, an honest `[security]` block, the consent-screen contents in the README.

Development loop: `python -m agent_sandbox.providers install ./my-provider --link --yes` installs a symlink with no digest check, so edits take effect immediately. Run `doctor`, then `test` (below), then install a pinned copy for real use.

### Methods a plugin answers

The wire methods, their parameter names and types, and which are required are listed in the [EPP method table](../design/providers-and-credentials.md#epp-methods) and, machine-readably, in `tests/fixtures/epp-methods.json` of the SDK repository (the CLI keeps an identical copy). In short:

- **Required** for `sandbox.lifecycle`: `sandbox.create`, `sandbox.get`, `sandbox.list`, `sandbox.kill`. `sandbox.connect` is **optional** (use it to resume or re-attach); when a plugin answers `-32601` for it, the host calls `sandbox.get` instead.
- **Per feature**: `exec.run`, `exec.start` (`exec.stream`), `process.list|kill|signal|stdin`, `files.read|write|list|stat|mkdir|remove|move`, `ports.url`, `sandbox.set_timeout`, `sandbox.pause|resume`. Declare a feature only if you implement all of its methods; the host raises E8004 for the rest.
- **Extensions** the host does not call yet but plugins may offer: `files.search`, `files.chmod`, `exec.start{detached}`, `files.read{offset,length}`, `files.write{mode,append}`.
- `files.move` takes `{sandbox_id, source, destination, overwrite?}` (a plugin may also accept `src`/`dest`).
- `exec.start` returns a **string** `process_id`. The `pid` of `process.kill|signal|stdin` is an opaque id: either the integer `pid` of a `process.list` entry or that string; `ProcessInfo.pid` and `commands.kill(pid)` accept both.
- Unknown error `sdk_code` values fall back to the EPP code's default class. The accepted values are the SDK error codes the host maps, for example `E1001` (bad credentials), `E2000`/`E2001` (sandbox/template not found), `E3001` (command timeout) and `E4001` (file not found); see the [error code reference](../reference/error-codes.md). A bare `-32002` for a missing **file** becomes E8005, so send `sdk_code: "E4001"`; a bare `-32002` for an unknown sandbox on `sandbox.get`/`connect`/`set_timeout`/`pause`/`resume` becomes E2009 (a plugin may also say `sdk_code: "E2009"`).
- Manifest defaults are **delivered** in `initialize.config`. Do not put a default on a field that has an alternative (`base_url` next to `domain`): the default would always win.
- `$/cancel {id}` for a running request means: stop the work (kill the spawned process) and answer with an error or the final result.

### What reaches `sandbox.create`

`Sandbox.create(..., provider="my-cloud", provider_options={...}, secure=...)` sends:

| Param | When |
|---|---|
| `template`, `timeout`, `metadata`, `envs`, `cpu`, `memory`, `disk`, `gpu`, `request_timeout` | always |
| `secure` | only when the caller passed `secure=True/False`; absent otherwise, so the plugin's own default applies (the built-in provider behaves as `secure=True`) |
| `options` | the `provider_options` the caller passed (declared config fields only), **without secret fields**; use them for per-create settings such as a network policy, platform or image pull settings |

`sandbox.network.get_url(port)` stays a local, synchronous computation. `await sandbox.network.resolve(port)` returns `(url, headers)` and `await sandbox.network.resolve_url(port)` the URL; both ask the plugin's `ports.url` when the provider declares it and fall back to the local computation otherwise.

`sandbox.commands.start()` (and `run(..., background=True)`) returns a lazy stream for **every** provider: nothing is sent until the stream is iterated. To start work and not wait, run `nohup ... &` through `commands.run(..., shell=True)`, or use the `sessions` feature.

### Configuration and credentials

Each provider has its own scoped keys: `ABX_<PROVIDER>_<KEY>` in the environment or `.env`, `[providers.<id>]` in `config.toml`, `provider_options={...}` in the SDK. The provider receives only the keys its manifest declares, in the `initialize` request. Secrets are never put in the plugin's argv or environment.

The generic keys `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` (`ABX_SANDBOX_API_KEY` and `ABX_SANDBOX_BASE_URL`) belong to the built-in provider. A plugin gets them only if its manifest lists them in `[core] inherit` **and** you consented at install or update time. The consent screen names the keys. Your LLM, GitHub and MCP keys are never delivered to a provider.

### What the host does to the plugin process

This is the `exec` child process. A `node` provider is loaded in the Node host (the CLI in-process, or `abx provider engine serve` for the Python SDK). It is not spawned this way.

- Starts it with a scrubbed environment: `PATH`, `HOME`, temp and locale variables, names listed in `env_passthrough`, and `ABX_PROVIDER_DATA_DIR`. No `ABX_*`, `E2B_*`, `ALICLOUD_*`, `GITHUB_TOKEN` or `OPENAI_*` leak in. The working directory is the plugin's `data/` directory.
- Limits a protocol line to 8 MiB and keeps the last 64 KiB of stderr for crash messages. Values it sent in `initialize` are redacted from captured stderr and errors.
- Applies timeouts (default 10 s to start, 60 s per call) and kills the whole process group on timeout, crash or close.
- Retries only idempotent methods, and only on errors the plugin marks `retryable`.

> **No isolation.** A plugin is third-party code that runs with your user privileges and your credentials for that provider. Install only code you trust. Pinning, digest verification and consent narrow the risk; they do not sandbox the process. The `[security]` block is a declaration shown to you, not a restriction.

### Errors

The host maps plugin errors onto the existing exception hierarchy, so scripts see the same exception types and CLI exit codes for every provider.

| EPP code | Raised as | CLI exit |
|---|---|---|
| `-32001` unauthenticated | `AuthenticationError` family (E1xxx) | 3 |
| `-32002` not found | `SandboxNotFoundError` (E2009) for a `sandbox.*` call on an existing id; otherwise `ProviderResourceNotFoundError` (E8005), or the class named by `data.sdk_code` | 4 |
| `-32003` feature not supported | `ProviderFeatureNotSupportedError` (E8004) | 1 |
| `-32004` quota exceeded | `QuotaExceededError` | 6 |
| `-32005` timeout | `ProviderTimeoutError` (E8022) or `CommandTimeoutError` | 5 |
| `-32006` invalid params or config | `ProviderConfigError` (E8002) | 2 |
| `-32000` other failure | class by `data.sdk_code`, else `ProviderError` (E8000) | 1 |
| JSON-RPC standard codes | `ProviderProtocolError` (E8020) | 1 |

The full E8xxx list is in the [error code reference](../reference/error-codes.md#e8xxx--provider-errors-providererror).

### Testing a plugin

Three ways to run the contract suite, from least to most work. The suite only exercises the features the plugin declares and skips the rest (a skipped test is not a failure).

```bash
# 1. One command, no test file. Fails when nothing was collected.
python -m agent_sandbox.providers test my-cloud --option base_url=http://127.0.0.1:8080
python -m agent_sandbox.providers test my-cloud -- -k exec -x      # extra pytest arguments after --

# 2. Plain pytest, no test file
pytest -p agent_sandbox.providers.testing --pyargs agent_sandbox.providers.contract \
       --provider-under-test my-cloud --provider-option base_url=http://127.0.0.1:8080
```

```python
# 3. A subclass in your plugin's own tests
from agent_sandbox.providers.testing import ProviderContractTests

class TestMyProvider(ProviderContractTests):
    provider_id = "my-cloud"          # an installed provider
    provider_options = {}
```

(`--provider-under-test` and `--provider-option KEY=VALUE`, repeatable, are registered when `agent_sandbox.providers.testing` is loaded as a pytest plugin with `-p`. `ABX_PROVIDER_UNDER_TEST` sets the default. With no provider selected the suite **fails** instead of skipping.)

What it checks: declared features are known; secret fields have no default; lifecycle (create, connect, list, kill, unknown id is `E2009`); `kill` is idempotent; `set_timeout`; pause and resume; `exec.run` exit codes, stderr and env; streamed output order with exactly one final `exit`; that a command timeout is enforced; process listing; files (text, binary, unicode, directories, move, remove, missing file is a typed not-found); `ports.url`; that features you did **not** declare fail with E8004 (a `CapabilityNotSupportedError`); and that secret option values never appear in error text.

Offline testing: the kit needs a working backend. For a plugin that talks to HTTP, write a small mock server and drive the plugin over stdio with a tiny JSON-RPC client. The [opensandbox plugin](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox) has both (`tests/mock/`, `tests/epp-client.mjs`).

Check an installed provider's wiring without running a sandbox:

```bash
python -m agent_sandbox.providers doctor my-cloud          # manifest, digest, handshake, credentials
python -m agent_sandbox.providers doctor my-cloud --no-handshake
```

Running `pytest` from a directory that has an unrelated `conftest.py`? Add `--noconftest` (or `--confcutdir`). `python -m agent_sandbox.providers test` already isolates itself from the current directory's pytest configuration.

---

## Python providers in code (SDK only)

```python
from agent_sandbox.providers import Provider, register_provider

class MyProvider(Provider):
    id = "my-cloud"
    ...

register_provider(MyProvider())
```

A package can also publish an entry point in the group `agent_sandbox.providers` that points to a `Provider` instance or a zero-argument factory; it is loaded the first time providers are listed. These providers run in your process with full trust, so they cannot be installed by `abx provider install`.

---

## See also

- [Configuration reference](../reference/configuration.md) — names, aliases, precedence
- [Authentication](authentication.md)
- [Design: providers and credentials](../design/providers-and-credentials.md)

Native terminal access enforces the provider's `pty` declaration before reading
session context or starting its wire adapter. An unsupported terminal returns the
typed provider feature error; declaring a client method does not enable an account
or function capability.
