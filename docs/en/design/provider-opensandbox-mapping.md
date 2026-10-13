# OpenSandbox as an Agent Sandbox provider — research, API mapping, config keys, test plan

> **Status**: Research (read-mostly, input to the implementation phase) · **Provider id**: `opensandbox` · **Plugin kind**: `exec` (EPP/1) · **Canonical plugin**: [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox) (dependency-free Node `provider.mjs`). This repository keeps the host and the local-server harness (`e2e/opensandbox/`); it does not ship the plugin source. · **Companion docs**: [providers-and-credentials.md](providers-and-credentials.md) (normative provider/EPP design), `cli/docs/design/providers-and-credentials-cli.md`
>
> Chinese status page: [zh](../../zh/design/provider-opensandbox-mapping.md). Section 9 records what was implemented and live-tested; sections 1 to 8 are the research that preceded it.
>
> **Evidence convention.** Every behavioural claim below is tagged **[spec]** (read in an OpenAPI file), **[code]** (read in server/execd source) or **[live]** (observed against a real OpenSandbox server started locally; commands in §5). Anything tagged only **[spec]** or **[code]** and not **[live]** has not been exercised and the contract tests (§5.5) must pin it.

---

## 0. TL;DR

* OpenSandbox is a real, Apache-2.0, Alibaba-originated open-source sandbox platform (repo moved to `opensandbox-group/OpenSandbox`; `alibaba/OpenSandbox` 301-redirects to it). Two HTTP surfaces: a **lifecycle server** (FastAPI, API key header `OPEN-SANDBOX-API-KEY`, `/v1/sandboxes…`) and a per-sandbox **`execd`** daemon (Go/Gin, commands + files + code + PTY, optional `X-EXECD-ACCESS-TOKEN`), reached through an endpoint the lifecycle server resolves (`GET /v1/sandboxes/{id}/endpoints/{port}`).
* It is **image-based, not template-based**: `template` ⇒ container image URI. There is no template build/registry on the Docker runtime (`/templates` is the fsb microVM catalog and returns `501` on Docker).
* **It can be run for real on a plain Linux dev box / CI runner, with no secrets and no Kubernetes**: Docker (`docker.io` from apt) + `pip install opensandbox-server==1.1.1`. `e2e/opensandbox/local-up.sh up` does it in ~5 s once images are pulled; `e2e/opensandbox/live_smoke.py` then passes 35/35 checks (lifecycle, SSE exec, background commands, files, TTL renew, pause/resume, kill). Egress network policy also works live. There is **no Docker-less runtime** in the server (only `docker` and `kubernetes`), but the real `execd` binary runs stand-alone as a plain process, which gives a Docker-free "real data-plane" test tier (§5.3).
* **Mapping**: lifecycle, exec (sync + streaming), files, ports/URL, PTY, pause/resume are **native**; TTL change, remove, search/depth, user switching, stdin, process list/signal, capability probing are **emulated**; file watch, signed transfer URLs, templates (build/read), disk sizing, per-process stdin are **unsupported** (typed errors). Stateful code contexts are native **only** on images that ship the code-interpreter runtime (otherwise `execd` answers `500` for `/code` and **hangs** on `/code/context`).
* **Recommended implementation**: a single-file **stdlib-only Python `exec` plugin that calls the REST APIs directly**; do **not** wrap the official SDKs (pydantic-core native wheel, 15 MB/18 packages in Python; 8 MB/897 files in JS — both violate "installer never runs pip/npm; plugin ≤ 2000 files/50 MiB; no native code"). Reuse the SDKs/specs **as references and as test oracles** only.
* **Four gaps in the EPP/1 draft** found while mapping (§6): string process ids, a `detached` flag for `exec.start`, missing `code.*` methods, no per-sandbox capability probe.

---

## 1. What OpenSandbox is

### 1.1 Identity, licence, versions studied

| Item | Value |
|---|---|
| Name | **OpenSandbox** — "general-purpose sandbox platform for AI applications" |
| Repository | <https://github.com/opensandbox-group/OpenSandbox> (`https://github.com/alibaba/OpenSandbox` → HTTP 301 to the former; web search shows both URLs, README badges and `pyproject` URLs use `opensandbox-group`) · docs <https://open-sandbox.ai> |
| Licence | **Apache-2.0** (`LICENSE` at repo root, `server/LICENSE`, SDK `LICENSE`s; every source header "Copyright 2025 The OpenSandbox Authors"). Compatible with Agent Sandbox's licence; the Apache NOTICE obligation only matters if we **vendor/copy** OpenSandbox code (we only vendor *specs and recorded fixtures*, keep the licence header on them). |
| Commit studied | `a6a013554fcde095f367d68ac35af5e7bd967a6e` (`main`, 2026-10-12 14:30 +0800, shallow clone at `$WORKDIR/opensandbox-src`) |
| Release studied (what I ran) | umbrella tag `release-1.1.1` = `531700ca18a7fa5fab6a2f25d6dc68a76eddab12` (2026-10-09). `specs/sandbox-lifecycle.yml` and `specs/execd-api.yaml` are **byte-identical** between `release-1.1.1` and `a6a0135` (`git diff --stat` empty; only `egress-api.yaml` differs) **[live]** |
| Artifacts | PyPI `opensandbox-server==1.1.1` (what the server reports on `GET /version`), `opensandbox==1.1.1`, `opensandbox-code-interpreter==1.1.1`; npm `@alibaba-group/opensandbox@1.1.1` (Apache-2.0, node ≥ 20); Go `github.com/alibaba/OpenSandbox/sdks/sandbox/go` v1.1.1; Java/Kotlin, C#/.NET SDKs; `opensandbox-cli` (`osb`) |
| Images | `opensandbox/execd:{v1.1.0,latest}`, `opensandbox/code-interpreter:v1.1.0`, `opensandbox/egress:v1.1.7`, `opensandbox/ingress:*` |
| API spec versions | lifecycle `info.version: 0.1.0` (OpenAPI 3.1, 2406 lines); execd `info.version: 1.0.0` (3408 lines); egress and diagnostics specs exist too |

> **Version skew that matters.** The default `runtime.execd_image` shipped in the 1.1.1 server package is **`opensandbox/execd:v1.1.0`** (built 2026-08-28), but the **spec at 1.1.1** documents two execd behaviours that image does **not** have **[live]**: (a) `argv` in `POST /command` (`v1.1.0` answers `400 … Field validation for 'Command' failed on the 'required' tag`), (b) line-ending preservation in command output (`v1.1.0` emits one `stdout` event per line with `\n`/`\r` stripped; newer builds keep them, commits `163af0a3`, `380322ba`). `opensandbox/execd:latest` (built 2026-10-11, includes both) is what `opensandbox-local-up.sh` configures. The plugin must handle **both** (§2.2 exec rows).

### 1.2 Architecture

```text
 client (SDK / osb CLI / our plugin)
   │  ① lifecycle  HTTP  OPEN-SANDBOX-API-KEY            ② data plane  HTTP/SSE/WS  [X-EXECD-ACCESS-TOKEN]
   ▼                                                      ▲   address = GET /v1/sandboxes/{id}/endpoints/44772
┌──────────────────────────────┐   docker / k8s API       │   (docker bridge: "<host>:<hostport>/proxy/44772")
│ Lifecycle server (FastAPI)   │ ───────────────┐         │
│  server/opensandbox_server   │                ▼         │
│  auth middleware, validators │      ┌───────────────────┴──────────────── sandbox (container / pod / microVM) ──┐
│  sqlite|pg|redis metadata    │      │ user entrypoint (e.g. tail -f /dev/null, jupyter wrapper)                   │
│  runtimes: docker | k8s(+fsb)│      │ execd :44772  Go/Gin daemon, injected by bootstrap.sh; /command /files /code │
└──────────────────────────────┘      │               /pty /session /metrics /proxy/<port> (reverse proxy to ports) │
                                      │ [egress sidecar :18080  DNS / nft allow-deny policy, only when networkPolicy]│
                                      └─────────────────────────────────────────────────────────────────────────────┘
```

* **Control plane** `server/opensandbox_server` (FastAPI; routes `api/lifecycle.py`, `api/proxy.py`, `api/network_policy.py`, `api/templates.py`, `api/devops.py`; services `services/docker/*`, `services/k8s/*`, `services/fast_sandbox/*`). Runtimes: `docker` (single host) and `kubernetes` (BatchSandbox or kubernetes-sigs `agent-sandbox` workload providers, plus the fsb/fast-sandbox microVM template backend). `services/factory.py` registers **only** these two — there is no in-process/local runtime.
* **Data plane** `components/execd` (Go ≥1.25, Gin; `pkg/web/router.go`). Injected into the user container by `bootstrap.sh` (execd image is mounted/copied, started on port `44772`). In Docker bridge mode execd also acts as the **port gateway**: `pkg/web/proxy.go` reverse-proxies `/proxy/<port>/…` (HTTP, SSE, WebSocket) to `127.0.0.1:<port>` inside the sandbox, so `GET …/endpoints/<any-port>` returns `<host>:<execd-hostport>/proxy/<port>` (`server/…/services/docker/networking.py:335`) **[code][live]**.
* Other components: `components/egress` (per-sandbox sidecar for `networkPolicy`), `components/ingress` (gateway for k8s), `components/nodeagent`, `kubernetes/` (operator), `server` ↔ `execd` contract in `specs/`.
* Official docs on third-party implementations: `docs/api/implementation-compatibility.md` (the contracts are the interface; "pin the spec revision and SDK version you target").

### 1.3 Lifecycle API — `specs/sandbox-lifecycle.yml` (base `http://host:8080/v1`; routes also served without `/v1`)

**Auth** [spec][code][live]: header `OPEN-SANDBOX-API-KEY: <key>` on everything except `/health`, `/version`, `/docs`, `/redoc`, `/openapi.json` and `…/proxy/…` routes (`middleware/auth.py:37-120`). Missing → `401 {"code":"MISSING_API_KEY"…}`, wrong → `401 {"code":"INVALID_API_KEY"…}`. If the server has no `api_key` configured auth is skipped (startup then demands `OPENSANDBOX_INSECURE_SERVER=YES` or a TTY confirmation, `configuration.md`). SDK env names: `OPEN_SANDBOX_API_KEY`, `OPEN_SANDBOX_DOMAIN` (`host[:port]`, default `localhost:8080`), `OPEN_SANDBOX_PROTOCOL`, `OPEN_SANDBOX_USE_SERVER_PROXY`, `OPEN_SANDBOX_REQUEST_TIMEOUT` (`sdks/sandbox/python/src/opensandbox/config/connection.py:140-142`, `cli/src/opensandbox_cli/config.py:105-120`).

**Endpoints** (every response carries `X-Request-ID`):

| Method + path | Purpose | Request / response (essentials) | Success | Notable errors |
|---|---|---|---|---|
| `POST /sandboxes` | create | `CreateSandboxRequest` (below) → `CreateSandboxResponse{id,status,metadata,expiresAt?,createdAt,entrypoint,extensions?,platform?}` | `202` **[live]** (state already `Running` on Docker) | `400` (`SANDBOX::INVALID_METADATA_LABEL`), `422` FastAPI validation (`{"detail":[…]}`, **not** `ErrorResponse`), `403` quota, `409`, `429` pool, `500 DOCKER::SANDBOX_IMAGE_PULL_FAILED` |
| `GET /sandboxes` | list | query `state` (repeatable, OR), `metadata` (one url-encoded `k=v&k2=v2`, AND), `page`≥1, `pageSize` 1..200 (default 20) → `{items:[Sandbox], pagination{page,pageSize,totalItems,totalPages,hasNextPage}}` | `200` | `400`, `401` |
| `GET /sandboxes/{id}` | info | `Sandbox{id,image{uri}|snapshotId,platform?,status{state,reason?,message?,lastTransitionAt?},metadata,extensions?,allocation?,entrypoint,expiresAt?,createdAt}` | `200` | `404 DOCKER::SANDBOX_NOT_FOUND` |
| `DELETE /sandboxes/{id}` | kill | — | `204` | `404` (a **second** delete is `404`, i.e. not idempotent) **[live]**, `409` |
| `PATCH /sandboxes/{id}/metadata` | merge-patch metadata (RFC 7396; `null` deletes; `opensandbox.io/` prefix reserved) | flat object → full `Sandbox` | `200` | `400` |
| `POST /sandboxes/{id}/pause` · `/resume` | pause / resume (docker `pause`/`unpause`; k8s support is runtime dependent) | — | `202`; state `Paused` ⇄ `Running` observed synchronously on Docker **[live]** | `409` |
| `POST /sandboxes/{id}/renew-expiration` | **set absolute** expiry | `{expiresAt: RFC3339}` → `{expiresAt}`; may shorten; not capped by `max_sandbox_timeout_seconds` | `200` **[live]** | `400` |
| `GET /sandboxes/{id}/endpoints/{port}` | resolve access to a sandbox port | query `use_server_proxy=bool` (returns `<server>/v1/sandboxes/{id}/proxy/{port}`), `expires=<epoch s>` (signed route, k8s gateway only) → `Endpoint{endpoint:"host:port[/path]" (no scheme), headers?{…}}` | `200` **[live]** | `400`, `404`, `500 NETWORK_MODE_ENDPOINT_UNAVAILABLE` |
| `GET/PUT/PATCH/DELETE /sandboxes/{id}/networkpolicy` | read/replace/merge/delete egress rules (proxied to the egress sidecar) | `NetworkPolicy{defaultAction: allow|deny, egress:[{action,target: FQDN or *.wildcard}]}` → `PolicyStatusResponse` | `200` **[live]** | `502 BACKEND_CONNECTION_FAILED` when the sandbox has no sidecar **[live]** |
| `POST /sandboxes/{id}/snapshots`, `GET /snapshots`, `GET/DELETE /snapshots/{id}` | persistent snapshots; `snapshotId` is a create source | `Snapshot{id,sandboxId,name?,status{Creating|Ready|Failed|Deleting}}` | `202`/`200`/`204` | (create `202 Creating` observed **[live]**) |
| `GET/POST/DELETE /templates[/{id}]` | **fsb microVM golden images only** | `CreateFsbTemplateRequest{image,publish(s3://…),resourceLimits,…}` | — | **`501 FSB::API_NOT_SUPPORTED`** on the Docker runtime **[live]** |
| `POST /metrics/events` | SDK telemetry sink | `MetricsEvent` | `204` | irrelevant for us |
| `GET /health`, `GET /version` | liveness; `{"version":"1.1.1"}` | | `200` **[live]** | |
| `GET /sandboxes/{id}/diagnostics/{logs,events}` | `specs/diagnostic-api.yml` | log/event descriptors | | not used |

**`CreateSandboxRequest`** [spec lines ~1710-1930, live-verified fields marked ✓]:

| Field | Type / rule | Notes |
|---|---|---|
| `image` ✓ | `{uri, auth?{username,password}}` | exactly one of `image` / `snapshotId` / `templateId` (fsb) / `extensions.poolRef`. `image.auth` for private registries |
| `entrypoint` ✓ | `string[]` (≥1) | **required with `image`** (`422 "Entrypoint is required when image is provided."` ✓). Must be a long-running process (e.g. `["tail","-f","/dev/null"]`); OpenSandbox injects `execd` around it |
| `resourceLimits` ✓ | `{cpu:"500m", memory:"512Mi", gpu:"1", …}` string map | **required** in standard mode (`422` ✓). Unknown keys (e.g. `disk`) are accepted and **ignored** on Docker ✓ |
| `resourceRequests` | same | k8s only (ignored on Docker) |
| `timeout` ✓ | integer seconds **≥ 60** (`422` for 10 ✓), or `null`/omitted = **no expiry (manual cleanup)** ✓; capped by server `max_sandbox_timeout_seconds` | after TTL the sandbox is removed and `GET` returns **404**, not `Terminated` ✓ |
| `env` ✓ | `string→string` | visible to execd-spawned commands ✓ |
| `metadata` ✓ | `string→string` | **K8s-label rules enforced at create** ✓: key `[prefix/]name`, value ≤ 63 chars `[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?` → otherwise `400 SANDBOX::INVALID_METADATA_LABEL` ✓. Key `name` is the conventional human label |
| `networkPolicy` ✓ | see above | needs `[egress] image` in the server config and Docker `network_mode="bridge"` |
| `platform` | `{os: linux|windows, arch: amd64|arm64}` | |
| `volumes[]` | `{name, mountPath, readOnly?, subPath?, host|pvc|ossfs}` | host binds are allow-listed server-side (`[storage] allowed_host_paths`) |
| `lifecycle` | `{preStart{command[],timeoutSeconds}, periodic[…]}` | executed by execd |
| `secureAccess`, `credentialProxy`, `templateId`, `snapshotId`, `extensions{poolRef,…}` | | k8s/gateway/fsb specific |

**States** [spec]: `Pending → Running ⇄ (Pausing → Paused → Resuming) → Stopping → Terminated`, any → `Failed`; "clients must handle unknown values". On Docker only `Running`, `Paused`, `Pending`, `Terminated`, `Failed` are produced (`services/docker/docker_service.py:529-557`).

**Errors**: `ErrorResponse{code,message}` with namespaced codes (`DOCKER::SANDBOX_NOT_FOUND`, `SANDBOX::INVALID_METADATA_LABEL`, `DOCKER::SANDBOX_IMAGE_PULL_FAILED`, `FSB::API_NOT_SUPPORTED`, `KUBERNETES::QUOTA_EXCEEDED`, …) **except** FastAPI request-validation errors, which are `422 {"detail":[{type,loc,msg,input}]}` **[live]**. The plugin's error mapper must accept both shapes (and `execd`'s third shape `{"error": "..."}` for token failures, below).

### 1.4 `execd` API — `specs/execd-api.yaml`, router `components/execd/pkg/web/router.go:49-149`

**Auth** [spec][live]: header `X-EXECD-ACCESS-TOKEN` when execd is started with `-access-token` (or in k8s secure-access); wrong/missing → `401 {"error":"Unauthorized: invalid or missing header X-EXECD-ACCESS-TOKEN"}`. On the Docker runtime the default is **no token** and `Endpoint.headers` is empty **[live]**; in gateway/secure-access modes `Endpoint.headers` carries the headers every data-plane request must send (including routing headers such as `OpenSandbox-Ingress-To`) — the plugin must **replay `Endpoint.headers` verbatim on every execd request**.

**Streaming format** [live; also `sdks/sandbox/python/src/opensandbox/adapters/sse.py` "legacy bare-JSON frames"]: `Content-Type: text/event-stream`, but frames are **bare JSON objects separated by a blank line, with no `data:` prefix**. A robust reader accepts both `JSON\n\n` and standard `data: JSON\n\n`. Event object `ServerStreamEvent{type, text?, timestamp, execution_count?, execution_time?, results?{mime→value}, error?{ename,evalue,traceback[]}}`, `type ∈ init|status|error|stdout|stderr|result|execution_complete|execution_count|ping`:

```text
POST /command {"command":"echo out; echo err >&2; exit 3"}
{"type":"init","text":"<commandId>"}   ← first event: the command id
{"type":"ping","text":"pong"}
{"type":"stdout","text":"out\n"}  {"type":"stderr","text":"err\n"}
{"type":"error","error":{"ename":"CommandExecError","evalue":"3","traceback":["exit status 3"]}}   ← non-zero exit; no execution_complete follows
… success path ends with {"type":"execution_complete","execution_time":<ms>}
timeout       → error evalue "-1", traceback ["signal: killed"]   (indistinguishable from an external SIGKILL)
start failure → error evalue = message (e.g. capability error for uid/gid switch)
```

**Endpoints**:

| Group | Method + path | Semantics (verified ✓ live) |
|---|---|---|
| health | `GET /ping` → `200` (empty body) ✓; `GET /ready`, `POST /internal/init` (runtime init gate) | readiness probe the SDKs poll |
| command | `POST /command` `{command | argv[], cwd?, background?, timeout? (ms), uid?, gid? (gid needs uid), envs?}` → SSE | exactly one of `command`/`argv`; `argv` only on execd newer than `v1.1.0` ✓; `cwd` expands `$VAR`/`~`; **no stdin field** (ignored; `cat` blocks) ✓; uid/gid switch needs CAP_SETUID/SETGID ✓; client disconnect ⇒ process group `SIGKILL` (`runtime/command.go:300-330`) |
| | `GET /command/status/{id}` → `{id,content,running,exit_code?,error?,started_at,finished_at?}` ✓ (retained ≥ 24 h); unknown id → `404 {"code":"INVALID_REQUEST_BODY","message":"command not found: …"}` ✓ |
| | `GET /command/{id}/logs?cursor=N` → `text/plain` (stdout+stderr **merged**), header `EXECD-COMMANDS-TAIL-CURSOR` ✓; only for `background:true` commands (foreground ⇒ `400 … not running in background`) ✓ |
| | `DELETE /command?id=` → `200`; **SIGKILLs the whole process group** (context cancel) ✓ — not a polite SIGINT despite the name |
| session | `POST /session {cwd?}` → `{session_id}`; `POST /session/{id}/run {command,cwd?,timeout?}` → SSE (shell state persists: `cd`, `export`) ✓; `DELETE /session/{id}` | stateful bash |
| files | `GET /files/info?path=a&path=b` → `{path: FileInfo}`; **any missing path fails the whole call** `404 {"code":"FILE_NOT_FOUND"}` ✓. `FileInfo{path,type: file|directory|symlink|other,size,modified_at,created_at,owner,group,mode}`; `mode` is the **octal digits as a decimal int** (`644`, `755`) ✓ |
| | `DELETE /files?path=…` files only; missing file ⇒ `200` (idempotent) ✓; directory ⇒ `500 RUNTIME_ERROR "path is a directory"` ✓ |
| | `POST /files/mv [{src,dest}]` ✓; destination exists ⇒ `500 RUNTIME_ERROR "destination path already exists"` ✓ (no overwrite); missing source ⇒ `404` ✓; missing destination parent was created (spec says it must exist) ✓ |
| | `GET /files/search?path=&pattern=` glob (`*.txt`, `**/*.txt`, default `**`), recursive, returns `FileInfo[]` (files **and** dirs per pattern) ✓ |
| | `POST /files/replace[?verbose=true]`, `POST /files/permissions {path:{owner?,group?,mode}}` | |
| | `POST /files/upload` multipart: repeating pairs of parts named **`metadata`** (JSON `{path,owner?,group?,mode?}` **sent as a file part with a filename**, a plain form field → `400 "metadata file is missing"` ✓) and **`file`** (`application/octet-stream`); parents auto-created ✓; 3 MB round trip byte-exact ✓ |
| | `GET /files/download?path=` → `application/octet-stream`, `Range` supported (`206`), or line mode `?offset=&limit=` (1-based lines, `text/plain`) ✓; missing ⇒ `404`; **a directory path returns `200`** (plugin must stat first) ✓ |
| dirs | `GET /directories/list?path=&depth=1` (root excluded; lexical order; symlinks not followed; non-dir ⇒ `400`) ✓; `POST /directories {path:{mode}}` = `mkdir -p`, idempotent ✓; `DELETE /directories?path=` = `rm -rf`, missing ⇒ `404` ✓ |
| code | `POST /code/context {language}` → `{id,language}`; `GET /code/contexts[?language=]`; `GET/DELETE /code/contexts/{id}`; `DELETE /code/contexts?language=`; `POST /code {context{id?,language}, code}` → SSE with `stdout`, `stderr`, `result{results:{"text":"42"}}`, `execution_count`, `error{ename,evalue,traceback}` then `execution_complete`; `DELETE /code?id=` interrupt | Jupyter-backed; state persists across runs ✓ (`x=41` then `x+1` → `42`); exceptions arrive as `status:error` + `error` + `execution_complete` ✓; omitting `context.id` uses a per-language default context ✓. Languages (code-interpreter image): `python java go typescript javascript bash` |
| PTY | `POST /pty {cwd?}` → `{session_id}` (`201`) ✓; `GET /pty/{id}`; `DELETE /pty/{id}`; **WebSocket** `GET /pty/{id}/ws[?pty=0&since=&takeover=1&mode=viewer]`, binary frames `0x00 stdin / 0x01 stdout / 0x02 stderr / 0x03 replay`, text JSON frames `resize`/`signal`/`ping`/`exit` (`components/execd/PTY.md`). **Not in the OpenAPI file** (acknowledged in `docs/api/implementation-compatibility.md`) |
| metrics | `GET /metrics` → `{cpu_count,cpu_used_pct,mem_total_mib,mem_used_mib,timestamp}` ✓ (values reflect the host, not cgroup limits); `GET /metrics/watch` (SSE) | |
| proxy | any `/proxy/<port>/<path>` → `127.0.0.1:<port>` inside the sandbox (HTTP/SSE/WS) ✓ | how arbitrary ports are exposed on Docker |
| isolated | `/v1/isolated/*` bwrap overlay sessions + per-identity filesystem `/v1/filesystem/{uid}/{gid}/…` | out of scope |

**Code-interpreter availability [live].** On an image **without** the code-interpreter runtime (`python:3.12-slim`): `GET /code/contexts` → `200 []` (misleading), `POST /code` → `500 {"code":"RUNTIME_ERROR","message":"error running codes language runtime server not configured, please check your image runtime"}`, and `POST /code/context` **never answers** (client timeout after 10 s). On `opensandbox/code-interpreter:v1.1.0` with entrypoint `/opt/code-interpreter/code-interpreter.sh` everything works after ~25 s of Jupyter warm-up.

### 1.5 Official SDKs and tools (reuse candidates, §7)

`sdks/sandbox/{python,javascript,go,kotlin,csharp}`, `sdks/code-interpreter/{python,javascript,csharp}`, `sdks/mcp/sandbox`, `cli/` (`osb`). The Python SDK is generated-client + adapters (`adapters/{sandboxes,command,filesystem,health,egress,…}_adapter.py`, `api/{lifecycle,execd,egress,diagnostic}` generated from the specs, `adapters/sse.py` for the bare-JSON SSE quirk, `adapters/endpoint_cache.py`). I ran it unchanged against the local server (`e2e/opensandbox/sdk_smoke.py`: create → `commands.run` → `get_info` → `get_endpoint(8000)` ✓).

---

## 2. Operation-by-operation mapping

Legend — **N** native (1:1 call), **E** emulated (client-side logic or extra calls; described), **U** unsupported (typed error). EPP method names are from [providers-and-credentials.md §7.4](providers-and-credentials.md); `base` = `[lifecycle]` base URL (`…/v1`), `execd` = `http(s)://` + `Endpoint.endpoint` from `GET /sandboxes/{id}/endpoints/44772`, with `Endpoint.headers` replayed on every call.

### 2.1 Sandbox lifecycle (`sandbox.lifecycle`, `sandbox.timeout`, `sandbox.pause`)

| Agent Sandbox op (SDK / CLI) | EPP | OpenSandbox calls | Class | Details |
|---|---|---|---|---|
| `Sandbox.create(template, timeout, metadata, envs, cpu, memory, disk, gpu, secure)` / `abx create` | `sandbox.create` | `POST base/sandboxes`; if state ≠ `Running`: poll `GET /sandboxes/{id}` (≤ `ready_timeout`); then `GET …/endpoints/44772` and poll `GET execd/ping` until `200` (what the SDKs do) | **N** + E | `template`→`image.uri` (§3: `default_image`, `image_aliases`, anything containing `:` or `/` is a literal image URI); `timeout` s→`timeout` (**clamped up to 60** with a warning in `data`; values above the server cap come back `400/422` ⇒ `-32006`); `envs`→`env`; `cpu` int cores→`resourceLimits.cpu:"<n>"`; `memory` MB→`resourceLimits.memory:"<n>Mi"`; defaults when omitted `cpu 500m, memory 512Mi` (required by the API); `entrypoint` default `["tail","-f","/dev/null"]` (code-interpreter images: `/opt/code-interpreter/code-interpreter.sh`); `metadata` validated against the label rules (**E**): invalid key/value ⇒ `-32006` naming the key and the rule (no silent mangling); `gpu` numeric string→`resourceLimits.gpu`, a GPU *type* (`"A10"`) ⇒ `-32006`; **`disk` ⇒ `-32006`** (silently ignored by the server on Docker — we refuse instead of pretending); `secure=true`→`secureAccess:true` (k8s gateway only, else server error ⇒ `-32006`); `provider_options` (`--opt`): `entrypoint`, `network_policy` (JSON), `platform`, `registry_username/password`→`image.auth`. Returns `SandboxRecord{sandbox_id=id, template=image, status, created_at, expires_at (absent when `timeout` null), metadata}` |
| `Sandbox.connect(id)` / `abx connect` (record part) · `info` | `sandbox.connect`, `sandbox.get` | `GET base/sandboxes/{id}` | **N** | status map in §2.5; `metadata` as stored; `template`=`image.uri` (or `snapshot:<id>`) |
| `Sandbox.list(status, limit, offset)` / `abx list` | `sandbox.list` | `GET base/sandboxes?state=…&metadata=…&page=&pageSize≤200` | **N** + E | EPP `cursor` = next page number; `status`→`state` filter via the inverse map; `limit/offset` emulated by paging and slicing; the `metadata` filter is the server's label-equality match |
| `Sandbox.kill_by_id` / `abx kill` | `sandbox.kill` | `DELETE base/sandboxes/{id}` | **N** + E | `204`. **`404` is swallowed** (EPP requires idempotent kill; the server is not idempotent **[live]**). `409` ⇒ retry after 1 s once, then `-32000` |
| `set_timeout(seconds)` / `refresh` / `abx sandbox timeout` | `sandbox.set_timeout` | `POST base/sandboxes/{id}/renew-expiration {expiresAt}` | **E** | OpenSandbox sets an **absolute** time, Agent Sandbox a TTL from now: `expiresAt = server_now + timeout`, where `server_now` is parsed from the response `Date` header of a preceding cheap call (`GET` of the sandbox) to avoid client clock skew. Sandboxes created with `timeout=null` have no expiry: `renew-expiration` turns it into a TTL (accepted ✓) |
| `pause` / `resume` | `sandbox.pause`, `sandbox.resume` | `POST …/pause`, `POST …/resume`; then poll `GET` until `Paused` / `Running` (≤ 30 s) | **N** | `202`; Docker is synchronous ✓ (`docker pause`, cgroup freezer works on the test host). `409` (wrong state) ⇒ `-32000`; `501`/k8s "not supported" ⇒ `-32003` |
| (not an Agent Sandbox op) metadata patch, snapshots (`snapshotId` as create source), egress policy read/patch | — | `PATCH …/metadata`, `POST …/snapshots`, `…/networkpolicy` | — | candidates for future features (`sandbox.snapshot`, `network.policy`); **not** declared in v1. Network policy at create is available through `provider_options.network_policy` |

### 2.2 Commands and processes (`exec.run`, `exec.stream`, `process.manage`, `pty`)

| Agent Sandbox op | EPP | OpenSandbox calls | Class | Details |
|---|---|---|---|---|
| `commands.run(cmd, cwd, envs, user, timeout)` / `abx exec`, `run` | `exec.run` `{cmd,args,env,cwd,user,timeout,stdin?}` → `{exit_code,stdout,stderr}` | `POST execd/command` (SSE) | **N** + E | consume the stream: `init.text`=command id; concatenate `stdout`/`stderr` events; exit code = `0` on `execution_complete`, `int(error.evalue)` on `CommandExecError`; if `evalue` is not an integer (start failure) ⇒ `exit_code=126` + message in `stderr`; **timeout**: when the plugin set `timeout` and the error is `-1`/`signal: killed` ⇒ `-32005` (`CommandTimeoutError`). `cmd`+`args` ⇒ `argv` when supported; **fallback** for execd `v1.1.0` (`400 … 'Command' required`): `command = shlex.join([cmd,*args])` — detect once per sandbox and cache. `cwd`→`cwd`; `env`→`envs`; `timeout` s→ms. **Output framing**: new execd keeps `\n`/`\r\n` inside `text`; execd `v1.1.0` strips them and emits one event per line — heuristic: if no event of the stream ever contains `\n` or `\r` but there is more than one event, join with `\n` and append a final `\n`; an ambiguous single fragment is returned as received. (Pin `execd:latest`/≥ the `380322ba` build in the live tests so byte-exactness is verified once.) `stdout_b64`/`stderr_b64` are **not** provided (execd emits text) |
| `user=` (run as another user) | (same) | `uid`/`gid` fields | **E** | numeric → `uid`(+`gid`); a **name** is resolved first with `POST /command {"argv":["id","-u","<name>"]}` and `-g` (2 extra calls, cached); needs CAP_SETUID/SETGID inside the sandbox — Docker default `drop_capabilities` keeps them; if the daemon refuses the error text names the capability ⇒ `-32000` with suggestion |
| `stdin` for a run | (same) | none (`/command` ignores stdin) | **E** | write the data to `/tmp/.abx-stdin-<uuid>` (upload), run `sh -c '<cmd> < file; rc=$?; rm -f file; exit $rc'` (string-command mode only; `argv` mode wraps `exec "$@"`). Otherwise `-32003` for interactive stdin (use PTY) |
| `commands.stream(...)` / `shell-stream` | `exec.start` + `exec.output`/`exec.exit` | `POST execd/command` (SSE) | **N** | one `exec.output{process_id=init.text, stream: stdout|stderr, data}` notification per `stdout`/`stderr` event as it arrives, then exactly one `exec.exit{process_id, exit_code}` (rules identical to `exec.run`). The foreground process dies if the plugin/CLI disconnects (execd cancels on client disconnect) — so attached streaming is only valid while the host keeps the plugin alive |
| `commands.start(..., background=True)` / `abx sandbox process start` (survives the CLI) | `exec.start` (+ proposed `detached:true`, §6) | `POST execd/command {background:true}` → `init` + `execution_complete` immediately; later output by polling `GET execd/command/{id}/logs?cursor=` (merged stdout+stderr, `EXECD-COMMANDS-TAIL-CURSOR`) | **N** (start) / **E** (follow) | `process_id` = execd command id (32-hex **string**; Agent Sandbox's `ProcessInfo.pid` is an int ⇒ §6 gap 1). Follow-mode emulates `exec.output` by polling every 250 ms; streams cannot be separated (`stream:"stdout"` is reported) |
| `commands.list()` / `abx sandbox process list` | `process.list` | `POST execd/command` running `ps -eo pid=,ppid=,user=,etime=,args=` (fallback `ps` flavours / `/proc` walk for busybox) | **E** | execd has **no** list endpoint; parse into `{pid:int,ppid,user,elapsed,cmd}`; requires `ps` in the image (the existing CLI already shells out to `ps`/`ss` for `process info/ports`, `cli/commands/sandbox_process.py:143`, `sandbox_system.py:190`) |
| `commands.kill(pid)` / `process kill` | `process.kill` | numeric pid → `exec` `kill -9 <pid>`; execd command id → `DELETE execd/command?id=` | **N**/**E** | the `DELETE` is a group `SIGKILL` ✓ |
| `commands.send_signal(pid, sig)` / `process signal` | `process.signal` | numeric pid → `kill -<sig> <pid>` through `exec.run`; command id: `sig=9` ⇒ `DELETE /command`, other signals ⇒ `-32003` ("signal other than KILL needs a numeric pid") | **E** | no signal endpoint exists except PTY `{"type":"signal"}` frames (PTY sessions only) |
| `commands.send_stdin(pid, data)` | `process.stdin` | — | **U** | `-32003`: execd `/command` has no stdin channel; use `pty.*` or a bash session. (A `POST /session/{id}/run`-based emulation changes semantics — rejected) |
| `process info` | (CLI shells `ps -p`) | `exec.run` | **E** | unchanged CLI behaviour |
| `get_terminal()` / `connect --pty` | `pty.open/write/resize/close` + `pty.output` | `POST execd/pty` → `GET execd/pty/{id}/ws` (WebSocket, binary framing above) | **N** | needs an RFC 6455 client; the Python stdlib has none ⇒ ~120 lines hand-rolled (client masking, ping/pong, text+binary frames) or defer `pty` to a v1.1 and omit the feature from the manifest. `resize`→`{"type":"resize",cols,rows}`; `close`→`DELETE /pty/{id}` |
| `run_code` / `code.*` — stateful contexts (`create_context`, `list_contexts`, `remove_context`) | (**missing in EPP/1**, §6 gap 3) | `POST /code/context` (client timeout **10 s** because it can hang), `GET /code/contexts`, `DELETE /code/contexts/{id}`, `POST /code` (SSE) | **N** | `stdout`/`stderr`/`result`/`error` events map onto `CodeResult`; `-32003` when `POST /code` answers `500 … language runtime server not configured` or context creation times out. `restart_context` **E**: `DELETE` + `POST` (the id changes; document it) |
| `run_code` on images without the interpreter | — | none | **E** | already handled by the SDK: `CodeContextModule.run` falls back to "write temp file + run interpreter via shell" when the provider reports no code service (`api/code.py:60-160`), so `run_code` keeps working through `exec.run` + `files.write` |

### 2.3 Files (`files.rw`; `files.watch`, `files.transfer` not offered)

| Agent Sandbox op | EPP | OpenSandbox calls | Class | Details |
|---|---|---|---|---|
| `files.read` / `read_bytes` / `download` | `files.read` → `{content_b64,size}` | `GET execd/files/info?path=` (type check) then `GET execd/files/download?path=` | **N** + E | a directory download answers `200`, so stat first and raise `FileOperationError` (`-32006`/`E4000`) for directories; missing ⇒ `404 FILE_NOT_FOUND` ⇒ `-32002` + `sdk_code=E4001`. Large files: base64-in-JSON doubles the size (EPP limit 8 MiB per line) — see §6 gap 4 (ranged reads via `Range` are available server-side for chunking: plugin returns ≤ 4 MiB per call with `offset`) |
| `files.write` / `upload` | `files.write` `{path,content_b64,mode?}` | `POST execd/files/upload` (multipart: `metadata` **file part** `{"path":…, "mode":…}` + `file` part) | **N** | parents auto-created ✓; `mode` octal-digits-as-int (`0o644`→`644`); build the multipart by hand (stdlib `email`/manual); metadata part must have a `filename` ✓ |
| `files.list(path)` / `abx sandbox files list` | `files.list` → `entries[{name,path,type,size,mtime}]` | `GET execd/directories/list?path=&depth=1` | **N** | `name`=basename; `type` map `file→file`, `directory→directory`, `symlink/other→file` + `symlink:true`; `modified_at`→`mtime`; non-directory `400` ⇒ `-32006`; missing ⇒ `404` ⇒ `-32002/E4001` |
| `files.stat/get_info` / `abx … stat` | `files.stat` | `GET execd/files/info?path=` | **N** | response is keyed by path; `mode` is octal digits |
| `files.exists` | (SDK composes stat) | same | **E** | `404 FILE_NOT_FOUND` ⇒ `false` |
| `files.make_dir` / `mkdir` | `files.mkdir` | `POST execd/directories {path:{mode:755}}` | **N** | `mkdir -p` + idempotent ✓; path is a file ⇒ `500 "not a directory"` ⇒ `-32006` |
| `files.remove` / `rm` | `files.remove` | `GET execd/files/info` → `DELETE execd/files?path=` (file/symlink) **or** `DELETE execd/directories?path=` (directory) | **E** | the two endpoints are type-specific (`DELETE /files` on a directory is `500`) ✓; missing file ⇒ `200` (OK); missing directory ⇒ `404` ⇒ `-32002/E4001` (SDK semantics of `remove` on a missing path decide whether to swallow — keep identical to the built-in provider) |
| `files.move/rename` / `mv` | `files.move` | `POST execd/files/mv [{src,dest}]` | **N** + E | works for files **and** directories ✓; **no overwrite** (`500 destination path already exists` ⇒ `-32006` "destination exists"); if Agent Sandbox's contract overwrites, plugin does `DELETE` target first (E) |
| `abx sandbox files search --pattern --max-depth` | (CLI today runs `find …`) | `GET execd/files/search?path=&pattern=` | **N** + E | glob is recursive; `--max-depth` filtered client-side by path segment count; files-only filter on `type=="file"`. The CLI may keep its `find` fallback unchanged |
| `files.watch(path)` | `files.watch` | — | **U** | `-32003` (`ProviderFeatureNotSupportedError`): execd has no watch endpoint. (A polling emulation over `directories/list` would lie about event types — not offered) |
| `upload_url` / `download_url` (signed transfer URLs) | `files.transfer` | — | **U** | `-32003`: no signed/expiring URL in the execd API (`GET execd/files/download?path=` works but is unsigned and needs the endpoint headers; not equivalent) |
| chmod / replace | (not in EPP) | `POST execd/files/permissions`, `POST execd/files/replace` | **N** (available) | only via `exec.run chmod` unless EPP adds `files.chmod` |

### 2.4 Ports, capabilities, templates

| Agent Sandbox op | EPP | OpenSandbox calls | Class | Details |
|---|---|---|---|---|
| `network.get_url(port)` / `abx url` / `sandbox system ports` (URL part) | `ports.url` → `{url,headers?}` | `GET base/sandboxes/{id}/endpoints/{port}[?use_server_proxy=true]` | **N** | the API returns `host:port[/path]` **without scheme**: `url = scheme + endpoint` where scheme = `https` if `base_url` is `https` else `http`; `headers` returned as-is (secure-access/gateway); `use_server_proxy` (config key) makes URLs go through the lifecycle server `…/v1/sandboxes/{id}/proxy/{port}` when sandbox host ports are not routable from the client. Docker bridge: every port ≠ 8080 resolves via execd's `/proxy/<port>` gateway ✓ (HTTP/SSE/WebSocket only, not raw TCP) |
| `sandbox system ports` (list listening ports) | `exec.run` | `ss -tlnp` | **E** | unchanged CLI behaviour (already shells out) |
| Capability discovery (`resolve_capabilities`, `abx sandbox system capabilities`) | `initialize.features` + proposed `sandbox.capabilities` | static features from the manifest; per-sandbox probes | **E** | Agent Sandbox derives capabilities from **template data** (`api/capability.py`); OpenSandbox has no template metadata. Effective tokens = provider features mapped (`shell←exec.run`, `files←files.rw`, `ports←ports.url`, `terminal←pty`) **plus** `code` only if the probe passes: `POST /code {context:{language:"python"},code:"None"}` ⇒ `200`+`execution_complete` ⇒ `code`; `500 … runtime server not configured` ⇒ no `code`. Never probe with `GET /code/contexts` (answers `200 []` on any image) or `POST /code/context` (hangs). Cache per sandbox for the process lifetime |
| `template` (image) · `templates.read` (`template list/info`) | — | — | **U** (read) / **N-ish** (use) | A "template" is an **image URI**. Using one at create is native. There is no catalogue to list on Docker: `GET /templates` is the fsb microVM catalogue and returns `501 FSB::API_NOT_SUPPORTED` ✓; the plugin does **not** declare `templates.read`; `abx template list` against this provider ⇒ `E8004`. Optional later: serve `image_aliases` as a read-only list |
| `templates.build` (`template build/deploy/delete`, `deploy`, `install`) | — | — | **U** | `E8004` before any Docker work (design doc §7.7). Prebuilt image: build/push with any registry, then `abx create --template <image-uri> --provider opensandbox`. Unknown/unpullable image on create ⇒ `500 DOCKER::SANDBOX_IMAGE_PULL_FAILED` (message contains `pull access denied` / `not found`) ⇒ `-32002` with `sdk_code=E2001` (TemplateNotFound) |
| `storage.mount`, `network.vpc`, `ports.domain` (extensions) | — | `volumes[]`, k8s | **U** in v1 | OpenSandbox volumes (`host`, `pvc`, `ossfs`) exist but are not part of Agent Sandbox's `OSSMount` contract; not declared |

### 2.5 Cross-cutting mappings

**Status** (`SandboxRecord.status`): `Pending`→`creating`, `Running`→`running`, `Pausing`→`paused` (execs would already fail), `Paused`→`paused`, `Resuming`→`creating`, `Stopping`→`stopping`, `Terminated`→`stopped`, `Failed`→`error`, unknown→`error` (+ raw state in `data`). Inverse for the list filter: `running`→`Running`, `paused`→`Paused,Pausing`, `creating`→`Pending,Resuming`, `stopping`→`Stopping`, `stopped`→`Terminated`, `error`→`Failed`.

**Errors** (EPP code ← OpenSandbox):

| OpenSandbox signal | EPP | Host exception |
|---|---|---|
| lifecycle `401` (`MISSING_API_KEY`, `INVALID_API_KEY`), execd `401 {"error":…}` | `-32001` (`sdk_code` `E1001`) | `InvalidAPIKeyError` |
| lifecycle `404` (`*SANDBOX_NOT_FOUND`), execd `404 FILE_NOT_FOUND` / `command not found` | `-32002` (`E4001` for files, none for sandbox/command) | `SandboxError` family |
| `501`, execd `NOT_SUPPORTED`, code-runtime-not-configured `500`, context-creation timeout | `-32003` | `ProviderFeatureNotSupportedError` (E8004) |
| `403 KUBERNETES::QUOTA_EXCEEDED`, `429` (pool) | `-32004` (`retryable` for 429) | `QuotaExceededError` |
| client/read timeout; execd `-1`/`signal: killed` with plugin timeout set | `-32005` | `CommandTimeoutError` / `ProviderTimeoutError` |
| `400`, `422 {"detail":…}`, `SANDBOX::INVALID_METADATA_LABEL`, unsupported option | `-32006` (`data.details` = field/loc/msg) | `ProviderConfigError` |
| connection refused / reset to execd while state is `Paused` | `-32000` + suggestion "resume the sandbox" | `SandboxError` |
| `5xx`, `409`, `502 BACKEND_CONNECTION_FAILED` | `-32000`, `retryable:true` for `502/503/504` and idempotent calls | `SandboxError` |

---

## 3. Credentials and configuration keys (proposal, naming style of the provider design doc)

Provider id **`opensandbox`** (matches `^[a-z][a-z0-9]*(-[a-z0-9]+)*$`, not reserved). Canonical env = `ABX_OPENSANDBOX_<KEY>` (design doc §2 principle 3); `native` env names are the names the OpenSandbox SDKs/`osb` CLI already use, so users with a working OpenSandbox environment need no new variables (none start with `ABX_`, `E2B_`, `ALICLOUD_`, as required by the manifest rules). The plugin consumes **no core credential**: `[core] inherit = []` — it must never receive `ABX_SANDBOX_API_KEY` or the Alibaba Cloud access key (§4.6 isolation).

| Key (scoped) | Type | Secret | Canonical env | `native` env | Default | Meaning |
|---|---|---|---|---|---|---|
| `base_url` | url | no | `ABX_OPENSANDBOX_BASE_URL` | — | `http://127.0.0.1:8080` | Lifecycle server root. A trailing `/v1` is accepted and normalised (the server serves `/v1/…` and bare routes) |
| `api_key` | str | **yes** | `ABX_OPENSANDBOX_API_KEY` | `OPEN_SANDBOX_API_KEY` | none | Sent as `OPEN-SANDBOX-API-KEY`. **Not** `credential=true`: a local dev server may run without a key (server logs an insecure-mode acknowledgement); `provider doctor` reports `401` precisely |
| `domain` | str (`host[:port]`) | no | `ABX_OPENSANDBOX_DOMAIN` | `OPEN_SANDBOX_DOMAIN` | none | SDK-style alternative to `base_url` (`protocol://domain`); `base_url` wins when both are set. Optional; may be dropped from v1 if the surface is judged too wide |
| `protocol` | enum `http`,`https` | no | `ABX_OPENSANDBOX_PROTOCOL` | `OPEN_SANDBOX_PROTOCOL` | `http` | Scheme used with `domain`, and for endpoint URLs |
| `use_server_proxy` | bool | no | `ABX_OPENSANDBOX_USE_SERVER_PROXY` | `OPEN_SANDBOX_USE_SERVER_PROXY` | `false` | Route execd traffic and port URLs through `GET …/endpoints/{port}?use_server_proxy=true` (needed when sandbox host ports are unreachable from the client, e.g. server in a container or k8s without gateway) |
| `default_image` | str | no | `ABX_OPENSANDBOX_DEFAULT_IMAGE` | — | `python:3.12-slim` | Image used when `template` is the generic default (`base`) |
| `image_aliases` | csv `name=image` | no | `ABX_OPENSANDBOX_IMAGE_ALIASES` | — | `code=opensandbox/code-interpreter:v1.1.0` | Short template names → image URIs |
| `entrypoint` | str (shell-split) | no | `ABX_OPENSANDBOX_ENTRYPOINT` | — | `tail -f /dev/null` | Entrypoint for generic images (required by the API) |
| `ready_timeout` | int s ≥ 1 | no | `ABX_OPENSANDBOX_READY_TIMEOUT` | — | `60` | Wait for `Running` + `execd /ping` after create |
| `registry_username` / `registry_password` | str / str | no / **yes** | `ABX_OPENSANDBOX_REGISTRY_USERNAME` / `…_PASSWORD` | — | none | → `image.auth` for private registries (never logged; redacted from errors by the host) |

Shared core tuning keys are honoured unchanged (`http_timeout`, `max_retries`, …). `[auth] any_of` is **omitted** (see `api_key`). Per-create options (`--opt` / `provider_options`) are not stored: `entrypoint`, `network_policy` (JSON object matching `NetworkPolicy`), `platform` (`linux/arm64`), `secure_access`, `image_auth`.

Manifest sketch (only the OpenSandbox-specific parts):

```toml
manifest_version = 1
[provider]
id = "opensandbox"
name = "OpenSandbox"
name_zh = "OpenSandbox 开源沙箱"
license = "Apache-2.0"
homepage = "https://github.com/opensandbox-group/OpenSandbox"
[compat]
protocol = "epp/1"
[runtime]
kind = "exec"
command = ["python3", "provider.py"]
[features]
supported = ["sandbox.lifecycle", "sandbox.timeout", "sandbox.pause", "exec.run", "exec.stream",
             "process.manage", "files.rw", "ports.url"]   # + "pty", "code.interpret" once the EPP gaps of §6 are closed
[security]
network = ["*"]                 # user-configured server URL
filesystem = ["data_dir"]
env_passthrough = []
spawns_processes = false
[core]
inherit = []
```

---

## 4. What cannot be done / honest limits

1. No disk sizing on Docker (ignored by the server) ⇒ `disk` refused.
2. No file watch, no signed transfer URLs, no per-process stdin, no real process table (shell emulation only, so `ps` must exist in the image).
3. TTL minimum is 60 s; Agent Sandbox allows 1 s.
4. Metadata must satisfy Kubernetes label syntax (≤ 63-char values).
5. `execd` output framing and `argv` depend on the execd image version (§1.1); `abx` should document a minimum (`opensandbox/execd:latest` or the first release after `release-1.1.1`) for byte-exact output.
6. Code contexts require a code-interpreter image; probing must avoid the hanging endpoint.
7. A foreground command is killed when the connection drops, so `abx … process start` must use `background:true` (needs the `detached` hint, §6).

---

## 5. Test plan

### 5.1 Can OpenSandbox run locally? — **Yes, for real (Docker runtime), no secrets**

Checked on a dev VM (Ubuntu 24.04, kernel 6.12, 4 vCPU, 16 GB, rootfs = overlayfs, non-root user with passwordless sudo, outbound internet to PyPI / Docker Hub):

| Question | Result |
|---|---|
| `docker --version` / `docker ps` at start | `docker: command not found` (no Docker preinstalled), no `/var/run/docker.sock`; no podman |
| Can Docker be installed? | **Yes**: `sudo apt-get install -y docker.io iptables` (29.1.3) |
| systemd? | No (PID 1 is `tini`; `systemctl` reports offline) ⇒ start `dockerd` by hand with `nohup` |
| Containers on the default overlay `/`? | **No** — `failed to mount … overlay … invalid argument` (overlay-on-overlay). **Fix that worked**: 20 GB sparse ext4 image loop-mounted at `/mnt/dockerdata` and `/etc/docker/daemon.json = {"data-root":"/mnt/dockerdata","storage-driver":"overlay2","features":{"containerd-snapshotter":false}}` |
| Privileges needed by OpenSandbox | Docker socket access for the server user (`chmod 666 /var/run/docker.sock`); containers run with the server's default `drop_capabilities`; **bridge networking, host port publishing, `docker pause`, egress sidecar (DNS enforcement) all worked** |
| Server without Docker (`dev`/local runtime)? | **No.** `services/factory.py` supports only `docker` and `kubernetes`; `DockerSandboxService` connects to the Docker daemon at start-up. Kubernetes runtime: no cluster here (not attempted; would need kind/k3s + CRDs + operator) |
| Python/uv install of the server | **Yes**: `uv venv --python 3.12` + `uv pip install opensandbox-server==1.1.1` (FastAPI 0.143; `opensandbox-server init-config … --example docker` writes a config); runs as a normal user |
| Images pulled OK | `opensandbox/execd:{v1.1.0,latest}` (35 MB binary), `python:3.12-slim`, `opensandbox/code-interpreter:v1.1.0`, `opensandbox/egress:v1.1.7` |
| Real execd without Docker | **Yes**: `docker cp` the `/execd` binary out of the execd image; `./execd --port 44790 [-access-token T]` runs as an unprivileged process and serves the full data-plane API (commands, files, SSE, `/proxy`) **[live]**. Code contexts need Jupyter and are not available this way. (extract `execd:latest` and `v1.1.0` with `docker cp` into `$WORKDIR/bin/`) |

**Exact commands that worked** (`$WORKDIR` = the script's `OSB_WORKDIR`, default `~/.cache/agent-sandbox/opensandbox-local`; `$ORIG_REPO` = the checkout of the Agent Sandbox source tree used for the surface survey; all wrapped in `python-sdk/e2e/opensandbox/local-up.sh`, idempotent, ≈ 5 s warm, ≈ 70 s with cold image pulls):

```bash
# Docker
sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io iptables
sudo truncate -s 20G /var/lib/docker-loop.img && sudo mkfs.ext4 -q -F /var/lib/docker-loop.img
sudo mkdir -p /mnt/dockerdata /etc/docker && sudo mount -o loop /var/lib/docker-loop.img /mnt/dockerdata
echo '{"data-root":"/mnt/dockerdata","storage-driver":"overlay2","features":{"containerd-snapshotter":false}}' | sudo tee /etc/docker/daemon.json
(sudo nohup dockerd >"$WORKDIR/dockerd.log" 2>&1 &); sleep 8; sudo chmod 666 /var/run/docker.sock
docker run --rm alpine echo ok                      # sanity
# OpenSandbox server (PyPI, normal user)
pip install --user uv && export PATH=$HOME/.local/bin:$PATH
uv venv $WORKDIR/venv --python 3.12
uv pip install --python $WORKDIR/venv/bin/python opensandbox-server==1.1.1
docker pull opensandbox/execd:latest python:3.12-slim opensandbox/egress:v1.1.7     # + opensandbox/code-interpreter:v1.1.0 for run_code
cat >$WORKDIR/server.toml <<'EOF'
[server]
host = "127.0.0.1"
port = 8080
api_key = "local-dev-key"          # not a secret: a throw-away local key
max_sandbox_timeout_seconds = 86400
[runtime]
type = "docker"
execd_image = "opensandbox/execd:latest"
[store]
type = "sqlite"
path = "$WORKDIR/opensandbox.db"
[docker]
network_mode = "bridge"
[ingress]
mode = "direct"
[egress]
image = "opensandbox/egress:v1.1.7"
mode = "dns"
EOF
(nohup $WORKDIR/venv/bin/opensandbox-server --config $WORKDIR/server.toml >$WORKDIR/server.log 2>&1 &)
curl -s localhost:8080/health   # {"status":"healthy"}   curl -s localhost:8080/version  # {"version":"1.1.1"}
```

Then `export OPENSANDBOX_BASE_URL=http://127.0.0.1:8080/v1 OPENSANDBOX_API_KEY=local-dev-key` and `python3 e2e/opensandbox/live_smoke.py` (stdlib only; 35 checks, all passing, ~5 s) — it doubles as the executable specification of the §2 mapping (auth, create/get/list/endpoint, SSE exec + exit codes + timeout, background + logs cursor + interrupt, mkdir/upload/stat/list/search/mv/rm/rmdir, renew, pause/resume, kill + second-kill `404`). Also verified live: server-proxied endpoints, egress policy (`deny` default + `allow pypi.org` blocks `example.com`, allows `pypi.org`; `PATCH …/networkpolicy` merge), snapshots (`202 Creating`), the official Python SDK end to end, execd access-token behaviour.

`opensandbox-local-up.sh` knobs: `up|down|status|env`, `OSB_SERVER_VERSION`, `OSB_EXECD_IMAGE`, `OSB_PORT`, `OSB_API_KEY`, `OSB_WORKDIR`, `OSB_WITH_EGRESS`, `OSB_WITH_CODE_INTERPRETER`. `down` stops the server and removes all `sandbox-*` containers. The local server harness stays in this repository (`e2e/opensandbox/`). The plugin source is [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox).

### 5.2 Test pyramid for the plugin

| Tier | What | Needs | Where it runs |
|---|---|---|---|
| **T0 unit** | pure functions: status/error maps, label validation, `timeout`/`memory`/`mode` conversions, bare-JSON **and** `data:` SSE parser (split chunks, CRLF, partial frames, huge events), line-ending heuristic, multipart builder, endpoint → URL, metadata filter encoding, `Date`-header TTL maths | nothing | every PR, offline |
| **T1 mock-server contract** | the whole plugin over real EPP (stdin/stdout JSON-RPC) against `mock_opensandbox.py` (§5.4) | python stdlib | every PR, offline |
| **T2 EPP conformance** | `ProviderContractTests` from `agent_sandbox.providers.testing` (design doc §10.8: declared features work, undeclared fail with `-32003`, idempotent kill, unknown sandbox `-32002`) against the mock | T1 | every PR, offline |
| **T3 real execd** | the mock's lifecycle half + the **real `execd` binary** as data plane (process per sandbox in a temp dir) — exercises true command/file/SSE semantics without Docker | `execd` binary (downloaded from the pinned image or `OPENSANDBOX_EXECD_BIN`) | CI when the binary is cached; skipped otherwise |
| **T4 live** | real `opensandbox-server` + Docker via `opensandbox-local-up.sh`; same test bodies as T1 parametrised by `OPENSANDBOX_LIVE=1`; adds pause/resume, TTL expiry, egress policy, code interpreter (`OSB_WITH_CODE_INTERPRETER=1`), v1.1.0-vs-latest execd matrix | Docker, ~1.5 GB images | opt-in (`pytest -m live`, nightly or label-triggered CI job on `ubuntu-latest`, which has Docker); **no secrets anywhere** |

CI policy: T0–T2 are required and offline; T3 optional-but-recommended; T4 must pass before a release and on a nightly schedule against `opensandbox/execd:latest` to catch upstream drift (version skew in §1.1 is a live example).

### 5.3 Docker-free real data plane (T3) — design

Start the real `execd` for each fake sandbox: `execd --port <p> [-access-token <t>]` with `cwd` = a per-sandbox temp dir (`HOME` and `TMPDIR` pointed inside; commands run as the test user, so `/tmp/...` absolute paths used by tests are rewritten under the sandbox root or avoided). The mock lifecycle returns `endpoint: "127.0.0.1:<p>"`; `kill` terminates the process group; TTL is enforced by a timer; `pause` = `SIGSTOP` of the process group (and `SIGCONT` on resume) — a faithful *enough* analogue of `docker pause`. This validates everything in §2.2/§2.3 except the code interpreter, PTY-under-Docker caveats and egress.

### 5.4 Faithful mock server (T1) — design, in case no execd binary / Docker is available

One stdlib `http.server`/`ThreadingHTTPServer` module (`tests/mock_opensandbox.py`, ≈ 600 lines), two virtual hosts on two ports (lifecycle, one execd per sandbox), in-memory state:

* **Fidelity source = recorded fixtures, not imagination.** Responses are **replayed from fixtures captured by the live smoke run** (scrubbed ids/times), covering the quirks that matter: `202` create with `Running`, `422 {"detail":…}` shape, `404 DOCKER::SANDBOX_NOT_FOUND`, second-delete `404`, bare-JSON SSE with `init`/`ping`, `error{CommandExecError,evalue}` exit signalling, `-1`/`signal: killed`, `files/info` map keyed by path with octal-digits `mode`, `DELETE /files` on a directory `500`, `/files/mv` overwrite `500`, upload `metadata` file-part requirement and `400 "metadata file is missing"`, merged background logs with `EXECD-COMMANDS-TAIL-CURSOR`, `501 FSB::API_NOT_SUPPORTED`, endpoint without scheme, `Endpoint.headers`, `GET /code/contexts → 200 []`, `500 … runtime server not configured`, and the **hang** of `POST /code/context` (a configurable stall to test the client timeout).
* **Behaviour = a tiny real model**: sandbox table with states and TTL (`expiresAt`, expiry ⇒ removal), virtual filesystem rooted in a temp dir, commands executed with `subprocess` (`sh -c`/argv) streaming stdout/stderr events in the exact framing (selectable *new* vs *v1.1.0* line-stripping mode, and `argv` accepted/rejected by flag), background registry, `renew-expiration`, `pause/resume`, metadata label validation, `pageSize ≤ 200`, API-key and `X-EXECD-ACCESS-TOKEN` enforcement, a "gateway mode" returning `Endpoint.headers` that the plugin must replay (the mock rejects requests without them).
* **Spec conformance guard (offline)**: vendor `specs/sandbox-lifecycle.yml` + `specs/execd-api.yaml` at the pinned commit (`a6a0135…`, Apache-2.0 headers kept) and, in dev-only test dependencies, validate every request the plugin sends and every response the mock produces against the schemas (`openapi-core` or `jsonschema` on `$ref`-resolved component schemas). A separate test fails if the vendored spec hash differs from the commit recorded in `tests/SPEC_PIN` so spec upgrades are deliberate. Known spec-vs-reality divergences found here are encoded as explicit allow-list entries with a comment: `422 detail` bodies, `execd 401 {"error"}`, `files/mv` auto-creating parents, `/pty` absent from the spec, `/command` `argv` unavailable in `v1.1.0`.
* **Differential rule**: every T1 test body also runs in T4; a mock behaviour change must come with a live re-recording (`make record-fixtures`, a script that replays the smoke flow against the live server and rewrites `tests/fixtures/*.json`).

### 5.5 Contract tests worth writing first

(1) exec exit-code matrix `0/3/127/timeout/start-failure`; (2) both framing modes produce identical `stdout` for `printf 'a\r\nb\n'`; (3) upload→download byte-exactness incl. `\x00\xff`, empty file, 3 MB; (4) remove of file/dir/missing, move-onto-existing, search depth; (5) `set_timeout` → `expiresAt` within ±2 s of server time even with a skewed client clock; (6) idempotent kill; (7) metadata label rejection message names the key; (8) capability probe never calls the hanging endpoint without a timeout; (9) `Endpoint.headers` replayed on every execd call incl. SSE and uploads; (10) `list` pagination > 200 items; (11) `exec.start` stream ordering: all `exec.output` before the single `exec.exit`; (12) error-shape tolerance (`ErrorResponse`, `{"detail":[…]}`, `{"error":…}`, non-JSON `502` HTML).

---

## 6. Gaps in the EPP/1 draft that this provider exposes (for the provider-design owner)

1. **Process ids are strings.** execd command ids are 32-hex strings; Agent Sandbox's `ProcessInfo.pid` is an `int`. EPP should type `process_id` as `string | int` and let `process.kill/signal` accept either (this doc's mapping: numeric ⇒ OS pid via `kill`, hex ⇒ execd command id).
2. **`exec.start` has no `detached`/`background` hint.** A foreground OpenSandbox command is killed when the connection closes, so a process that must outlive the CLI invocation (`abx sandbox process start`, background `commands.start`) needs `background:true` plus log polling. Proposal: optional boolean `detached` in `exec.start` params (ignored by providers whose processes are always detached).
3. **No `code.*` methods** although `code.interpret` is a feature id: add `code.run` (`{sandbox_id, code, language, context_id?, envs?, timeout}` → streamed `code.output` notifications + final `{results, error?}`), `code.context.create/list/remove/restart`. Until then the plugin must **not** declare `code.interpret`; `run_code` still works through the SDK's shell fallback (`api/code.py`).
4. **Large file bodies.** `files.read/write` are base64-in-JSON with an 8 MiB line cap; OpenSandbox supports `Range` and 3 MB+ bodies natively. Options: chunked `files.read{offset,length}` / `files.write{append}`, or an optional "direct data plane" descriptor on `SandboxRecord` (`{base_url, headers}`) for providers whose data plane is plain HTTP (OpenSandbox's `Endpoint` is exactly that) — the doc's hybrid `envd_url` model is envd-protocol-specific.
5. **Per-sandbox capabilities.** Effective capabilities are template-derived today; for image-based providers they depend on the image (`code` only with the interpreter). Add optional `sandbox.capabilities{sandbox_id} → {tokens:[…]}` (else the host falls back to static features).
6. Minor: `files.search`, `files.chmod` are absent from the EPP table (native in OpenSandbox; the CLI emulates search with `find`); `sandbox.list` `metadata` filter semantics (label equality, AND) should be stated; `SandboxRecord.expires_at` must be optional (manual-cleanup sandboxes); error `data.retryable` is needed for `429/502`.

---

## 7. Reusable pieces: wrap the official SDKs, or call REST directly?

| Criterion | Python SDK `opensandbox` 1.1.1 | JS SDK `@alibaba-group/opensandbox` 1.1.1 | Direct REST (stdlib) |
|---|---|---|---|
| Licence | Apache-2.0 | Apache-2.0 | n/a |
| Runtime deps | `pydantic>=2.4.2` (**pydantic-core native wheel**), `python-dateutil`, `attrs`, `httpx`, `httpcore`, `httpx-sse`, `opentelemetry-api` → 18 packages, **15 MB**, SDK itself 393 `.py` files / 3.1 MB | `@opentelemetry/api`, `openapi-fetch`, `undici` → 4 packages, **8.1 MB / 897 files**, Node ≥ 20, ESM only | 0 |
| Fits "installer never runs `pip`/`npm`, plugin ≤ 2000 files / 50 MiB / 10 MiB per file, no symlinks" (design §8) | **No** — native extension per OS/arch/Python ABI cannot be vendored portably | Only after bundling to a single file (esbuild ≈ 1–2 MB) — a build step the plugin repo must own and keep reproducible | **Yes** |
| EPP fit (JSON-RPC over stdio, stateless process per invocation) | async/pool/telemetry features unused; SDK `Sandbox` object model (create-and-hold, auto health check, endpoint cache, metrics event POST) is a poor match for stateless per-call RPC | same | exactly the 20 calls in §2 |
| Needed behaviours | covers lifecycle/exec/files/code and the bare-JSON SSE quirk | same | must implement: SSE reader (~40 lines), multipart builder (~30), WebSocket client for PTY (~120), error mapping (~60) |
| Maintenance risk | tracks the server; frequent releases (`python/sandbox/v0.1.x` → `1.1.x`); pydantic/httpx version coupling | same | spec changes are additive ("prefer additive changes", `specs/AGENTS.md`); pin spec commit + live nightly (§5.2) |
| Telemetry | posts `POST /metrics/events` (best effort) | same | none (we don't opt in) |

**Decision: call REST directly, stdlib-only, in one `provider.py` (≈ 700–900 lines).** Use the SDKs (a) as readable references for edge cases (`adapters/sse.py`, `adapters/command_adapter.py`, `adapters/filesystem_adapter.py`, `endpoint_cache.py`) and (b) **as test oracles** in T4 (create with the SDK, operate with the plugin and vice versa; dev-only dependency, never shipped). Interpreter choice: Python stdlib (`http.client`, `json`, `threading`, `base64`, `ssl`), matching the reference `local-process` plugin and available wherever the Python SDK runs; a Node `provider.mjs` (global `fetch`, no deps) is the alternative if CLI-only machines without Python are a target — the EPP makes the two interchangeable and a second manifest can ship both. Keep the data-plane HTTP client persistent (keep-alive) within one plugin process; the plugin is one process per CLI invocation, so cache the resolved execd endpoint and the code-interpreter probe in memory only.

### 7.1 Suggested plugin layout and order of work

```text
providers/opensandbox/
  abx-provider.toml           # §3
  provider.py                 # EPP loop, method table, config, error mapping   (~250)
  _osb_http.py                # request(), retry (idempotent only), SSE reader, multipart, endpoint cache, Date-skew
  tests/{unit,contract,live}/ # T0, T1/T2, T4
  tests/mock_opensandbox.py   # T1 (+ T3 shim)
  tests/fixtures/ specs/      # recorded responses, vendored specs + SPEC_PIN
  scripts/opensandbox-local-up.sh  scripts/opensandbox_live_smoke.py
```

Order: (1) `initialize` + lifecycle + `ports.url` against T4; (2) `exec.run`/`exec.start` with both framing modes; (3) `files.*`; (4) `process.*`, `sandbox.timeout/pause`; (5) T1 mock + fixtures recorded from T4; (6) `pty` (WebSocket) and, after EPP gap 3, `code.*`; (7) install with `abx provider install alibaba-agent-sandbox/awesome-providers//opensandbox` (or a local directory of that plugin). The shipped plugin is the Node tree in that catalog, not the Python sketch above.

---

## 8. Appendix — evidence and artifacts

| Artifact | Location |
|---|---|
| OpenSandbox sources (studied commit `a6a0135…`; `release-1.1.1` = `531700c…` fetched) | `$WORKDIR/opensandbox-src` |
| Server venv + config + logs, `down`/`up` script | `$WORKDIR` (default `~/.cache/agent-sandbox/opensandbox-local`), `e2e/opensandbox/local-up.sh` |
| Stdlib live smoke (35 checks) | `e2e/opensandbox/live_smoke.py` |
| Official SDK smoke | `e2e/opensandbox/sdk_smoke.py` |
| Real execd binaries (`v1.1.0`, `latest`) | `$WORKDIR/bin/execd`, `$WORKDIR/bin/execd-latest` |
| Key source references | lifecycle spec `specs/sandbox-lifecycle.yml`; execd spec `specs/execd-api.yaml`; auth `server/opensandbox_server/middleware/auth.py:37-120`; routes `server/opensandbox_server/api/{lifecycle,proxy,network_policy,templates}.py`; Docker endpoint resolution `server/opensandbox_server/services/docker/networking.py:300-345`; state mapping `services/docker/docker_service.py:529-557`; runtime registry `services/factory.py`; execd router `components/execd/pkg/web/router.go:45-149`; upload parsing `components/execd/pkg/web/controller/filesystem_upload.go`; command cancel semantics `components/execd/pkg/runtime/command.go:285-335`; proxy `components/execd/pkg/web/proxy.go`; PTY `components/execd/PTY.md`; SDK config `sdks/sandbox/python/src/opensandbox/config/connection.py`; SSE quirk `sdks/sandbox/python/src/opensandbox/adapters/sse.py`; third-party-implementation guidance `docs/api/implementation-compatibility.md`; server config reference `server/configuration.md` |
| Agent Sandbox surface used for the mapping | `$ORIG_REPO/src/agent_sandbox/{api,protocol,models}` and `cli/commands/sandbox*.py` (create/list/info/kill/exec/connect/upload/download/run; `files list/stat/mkdir/rm/mv/search`; `process list/start/info/signal`; `system ports/capabilities/metrics`) |

## 9. Status after the 2026-10-13 live review

The mapping in section 2 was implemented as the `opensandbox` plugin and driven against a real server (`opensandbox-server` 1.1.1, Docker) through `abx` and `Sandbox.create(provider="opensandbox")`. Evidence: [2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md).

| Area | Status |
|---|---|
| Lifecycle (create from an image URI, get, list, connect, kill, `E2009` after kill) | works on both hosts |
| Exec (buffered, streamed, exit code, stderr, env) | works |
| Files (text, 300 KB binary, unicode, list, stat, upload/download through the CLI, typed `E4001`) | works; `files.watch` and signed transfer URLs are not declared (E8004) |
| Timeout, pause, resume | works (SDK; the CLI has no pause/resume command) |
| Port URL | `network.resolve(9000)` returns the server proxy URL |
| Process control | list works; `send_stdin` is E8004 |
| Templates | the create-time template is an image URI mapped by the plugin (`default_image`, `image_aliases`); no `[template]` profile (that table is only for template authoring); `template` commands of the CLI are not provider-aware yet |
| Network policy | the `network_policy` per-create option exists; the egress sidecar was not exercised in this run |
| Credentials | `ABX_OPENSANDBOX_API_KEY`, `ABX_OPENSANDBOX_BASE_URL`; native aliases `OPEN_SANDBOX_API_KEY`, `OPEN_SANDBOX_DOMAIN` |
| Install | pinned git install works from a local clone; the public catalog still ships `ebx-provider.toml` and needs the `abx` rename patch (`cli/e2e/providers/awesome-providers-abx-rename.patch`) |
