# opensandbox provider plugin

[简体中文](README.zh-CN.md)

An [EPP/1](../../../docs/en/design/providers-and-credentials.md) **exec provider** that runs Easy
Sandbox sandboxes on an [OpenSandbox](https://github.com/opensandbox-group/OpenSandbox) server
(Docker or Kubernetes runtime). It works unchanged from the Python SDK (`Sandbox.create(provider="opensandbox")`)
and from the `ebx` CLI (`ebx --provider opensandbox ...`).

* Runtime: **Node.js >= 20, no npm dependencies** (built-in `fetch`). Chosen because the `ebx` CLI is a
  Node program, so every `ebx` user already has Node; the Python SDK needs `node` on `PATH` to use it.
* Design and API mapping: [`provider-opensandbox-mapping.md`](../../../docs/en/design/provider-opensandbox-mapping.md).
* Authoring review that produced this plugin: [`provider-authoring-evaluation.md`](../../../docs/en/design/provider-authoring-evaluation.md).

## Install

```bash
python -m easy_sandbox.providers install examples/providers/opensandbox --yes   # or: ebx provider install <path|git-url>
python -m easy_sandbox.providers doctor opensandbox
```

From git, pin a commit (`file://` or other plain-text transports additionally need
`--allow-insecure-transport`):

```bash
ebx provider install https://example.com/you/ebx-provider-opensandbox.git --ref <40-hex-commit>
```

Installing does not execute anything; the plugin runs only when a command uses it, and its files are
re-hashed against the install receipt before every start.

## Configure

Every field can be set with the canonical `EBX_OPENSANDBOX_<FIELD>` variable, in `~/.ebx/config.toml`
under `[providers.opensandbox]`, or (where listed) with the OpenSandbox-native variable. Canonical names win.

| Field | Native alias | Default | Meaning |
|---|---|---|---|
| `base_url` | | `http://127.0.0.1:8080` | Server root (a trailing `/v1` is accepted) |
| `api_key` (secret) | `OPEN_SANDBOX_API_KEY` | none | Sent as `OPEN-SANDBOX-API-KEY`; a local server may need none |
| `domain`, `protocol` | `OPEN_SANDBOX_DOMAIN`, `OPEN_SANDBOX_PROTOCOL` | `http` | `host[:port]` alternative to `base_url` |
| `use_server_proxy` | `OPEN_SANDBOX_USE_SERVER_PROXY` | `false` | Route sandbox traffic through the server proxy |
| `default_image` | | `python:3.12-slim` | Image for the generic template `base` |
| `image_aliases` | | `code=opensandbox/code-interpreter:v1.1.0` | `name=image,...` short template names |
| `entrypoint` | | `tail -f /dev/null` | Keep-alive command for generic images |
| `ready_timeout` | | `60` | Seconds to wait for Running + execd |
| `registry_username`, `registry_password` (secret) | | none | Private registry auth |
| `network_policy` | | none | JSON NetworkPolicy for every new sandbox (overridable per create) |
| `platform` | | none | `linux/amd64`, `linux/arm64`, ... |
| `secure_access` | | `false` | Kubernetes gateway secure access |

The template argument of `Sandbox.create(template=...)` is resolved as: alias, then `base` -> `default_image`,
otherwise used as an image reference verbatim.

## Capabilities

| Feature | Status | Notes |
|---|---|---|
| `sandbox.lifecycle` | yes | create (waits for Running and execd, kills on failure), connect, get, list (paged), kill (idempotent) |
| `sandbox.timeout` | yes | `set_timeout`; OpenSandbox's 60 s minimum is clamped; the new expiry is derived from the server clock |
| `sandbox.pause` | yes | pause / resume (Docker runtime) |
| `exec.run`, `exec.stream` | yes | env, cwd, user, stdin, timeout; ordered `exec.output` / one `exec.exit`; `$/cancel` stops the command |
| `process.manage` | partly | `process.list`; `process.kill` / `process.signal` (numeric pid: any signal; execd command id: SIGKILL only); `process.stdin` is `E8004` |
| `files.rw` | yes | read (offset/length), write (mode), list, stat, mkdir, remove, move, plus `files.search` and `files.chmod` extensions (not called by any host yet) |
| `ports.url` | yes | `ports.url` method (direct endpoint, or the server proxy with `use_server_proxy`) |
| `sessions` | yes | detached commands through the `detached` extension of `exec.start` (no host adapter sends it yet) |
| `pty`, `code.interpret`, `templates.*`, `files.watch`, transfer URLs | no | `E8004` (`-32003`) |

## Test

```bash
node tests/run.mjs                      # 24 unit + 21 mock-server tests, no server needed
```

Live tiers need a reachable OpenSandbox server (see `../../e2e/opensandbox/README.md` for a one-command
local setup):

```bash
export EBX_OPENSANDBOX_BASE_URL=http://127.0.0.1:8080
export OPEN_SANDBOX_API_KEY=...         # whatever your server expects
OPENSANDBOX_LIVE=1 node tests/run.mjs live                         # plugin over EPP/1 directly
OPENSANDBOX_LIVE=1 python -m pytest tests/contract                 # contract kit + SDK scenarios
python ../../e2e/opensandbox/provider_e2e.py                       # everything, in a throwaway HOME
python ../../e2e/opensandbox/provider_install_e2e.py               # install / update / uninstall flows
```

`tests/contract` needs `easy_sandbox` importable and `pytest`; it installs the plugin into a temporary
`~/.ebx` and never touches your real store.

## Layout

```
ebx-provider.toml   manifest (runtime, features, security, config schema)
provider.mjs        entry: EPP dispatcher and capability wiring
src/                http.mjs (lifecycle + execd client), sandbox.mjs, exec.mjs, files.mjs,
                    sse.mjs, multipart.mjs, convert.mjs, config.mjs, errors.mjs, epp.mjs
tests/              unit/, mock/ (in-process fake server), live/, contract/ (pytest)
```

## Known limits

* File reads/writes are limited by EPP's 8 MiB line limit (reads are capped at 4 MiB per call; use `offset`/`length`).
* `secure=True` passed to `Sandbox.create` requests gateway "secure access" (Kubernetes gateway deployments only; a Docker server refuses it). `secure=False` and an omitted `secure` leave it off, or use the `secure_access` config field for a global default.
* Per-create settings: `provider_options={"network_policy": ..., "platform": ..., "default_image": ...}` given to `Sandbox.create` override the configured values for that sandbox only (whitelist: `default_image`, `image_aliases`, `entrypoint`, `ready_timeout`, `registry_username`, `registry_password`, `network_policy`, `platform`, `secure_access`; never the server address or API key).
* `commands.start()` is lazy for every provider (nothing is sent until the stream is iterated); run `nohup ... &` through `commands.run(..., shell=True)` to start a background process.
* Legacy execd v1.1.0 lacks `argv` and strips line endings; the plugin detects it and falls back (use a newer execd image for exact output).

Licensed under Apache-2.0.
