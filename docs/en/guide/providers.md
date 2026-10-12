# Providers

> **Note:** The `ebx provider ...` commands on this page are provided by the Node.js CLI in the `cli` repository. Python-only users get the same operations from `python -m easy_sandbox.providers ...`. Both use the same install directory, the same receipts and the same tree digest.

A **provider** is a sandbox backend. Easy Sandbox ships one built-in provider and can load more from plugins.

| Id | Name | Kind | Default |
|---|---|---|---|
| `alicloud-express` | Alibaba Cloud Express Edition (阿里云极速版) | built-in | yes |

If you never touch providers, nothing changes: every command, every output and every environment variable behaves as before. The id `alicloud-express` is stable. Only the display name may change.

---

## Choosing a provider

Highest priority first:

| Where | Example |
|---|---|
| SDK argument | `await Sandbox.create(provider="my-cloud")` |
| CLI flag | `ebx create --provider my-cloud` |
| Process environment | `export EBX_PROVIDER=my-cloud` |
| `./.env` | `EBX_PROVIDER=my-cloud` |
| `~/.ebx/.env` | `EBX_PROVIDER=my-cloud` |
| `~/.ebx/config.toml` | `[core]` `provider = "my-cloud"` (written by `ebx provider default my-cloud`) |
| Built-in | `alicloud-express` |

```python
from easy_sandbox.api.sandbox import Sandbox

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
ebx provider list
ebx provider default my-cloud       # persist in ~/.ebx/config.toml
ebx provider default                # show the current default
ebx provider default alicloud-express
```

---

## Installing a provider plugin

```bash
ebx provider install ./my-provider                          # a local directory
ebx provider install https://github.com/acme/ebx-provider-acme.git --ref 3f2c...   # a full commit
ebx provider install git@github.com:acme/ebx-provider-acme.git --ref v1.2.0 --allow-unpinned
ebx provider list
ebx provider info my-cloud
ebx provider update my-cloud --check
ebx provider uninstall my-cloud
```

Without the CLI:

```bash
python -m easy_sandbox.providers install ./my-provider
python -m easy_sandbox.providers list --json
python -m easy_sandbox.providers update my-cloud --check
python -m easy_sandbox.providers doctor my-cloud
python -m easy_sandbox.providers test my-cloud       # the contract suite (needs pytest)
```

### What install does and does not do

- **Nothing from the plugin is executed at install time.** There is no `setup.py`, no postinstall hook and no `git checkout`. Git sources are fetched without a checkout, every entry is validated (regular files only, no symlinks or submodules, size and count limits) and the installer writes the files itself.
- The install shows a **consent screen**: id, version, source, resolved commit, content digest, the command that will run, the declared security block, the features, and the configuration fields. A non-interactive run needs `--yes`.
- A source is **pinned** when you give a full 40-hex commit (`--ref`) or `--sha256 <tree digest>`. A tag or branch is **unpinned**: it could move between your review and the install. Unattended runs refuse unpinned sources unless you pass `--allow-unpinned`.
- Only `https://` and `ssh` git URLs are accepted. URLs with embedded credentials are rejected; use an SSH agent or install from a directory you cloned yourself. `--allow-insecure-transport` enables `file://`, `http://` and `git://` (for tests and development).
- The installed files are recorded in a receipt (`.ebx-install.json`) with a SHA-256 tree digest. The digest is **verified every time the plugin starts**. If a file changed, the command fails with `ProviderIntegrityError` (E8011); reinstall or run `provider update`.
- `--link` makes a development symlink install with no integrity check. It needs confirmation, and every use prints a warning on stderr.

### Update and uninstall

`provider update` re-fetches from the recorded source. If the command, the security block, or the feature list changed, you must consent again. Installs that are **pinned** (a 40-hex commit or `--sha256`) do not move: `update` reports `pinned` and does nothing unless you pass a new `--ref`. `update` takes the same transport and verification flags as `install`: `--ref`, `--check`, `--yes`, `--allow-unpinned`, `--allow-insecure-transport` (the receipt does not remember that you used it; a `file://`, `http://` or `git://` source needs it on every update) and `--no-verify` (skip the post-update handshake). The previous version stays in a trash directory until the new one starts successfully, then it is dropped. If the new version fails (for example its handshake), the previous files **and its `data/` directory** are restored exactly. `provider uninstall` removes the directory; stored settings (`[providers.<id>]`, `EBX_<ID>_*`) stay unless you pass `--purge`. Uninstalling the default provider resets the default to `alicloud-express`.

### Where things live

```text
~/.ebx/providers/
  <id>/
    ebx-provider.toml     # manifest
    ...                   # plugin files
    .ebx-install.json     # receipt: source, commit, digest, consent
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
| `python` | A `Provider` subclass registered in-process | no (pip entry point or `register_provider`) | SDK only |

The `exec` kind is the primary extension point: one plugin works for both the Python SDK and the Node CLI, in any language. A backend that already speaks the E2B envd data-plane protocol only needs to implement the control plane (create, connect, list, kill) and return the envd URL; commands, files and terminals then use the fast native transports. A backend without envd implements the data-plane methods (`exec.run`, `files.*`) as well.

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
| `templates.read`, `templates.build` | list and inspect templates; build, deploy and delete them |
| `ports.url`, `ports.domain` | public URL for a port; custom domains |
| `storage.mount`, `network.vpc` | object-storage mounts; VPC attachment |
| `sessions` | the sandbox survives the process and can be re-attached by id |

`alicloud-express` implements all 18 features. `ebx provider info <id>` shows what a plugin declares.

---

## Writing a provider

A plugin is a directory with `ebx-provider.toml` and the program it runs.

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

[config.fields.workdir_root]             # the plugin's own settings: EBX_LOCAL_PROCESS_WORKDIR_ROOT
type    = "path"
required = false
description = "Directory that holds sandbox working directories"
```

Two working examples are in the repository:

- `examples/providers/local-process/` — an `exec` provider in about 200 lines of Python standard library (lifecycle, commands, files).
- `examples/providers/e2b-compatible/` — a `rest` provider that is only a manifest.
- `examples/providers/opensandbox/` — a complete, dependency-free Node `exec` provider for an [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) server: streaming exec, files, process control, pause/resume and port URLs, with mock-server and live tests.

Development loop: `python -m easy_sandbox.providers install ./my-provider --link --yes` installs a symlink with no digest check, so edits take effect immediately. Run `doctor`, then `test` (below), then install a pinned copy for real use.

### Methods a plugin answers

The wire methods, their parameter names and types, and which are required are listed in the [EPP method table](../design/providers-and-credentials.md#epp-methods) and, machine-readably, in `tests/fixtures/epp-methods.json` of the SDK repository (the CLI keeps an identical copy). In short:

- **Required** for `sandbox.lifecycle`: `sandbox.create`, `sandbox.get`, `sandbox.list`, `sandbox.kill`. `sandbox.connect` is **optional** (use it to resume or re-attach); when a plugin answers `-32601` for it, the host calls `sandbox.get` instead.
- **Per feature**: `exec.run`, `exec.start` (`exec.stream`), `process.list|kill|signal|stdin`, `files.read|write|list|stat|mkdir|remove|move`, `ports.url`, `sandbox.set_timeout`, `sandbox.pause|resume`. Declare a feature only if you implement all of its methods; the host raises E8004 for the rest.
- **Extensions** the host does not call yet but plugins may offer: `files.search`, `files.chmod`, `exec.start{detached}`, `files.read{offset,length}`, `files.write{mode,append}`.
- `files.move` takes `{sandbox_id, source, destination, overwrite?}` (a plugin may also accept `src`/`dest`).
- `exec.start` returns a **string** `process_id`. The `pid` of `process.kill|signal|stdin` is an opaque id: either the integer `pid` of a `process.list` entry or that string; `ProcessInfo.pid` and `commands.kill(pid)` accept both.
- Unknown error `sdk_code` values fall back to the EPP code's default class. The accepted values are the SDK error codes the host maps, for example `E1001` (bad credentials), `E2000`/`E2001` (sandbox/template not found), `E3001` (command timeout) and `E4001` (file not found); see the [error code reference](../reference/error-codes.md). A bare `-32002` for a missing **file** becomes E8005 (sandbox not found), so send `sdk_code: "E4001"`.
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

Each provider has its own scoped keys: `EBX_<PROVIDER>_<KEY>` in the environment or `.env`, `[providers.<id>]` in `config.toml`, `provider_options={...}` in the SDK. The provider receives only the keys its manifest declares, in the `initialize` request. Secrets are never put in the plugin's argv or environment.

The generic keys `sandbox_api_key`, `sandbox_base_url` and `sandbox_domain` (including `E2B_API_KEY` and `E2B_API_URL`) belong to the built-in provider. A plugin gets them only if its manifest lists them in `[core] inherit` **and** you consented at install or update time. The consent screen names the keys. Your LLM, GitHub and MCP keys are never delivered to a provider.

### What the host does to the plugin process

- Starts it with a scrubbed environment: `PATH`, `HOME`, temp and locale variables, names listed in `env_passthrough`, and `EBX_PROVIDER_DATA_DIR`. No `EBX_*`, `E2B_*`, `ALICLOUD_*`, `GITHUB_TOKEN` or `OPENAI_*` leak in. The working directory is the plugin's `data/` directory.
- Limits a protocol line to 8 MiB and keeps the last 64 KiB of stderr for crash messages. Values it sent in `initialize` are redacted from captured stderr and errors.
- Applies timeouts (default 10 s to start, 60 s per call) and kills the whole process group on timeout, crash or close.
- Retries only idempotent methods, and only on errors the plugin marks `retryable`.

> **No isolation.** A plugin is third-party code that runs with your user privileges and your credentials for that provider. Install only code you trust. Pinning, digest verification and consent narrow the risk; they do not sandbox the process. The `[security]` block is a declaration shown to you, not a restriction.

### Errors

The host maps plugin errors onto the existing exception hierarchy, so scripts see the same exception types and CLI exit codes for every provider.

| EPP code | Raised as | CLI exit |
|---|---|---|
| `-32001` unauthenticated | `AuthenticationError` family (E1xxx) | 3 |
| `-32002` not found | `ProviderResourceNotFoundError` (E8005), or the class named by `data.sdk_code` | 4 |
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
python -m easy_sandbox.providers test my-cloud --option base_url=http://127.0.0.1:8080
python -m easy_sandbox.providers test my-cloud -- -k exec -x      # extra pytest arguments after --

# 2. Plain pytest, no test file
pytest -p easy_sandbox.providers.testing --pyargs easy_sandbox.providers.contract \
       --provider-under-test my-cloud --provider-option base_url=http://127.0.0.1:8080
```

```python
# 3. A subclass in your plugin's own tests
from easy_sandbox.providers.testing import ProviderContractTests

class TestMyProvider(ProviderContractTests):
    provider_id = "my-cloud"          # an installed provider
    provider_options = {}
```

(`--provider-under-test` and `--provider-option KEY=VALUE`, repeatable, are registered when `easy_sandbox.providers.testing` is loaded as a pytest plugin with `-p`. `EBX_PROVIDER_UNDER_TEST` sets the default. With no provider selected the suite **fails** instead of skipping.)

What it checks: declared features are known; secret fields have no default; lifecycle (create, connect, list, kill, unknown id is `E8005`); `kill` is idempotent; `set_timeout`; pause and resume; `exec.run` exit codes, stderr and env; streamed output order with exactly one final `exit`; that a command timeout is enforced; process listing; files (text, binary, unicode, directories, move, remove, missing file is a typed not-found); `ports.url`; that features you did **not** declare fail with E8004 (a `CapabilityNotSupportedError`); and that secret option values never appear in error text.

Offline testing: the kit needs a working backend. For a plugin that talks to HTTP, write a small mock server and drive the plugin over stdio with a tiny JSON-RPC client; `examples/providers/opensandbox/tests/` has both (`tests/mock/`, `tests/epp-client.mjs`).

Check an installed provider's wiring without running a sandbox:

```bash
python -m easy_sandbox.providers doctor my-cloud          # manifest, digest, handshake, credentials
python -m easy_sandbox.providers doctor my-cloud --no-handshake
```

Running `pytest` from a directory that has an unrelated `conftest.py`? Add `--noconftest` (or `--confcutdir`). `python -m easy_sandbox.providers test` already isolates itself from the current directory's pytest configuration.

---

## Python plugins (SDK only)

```python
from easy_sandbox.providers import Provider, register_provider

class MyProvider(Provider):
    id = "my-cloud"
    ...

register_provider(MyProvider())
```

A package can also publish an entry point in the group `easy_sandbox.providers` that points to a `Provider` instance or a zero-argument factory; it is loaded the first time providers are listed. These providers run in your process with full trust, so they cannot be installed by `ebx provider install`.

---

## See also

- [Configuration reference](../reference/configuration.md) — names, aliases, precedence
- [Authentication](authentication.md)
- [Design: providers and credentials](../design/providers-and-credentials.md)
