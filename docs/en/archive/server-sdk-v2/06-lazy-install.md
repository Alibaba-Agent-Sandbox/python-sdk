# 06 - Lazy installation, manifests and the `agent-sandbox-server` command

> Status: archive. Not the current specification.

> **Status: target design, not implemented.** The shipped server uses endpoint ids and one policy engine; see [README](README.md) section 1 for what exists and section 2 for what does not.

> Part of [Server SDK v2](README.md). Rule R6. Replaces the in-flight `npm i -g` / `curl | bash` /
> `POST /agents/runtimes/{name}/install` mechanism and the "install at image build always" habit of templates.
> **v2.1** (independent reviews IF-20..IF-25, IS-L1..L5, C-11): the lock is no longer taken before the marker check and never
> lives on a read-only tree; a slow install answers **202 + job id** instead of blocking up to 10 minutes; **`prepare` at build time is the
> recommended path on FC / the Alibaba Cloud base image**; the build snippet is PEP 668 safe; noexec and no-network are probed;
> installation is decided by `deny(install)` for session creation too. Changes are marked **(v2.1)**.

## 1. Requirements

1. **Never download a tool unless an enabled operation that needs it is called** (or an operator ran `prepare`).
2. Build time can pre-install exactly what the configuration needs (`prepare`), derived from the enabled ops - no
   hand-maintained package lists in Dockerfiles.
3. First-use installs are **safe**: authorized first, locked, checksummed, staged and atomically published, observable,
   offline-capable, mirror-capable, and work on a read-only root filesystem when one writable tools directory exists.
4. Nothing runs `curl | bash`, `npm install -g`, `pip install` into the system, or `sudo`.
5. Works on the Alibaba Cloud Agent Sandbox base image (user `user`, HOME `/home/user`, entrypoint gateway as PID 1,
   `python3` on PATH, `node` only conditionally present, PEP 668 Python).
6. **(v2.1)** Works on a **read-only root filesystem with no writable tools directory** by failing fast and clearly
   (`install.read_only` listing the directories tried, remedy `agent-sandbox-server prepare` at build time), never by hanging.

## 2. Vocabulary

| Term | Meaning |
|------|---------|
| **tool** | something installable: `codex`, `claude_code`, `qwen_code`, `cursor`, `node-runtime`, `playwright-chromium`, user tools |
| **manifest** | JSON describing how to install a tool *reproducibly* (below). Shipped in the wheel under `install/manifests/`; users add their own via `install.manifests` paths |
| **requirement** | an op's `install=("codex",)` declaration: tool names the op needs before its handler runs |
| **tools dir** | writable root where tools live; resolved at start (section 5) |
| **prepare** | CLI step that installs the tools required by a configuration ahead of time |

## 3. Manifest schema (v1)

```json
{
  "schema": 1,
  "name": "codex",
  "binary": "codex",
  "version": "0.158.0",
  "description": "OpenAI Codex CLI",
  "requires": ["node-runtime"],
  "source": {
    "type": "npm-lock",
    "package": "@openai/codex",
    "lock": "codex/package-lock.json",
    "package_json": "codex/package.json",
    "bin": "node_modules/.bin/codex",
    "allow_scripts": false
  },
  "hosts": ["registry.npmjs.org"],
  "verify": {"argv": ["{bin}", "--version"], "expect": "0.158", "timeout": 20},
  "platforms": ["linux-x64", "linux-arm64"],
  "size_hint_mb": 90
}
```

Source types (closed list; adding one needs a design review):

| `source.type` | How it installs | Integrity |
|---------------|-----------------|-----------|
| `npm-lock` | `npm ci --ignore-scripts --omit=dev --no-audit --no-fund --prefix <staging>` with the shipped `package.json` + `package-lock.json`; `bin` is relative to the prefix | lockfile `integrity` (sha512) per package; `npm ci` fails on mismatch |
| `tarball` | download `url` (per platform), verify, extract with a safe extractor (rejects absolute paths, `..`, links escaping the dir, device files; size caps) | `sha256` per platform, **mandatory** |
| `pip-hashes` | `python3 -m pip install --target <staging> --no-deps --require-hashes -r <requirements-with-hashes>`; entry via `python3 -m` | hashes in the requirements file; `--target` avoids PEP 668 and the system site-packages |
| `playwright-browser` | after `pip-hashes` of `playwright`, `PLAYWRIGHT_BROWSERS_PATH=<staging>/browsers playwright install chromium` | Playwright's own revision pins; version pinned by the wheel hash |
| `system` | not installed by the server: the tool must exist on PATH (`doctor` reports); `prepare` may only *check* | n/a |

Example `tarball` (the `cursor` agent; derived from the vendor installer, which downloads a versioned tarball - the
manifest replaces `curl | bash`):

```json
{"schema": 1, "name": "cursor", "binary": "cursor-agent", "version": "2026.10.01-e373342",
 "source": {"type": "tarball", "bin": "cursor-agent",
   "platforms": {"linux-x64": {"url": "https://downloads.cursor.com/lab/2026.10.01-e373342/linux/x64/agent-cli-package.tar.gz",
                               "sha256": "<pinned at release by `agent-sandbox-server lock cursor`>"},
                 "linux-arm64": {"url": "…/linux/arm64/agent-cli-package.tar.gz", "sha256": "<pinned>"}}},
 "hosts": ["downloads.cursor.com"], "verify": {"argv": ["{bin}", "--version"], "timeout": 20}}
```

Pins (sha256, lockfiles) are produced by `agent-sandbox-server lock <tool> [--version V]` on a connected machine in CI,
reviewed in a PR, and shipped; a manifest with a missing digest does not load (`install.manifest_invalid`). There is
**no trust-on-first-use mode**; a deliberate escape hatch for development is `ABX_INSTALL_UNPINNED=1` which prints a
loud warning, is refused when `ABX_SERVER_ENV=production`, and is audit-logged.

`requires` forms a DAG (`codex` -> `node-runtime`); cycles are a manifest error. `node-runtime` is a `tarball` manifest of the
official Node distribution (nodejs.org / mirror, sha256 pinned) and is skipped when `node >= required` is already on PATH.

## 4. Declaring requirements and the first-use flow

* Ops declare `install=("codex",)`; the agents runtime declares them from the adapter's `manifest`.
  Read-only ops (`agents.codex.sessions.get/items/events`) declare **none**: reading a journal never installs anything.
* The pipeline step 8 (02 section 6) is extended: **after authorization and admission**, for each requirement the
  installer's `ensure(name)` runs. Therefore **an unauthorized or unmounted call can never trigger a download**; downloads are
  attributable (audit record `install.start/finish` with the triggering principal and op).
* `ensure` result states: `ready` (go on), `pending` (an install job is running: **202**, below), `missing` (mode forbids
  installing: `424 install.required`), `failed` (`502 install.failed` with `details.phase`), `read_only` (`503 install.read_only`),
  `disabled` (modes `off`/`offline` without cache: `424 install.disabled`), `network_unreachable` (cached probe, below).
* **Install is its own policy decision (v2.1, IS-L2).** Creating an agent session whose adapter is not installed performs an install, so
  `agents.<a>.sessions.create`, `.run` and `.sessions.send_event` are admitted only when `agents.<a>.install` is **not denied** for the
  principal (a `deny(ops.agents.codex.install)` is "never download for this principal", and it is absolute) and the install mode permits it.
  Mounting `install` explicitly (`allow(ops.agents.codex.install)`) is only needed to expose the admin endpoint `POST .../install`
  (progress, `reset`); it is not a precondition of a first-use install triggered by an authorised session call.
* **Wait semantics (v2.1, IF-21, C-11; replaces the 10-minute blocking default).** The installer runs on a job thread. The calling request waits
  at most `install.wait` (default **20 s**, `0` = never wait). If the job is not finished the call returns **`202 Accepted`** with
  `{"object":"install.job","id":"ij_...","status":"pending","phase":...,"retry_after":5}` and `Retry-After: 5`; the same call may simply be
  repeated (idempotent: it joins the running job) and `GET /ops/agents.<a>.install` (or `GET /v1/agents/runtimes/<a>`) reports `{phase, bytes, total}`.
  On the OpenAI wire the session is created in status `in_progress` with a pending `agent.session.environment.pending` event instead of blocking the POST,
  which keeps the official SDK's subscribe-before-send flow and gateway timeouts (typically 30-60 s) working. A **gateway-safe** deployment sets
  `mode: build` and runs `prepare` in the image build (section 8); then no request ever installs.
* **Locking (v2.1, IF-20, IS-L5).** Order: (1) lock-free fast path: marker present and manifest sha256 equal; trees not owned by root re-verify a tree digest
  (a user-writable tools dir cannot be trusted on the marker alone); `ready` returns without touching any lock or any writable location, so a read-only
  image with a prepared tool never needs one. (2) Only if not ready: pick the first **writable** directory of the chain and take the flock **there**, in
  `<dir>/.locks/` (never next to the marker in a read-only tree). (3) Re-check the marker under the lock.
* **Failure backoff**: a failed tool is not retried for 30 s (exponential to 10 min) to prevent retry storms; `prepare --force`
  or `install.reset` (admin op `agents.<a>.install`) clears it.

## 5. Modes and the tools directory

`install.mode` (config `install:`; env `ABX_SERVER_INSTALL_MODE` **(v2.1, N-5: one prefix; `ABX_INSTALL_MODE` is accepted as a deprecated alias)**):

| Mode | Behaviour |
|------|-----------|
| `lazy` | install on first use of a requirement (202 + job when slow); also usable with `prepare`. **Default: `lazy` for development and `serve` on a writable HOME; `build` is the recommended mode for FC and the base image** (the template builder sets it, 08 section 4). `doctor` states the effective mode and why |
| `build` | the runtime **never** installs; missing tools -> `424 install.required` ("run `agent-sandbox-server prepare` at build time"); for hardened images |
| `offline` | like `lazy` but only from the local cache / mirror dir (`ABX_INSTALL_CACHE`, `install.mirrors.tarball` with `file://`), never the internet; nothing cached -> `install.disabled` |
| `off` | no tool management: tools must be on PATH; `install.*` ops are unmounted; a missing tool -> `install.disabled` |

Restrict-only layers (03 section 10) can force `build` or `off` (`ABX_SERVER_INSTALL_MODE=build` in the restrict env class).
`auto` was considered and **rejected** (ambiguous: "does it install or not here?"); `doctor` states the effective mode.

Tools directory resolution (first match that exists and is writable, else the first non-writable existing one, read-only):

1. `$ABX_TOOLS_DIR`
2. `/opt/agent-sandbox/tools` (build-time default; root-owned in the official image; used read-only at runtime when prepared)
3. `~/.local/state/agent-sandbox/tools` (runtime default for user `user`: `/home/user/.local/state/agent-sandbox/tools`; `/var/lib/agent-sandbox/tools` when running as root) **(v2.1, IS-L1)**
4. no `/tmp` fallback by default **(v2.1)**: `/tmp` is inside the most common file scope and world-writable. `install.allow_tmp: true` re-enables
   `$TMPDIR/agent-sandbox-<uid>/tools` (mode 0700, owned by the server user, verified at use) for ephemeral sandboxes; `doctor` warns.

The chain is searched in order for a **verified installed** tool (read) and the first **writable** directory receives new installs. If no directory is
writable and the tool is not installed anywhere: `503 install.read_only` with `details.tried` (the directories) and the fix. The directory
must satisfy the same rules as the state dir (03 section 15.2: mode 0700, owner = server user, not group/world writable) or `config.state_dir_unsafe`.
Tool and state directories are added to the **non-removable system deny list** of every path scope (`protect_dir`), so no `PathScope("/")`-style grant
and no agent file scope can read or overwrite them (IS-L1).

Layout:

```
<tools>/
  bin/<binary>                      -> ../<name>/<version>-<platform>/<bin>   (symlinks; this dir is prepended to the agent child PATH only)
  <name>/<version>-<platform>/...   installed tree (immutable after publish)
  <name>/.installed.json            marker: manifest sha256, version, artifact digests, time, installer version, SBOM rows
  <name>/.progress.json             {phase, bytes, total, started, pid}
  .locks/<name>.lock                flock file
  .cache/<sha256>                   content-addressed downloads (shared with offline mode)
  .staging/<name>-<random>/         in-progress installs
```

The tool resolver order for a binary (v2.1, IS-L3: `ABX_TOOL_<NAME>` is read **once from the server's own startup environment**, never from request or
child environments, and the target must be owned by the server user or root and not group/world writable; PATH entries that are world-writable are skipped):
explicit `ABX_TOOL_<NAME>` path > `<tools>/bin` > PATH (only when
`install.use_path=true`, default **true** for tools present on PATH with a satisfying `--version`; so images that already
ship `codex` keep working and nothing is downloaded) > install. The server **never** adds the tools dir to its own or the
callers' global PATH; adapters pass absolute binary paths.

## 6. Install algorithm (normative)

0. **Fast path (v2.1, IF-20).** Marker + manifest digest verify, no lock, no writes: `ready`. Otherwise continue.
0b. **Probes (v2.1, IF-23, IF-24).** Once per process and cached 60 s: the staging filesystem must be writable and **not `noexec`** (a one-byte
   executable is created and `exec`ed under the target dir; failure -> `install.noexec` naming the mount and suggesting `ABX_TOOLS_DIR`); for non-`tarball`-from-cache sources a
   TCP connect probe (2 s) to the first manifest host or mirror; failure -> `install.network_unreachable` immediately (no 60 s urllib timeouts) with the mirror/offline hint.
1. Acquire `fcntl.flock(LOCK_EX)` on `<writable-dir>/.locks/<name>.lock` (blocking with 1 s polls so waiters can report `.progress.json`;
   `flock` is released by the kernel when a crashed installer dies, so there are **no stale locks**). Lock-wait is bounded by the job, not the request.
2. Re-check the marker under the lock (another process may have finished): marker present, manifest sha256 equal, `verify`
   passes -> `ready`.
3. Resolve `requires` recursively (same procedure, locks acquired in name-sorted order; no cycles by construction).
4. Create `.staging/<name>-<rand>/` on the same filesystem as the final path (so `rename` is atomic). Disk space check:
   `size_hint` x 2 free, else `install.no_space`.
5. Fetch (per type) from the manifest's `hosts` only (HTTPS only; redirects must stay within `hosts` or `install.mirrors`),
   with timeouts (connect 15 s, read 60 s, total `install.timeout`), size cap (`max_download_mb`, default 500), into
   `.cache/<sha256>` if not already cached; verify digest **before** extraction; on mismatch delete and fail
   `install.checksum_mismatch`.
6. Extract/install into staging with a scrubbed environment (`PATH`, `HOME`=staging, `npm_config_*` from mirrors only; no
   inherited secrets), no network after fetch for `tarball`; `npm ci --ignore-scripts` is the only step that may reach the registry.
   **(v2.1, IS-L4)** `hosts` cannot be enforced inside `npm ci` or the Playwright downloader, so the scrubbed environment points both at the
   configured mirror/registry only (`npm_config_registry`, `PLAYWRIGHT_DOWNLOAD_HOST`) and `lock` validates that every `resolved` URL in the lockfile and every
   Playwright revision host is in `hosts`+integrity before the manifest is accepted (`install.manifest_invalid` otherwise); the doc states this as
   "hosts is a manifest-review property for `npm-lock`, enforced for `tarball`".
7. Run `verify.argv` (timeout) with the scrubbed environment; failure -> `install.failed` (`details.phase = "verify"`).
8. Write `.installed.json` (with the tree digest); `os.replace(staging, final)` (atomic publish; exactly one installer wins under concurrency, losers see `ready`); update `bin/` symlinks atomically (`symlink` temp + `rename`).
9. Delete staging on any failure; release lock; emit audit `install.finish` (digests, duration, bytes).

Interruption safety: a crash between steps leaves only `.staging/*` (garbage-collected by the next installer when older than
1 h) - the final path is never half-written.

## 7. Mirrors, offline and caching

* `install.mirrors`: `{"npm": "https://registry.npmmirror.com", "tarball": ["https://mirror.example/{host}/{path}", "/mnt/cache"]}`; env
  `ABX_INSTALL_NPM_REGISTRY`, `ABX_INSTALL_MIRROR`. Mirrors are safe because digests are pinned in the manifest/lockfile - a hostile mirror
  can cause a failure, not a compromise. `hosts` still applies to the *original* URL; mirror hosts must be listed in `install.allow_hosts`.
* **Regional note for Alibaba Cloud**: sandboxes in mainland regions commonly cannot reach `registry.npmjs.org` quickly; recommended
  defaults for those images are `npmmirror` for npm and a regional OSS bucket for tarballs, set in the template's `server.install.mirrors`.
* **Offline**: `prepare --cache-only` fills `.cache` from a connected machine/CI; `mode: offline` consumes it. Cache keys are sha256, so a
  cache can be shipped as an image layer or a mounted volume.
* Proxies: honour `HTTPS_PROXY`/`NO_PROXY` (stdlib `urllib` does).

## 8. `prepare`: derive installs from configuration

`agent-sandbox-server prepare [--config server.json] [--only NAME ...] [--cache-only] [--dry-run] [--json]`

1. Load the configuration in **introspection mode** (`ABX_SERVER_INTROSPECT=1`): resolves policy, registry, adapter set; opens no
   sockets, spawns nothing, reads no secrets, imports no heavy optional modules (adapters are described, not executed).
2. Compute the **mounted** ops for *any* principal; collect `install=` requirements of those ops; add `requires`; subtract tools already
   satisfied by PATH.
3. `--dry-run` prints the plan with sizes/hosts/versions; otherwise install in dependency order using the same algorithm as runtime.
4. Exit code 0 (all ready), 3 (some failed), 2 (config error).

Dockerfile pattern (official base image; **PEP 668 safe**, v2.1, IF-22). The base image's Python is "externally managed", so a bare `pip install`
fails; the build injection (08 section 4) emits exactly this, with the wheel copied from the **build context** at the version pinned by the SDK
(never `pip install agent-sandbox-server` from an index, which ignores `docker_builder` and the lockstep version):

```dockerfile
FROM fc-e2b-registry.<region>.cr.aliyuncs.com/runtime/base:<tag>
USER root
COPY agent_sandbox_server-<ver>-py3-none-any.whl /opt/build/
RUN pip install --no-cache-dir --break-system-packages /opt/build/agent_sandbox_server-<ver>-py3-none-any.whl \
    && rm -rf /opt/build
#   alternative without --break-system-packages: python3 -m venv /opt/agent-sandbox/venv && /opt/agent-sandbox/venv/bin/pip install ... (start_cmd then uses the venv)
COPY server.json /etc/agent-sandbox/server.json
ENV ABX_TOOLS_DIR=/opt/agent-sandbox/tools
RUN agent-sandbox-server prepare          # recommended on FC: build-time install, then mode=build at runtime
USER user
```

Option A (small image, first-use install, development only): omit the `prepare` line and set `server.install.mode: lazy`; the first agent call answers 202 and
installs in the background.
Option B (self-contained image, **recommended for FC**): keep `prepare`; the template compiler sets `install.mode: build`.

`abx template build` runs the equivalent automatically when `server.install.mode: build` (08).

## 9. The `agent-sandbox-server` command

`agent-sandbox-server` = `python -m agent_sandbox.server` (stdlib `argparse`; no color/IO dependencies). Default subcommand: `serve`.

| Subcommand | Purpose | Key options | Exit |
|------------|---------|-------------|------|
| `serve` | start the server | `--host --port --pty-port --config --policy --preset NAME --paths P --require-auth --load MODULE --commands FILE` | runs; 2 config error |
| `init` | write a starter `server.yaml` (and optional Dockerfile fragment) | `--preset NAME [--paths P] [--agents a,b] [--auth tokens] [--dockerfile]` | 0 |
| `describe` | print the registry/catalog/effective ops (offline) | `--json --markdown --ids --namespace N --preset NAME --effective (applies config)` | 0 |
| `check-config` | validate + lint a config; print effective table | `--config F --strict (warnings fail)` | 0 / 1 lint errors / 2 invalid |
| `explain` | explain one decision offline | `--op ID --arg k=v ... --principal id:x --role r` | 0 allowed / 1 denied |
| `prepare` | pre-install tools (section 8) | see above | 0/2/3 |
| `doctor` | environment/readiness report | `--network --json` | 0 ok / 1 warnings / 2 errors |
| `lock` | refresh manifest pins (maintainers/CI) | `NAME [--version V] [--write]` | 0 |
| `gen-client` | emit client code/specs from the registry | `--lang python\|ts\|openapi --out PATH [--module M]` | 0 |
| `healthcheck` | HTTP GET `/health` on 127.0.0.1 (`urllib`, 2 s) for `HEALTHCHECK`/`ready_cmd` | `--port` | 0 / 1 |
| `sbom` | list installed tools with digests | `--json` | 0 |
| `version` | versions + catalog_version + base-image contract | | 0 |

`doctor` checks (each prints PASS/WARN/FAIL with a one-line fix): Python >= 3.10; `/bin/bash` present; `/etc/passwd` writable (base-image
contract); HOME and tools dir writable (and which); effective install mode; installed tools + versions (`--version`, 10 s); manifests
valid; config lint; port 9000/9001 free; optional `--network` reachability of manifest hosts/mirrors (HEAD, 5 s); agent credential
env variables present (names only, never values); read-only root detection (`/proc/mounts`) with advice.

## 10. Read-only filesystems and the Alibaba Cloud Agent Sandbox base image

* The server itself writes only to: tools dir (if installing), the state dir (`ABX_SERVER_STATE_DIR`, default `~/.local/state/agent-sandbox`; journals,
  idempotency keys, rate-limit state; 0700), the audit file (if configured), and `/tmp` for transient scratch only (never state or tools). On a read-only root these must be tmpfs/volumes; `doctor` prints the exact `ABX_*` variables to set. If nothing is writable the
  server still starts: `mode: build` tools work, install ops report `install.read_only`, agents journal falls back to memory
  (replay limited to process lifetime).
* The official image runs the gateway as PID 1 and supervises envd; the server is started by the platform `start_cmd = "agent-sandbox-server
  serve --port 9000"` with `ready_cmd = "agent-sandbox-server healthcheck --port 9000"` (alignment doc). **`serve` never installs anything at start**
  (it would delay readiness and violate R6); the first agent call does, or `prepare` did at build time.
* Python in the image is PEP 668 "externally managed" and may be 3.13: the **runtime** uses `pip --target` only inside the tools dir and never
  touches system site-packages; the **build** step that installs the server package itself is the snippet in section 8
  (`--break-system-packages` or a venv, as root, in the Dockerfile only). `node` may be absent: `node-runtime` is a manifest dependency, not an assumption.
* The root-owned `/opt/agent-sandbox/tools` is the build-time default and is mounted read-only in hardened deployments; runtime `lazy` then
  falls back to `~/.agent-sandbox/tools` for *additional* tools (resolver reads both).
* Open questions that cannot be settled from the repository (tracked in the decision log): whether `/home/user` is persistent across
  sandbox pause/resume on every platform tier (affects whether lazy installs repeat); whether egress to the manifest hosts is allowed by
  the platform network policy (`doctor --network` answers per deployment).

## 11. Failure modes

| Situation | Result |
|-----------|--------|
| Tool needed, mode `build`, not installed | `424 install.required` with the exact `prepare` command |
| Install takes longer than `install.wait` (v2.1) | `202` + job id + `Retry-After`; repeat or poll; never a blocked request |
| Read-only root, no writable tools dir, tool not prepared (v2.1) | `503 install.read_only`, `details.tried=[dirs]`, remedy `prepare` at build time |
| `noexec` tools dir / no network (v2.1) | `install.noexec` / `install.network_unreachable` within seconds, with the remedy |
| `deny(install)` for the principal (v2.1) | session create refused `403 policy.denied_by_rule`; nothing downloaded |
| Download blocked / DNS failure | `502 install.failed` `details.phase="fetch"` + hint to configure mirrors/offline cache |
| Digest mismatch | `502 install.checksum_mismatch`; cached artifact removed; no extraction |
| Two sandboxes' servers share a volume | flock serialises; second waits and sees `ready` |
| Disk full | `507`-style `install.no_space` (HTTP 503) before download, staging removed |
| `verify` fails (wrong platform) | `install.failed` `phase="verify"`; staging removed |
| Manifest from a user path invalid | refused at start (`check-config` error), server does not start |
| Caller tries to force install through a request field | not possible: install is never a request parameter |

## 12. Testing

* Local fixture HTTP server serving tiny tarballs and a fake npm registry (a `file:`-lockfile fixture + local registry via `npm_config_registry`
  when `npm` exists; otherwise the `npm-lock` driver is covered by a stub `npm` script on PATH that records its argv).
* Cases: checksum mismatch; concurrent installers (multiprocess, 8 callers, one download); kill -9 mid-install then retry; read-only tools dir;
  offline with/without cache; mirror redirect to non-allowed host; staging GC; marker/manifest drift triggers reinstall; unauthorized call never
  touches the network (assert zero connections); `prepare --dry-run` plan equals the set derived from the mounted ops for a config matrix.
