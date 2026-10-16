# OpenSandbox provider 研究（不是当前适配器）

> 状态：研究文档与 2026-10-13 exec 插件记录。当前交付的适配器以 [provider-opensandbox-mapping.md](../design/provider-opensandbox-mapping.md) 为准。[英文原文](../../en/archive/provider-opensandbox-research.md)。下述版本、实测和部署命令均属于历史研究，不代表本次翻译重新执行了验证，也不应把旧插件当作当前安装路径。

## 0. 摘要

* OpenSandbox 是源自阿里巴巴、采用 Apache-2.0 许可的开源沙箱平台；仓库已迁到 `opensandbox-group/OpenSandbox`，`alibaba/OpenSandbox` 通过 301 跳转。它有两个 HTTP 接口面：**生命周期服务**（FastAPI，`OPEN-SANDBOX-API-KEY` 请求头，`/v1/sandboxes…`）和每个沙箱内的 **`execd`** 守护进程（Go/Gin，命令、文件、代码、PTY，可选 `X-EXECD-ACCESS-TOKEN`）。后者通过生命周期服务的 `GET /v1/sandboxes/{id}/endpoints/{port}` 解析地址。
* 它以**镜像而非模板**为基础：`template` 对应容器镜像 URI。Docker 运行时没有模板构建或注册中心；`/templates` 是 fsb microVM 目录，在 Docker 上返回 `501`。
* 历史研究证明，**可以在普通 Linux 开发机或 CI runner 上真实运行，不需要秘密或 Kubernetes**：通过 apt 安装 Docker（`docker.io`），再安装 `opensandbox-server==1.1.1`。镜像已拉取时，`e2e/opensandbox/local-up.sh up` 约需 5 秒；随后 `live_smoke.py` 的生命周期、SSE 执行、后台命令、文件、TTL、暂停/恢复和删除共 35 项检查通过。出口网络策略也做过实测。服务仅有 `docker`、`kubernetes` 两种运行时，**没有免 Docker 的本地运行时**；但真实 `execd` 可以作为普通进程独立运行，因此可建立无需 Docker 的真实数据面测试层（§5.3）。
* **映射结论**：生命周期、同步/流式执行、文件、端口 URL、PTY、暂停/恢复为原生能力；TTL 修改、删除、搜索深度、用户切换、stdin、进程列表/信号和能力探测需要模拟；文件监听、签名传输 URL、模板构建/读取、磁盘规格和每进程 stdin 不支持，应返回类型化错误。只有包含解释器运行时的镜像才原生支持有状态代码上下文；否则 `/code` 返回 `500`，`/code/context` 会挂起。
* **当时建议的实现**是只用 Python 标准库直接调用 REST 的单文件 `exec` 插件，不包装官方 SDK。Python SDK 有 pydantic-core 原生 wheel、18 个包约 15 MB；JS SDK 为 897 个文件约 8 MB。它们与“安装器不运行 pip/npm、插件最多 2000 文件/50 MiB、无原生代码”的边界不合。SDK/规范仍可作为实现参考和测试判据。当前交付路径已改为目录中的 Node provider，见本文开头。
* 映射中发现 EPP/1 草案的**四类主要缺口**（§6）：字符串进程 ID、`exec.start` 的 `detached` 标志、缺失的 `code.*` 方法、每沙箱能力探测；大文件传输等问题也在该节展开。

---

## 1. OpenSandbox 是什么

### 1.1 身份、许可与研究版本

| 项目 | 值 |
|---|---|
| 名称 | **OpenSandbox**，面向 AI 应用的通用沙箱平台 |
| 仓库 | <https://github.com/opensandbox-group/OpenSandbox>；旧地址 `https://github.com/alibaba/OpenSandbox` 通过 HTTP 301 跳转。搜索结果仍有两个地址，README 徽章和 pyproject 使用新组织。文档：<https://open-sandbox.ai> |
| 许可 | **Apache-2.0**：根目录、server 和各 SDK 的 LICENSE；源码声明 Copyright 2025 The OpenSandbox Authors。与 Agent Sandbox 许可兼容。只有 vendor/复制源码时才涉及 NOTICE 义务；本方案只保存规范与录制 fixture，并保留许可头。 |
| 研究提交 | `a6a013554fcde095f367d68ac35af5e7bd967a6e`，`main`，2026-10-12 14:30 +0800；浅克隆位于 `$WORKDIR/opensandbox-src` |
| 实际运行的发布版 | umbrella tag `release-1.1.1` = `531700ca18a7fa5fab6a2f25d6dc68a76eddab12`（2026-10-09）。其 `sandbox-lifecycle.yml`、`execd-api.yaml` 与研究提交**字节相同**；git diff 无输出，只有 `egress-api.yaml` 不同。**[实测]** |
| 发行物 | PyPI：`opensandbox-server==1.1.1`（`GET /version` 的返回）、`opensandbox==1.1.1`、`opensandbox-code-interpreter==1.1.1`；npm：`@alibaba-group/opensandbox@1.1.1`（Apache-2.0、Node ≥20）；Go：`github.com/alibaba/OpenSandbox/sdks/sandbox/go` v1.1.1；另有 Java/Kotlin、C#/.NET SDK 和 `opensandbox-cli`（`osb`） |
| 镜像 | `opensandbox/execd:{v1.1.0,latest}`、`opensandbox/code-interpreter:v1.1.0`、`opensandbox/egress:v1.1.7`、`opensandbox/ingress:*` |
| API 规范版本 | lifecycle `info.version: 0.1.0`（OpenAPI 3.1，2406 行）；execd `info.version: 1.0.0`（3408 行）；另有 egress、diagnostics 规范 |

> **必须关注版本差异。** 1.1.1 服务包默认使用 **`opensandbox/execd:v1.1.0`**（2026-08-28 构建），但 1.1.1 规范中两项行为在该镜像中**不存在 [实测]**：(a) `POST /command` 的 `argv`，v1.1.0 返回 `400 … Field validation for 'Command' failed on the 'required' tag`；(b) 输出换行保留，v1.1.0 每行一个 stdout 事件且移除 `\n`/`\r`，后续构建（提交 `163af0a3`、`380322ba`）才保留。2026-10-11 的 `execd:latest` 同时具备这两项行为，是历史 local-up 脚本配置的镜像。插件需要兼容两者（§2.2）。

### 1.2 架构

```text
客户端（SDK / osb CLI / 插件）
  │ ① 生命周期 HTTP：OPEN-SANDBOX-API-KEY
  ▼
Lifecycle server（FastAPI）── Docker / k8s API ──► 沙箱容器 / Pod / microVM
  server/opensandbox_server                        用户 entrypoint
  鉴权、校验、sqlite|pg|redis 元数据                 execd :44772
  docker | kubernetes(+fsb)                        /command /files /code /pty
  │                                                /session /metrics /proxy/<port>
  └─ GET /v1/sandboxes/{id}/endpoints/44772 ───────► ② 数据面 HTTP/SSE/WS
     Docker bridge：<host>:<hostport>/proxy/44772      [X-EXECD-ACCESS-TOKEN]
                                                   egress sidecar :18080
                                                   DNS / nft 允许拒绝策略
                                                   （仅配置 networkPolicy 时）
```

* **控制面**：`server/opensandbox_server`（FastAPI）；路由 `api/lifecycle.py`、`proxy.py`、`network_policy.py`、`templates.py`、`devops.py`；服务在 `services/docker/*`、`k8s/*`、`fast_sandbox/*`。运行时为单机 `docker` 与 `kubernetes`；后者包含 BatchSandbox、kubernetes-sigs `agent-sandbox` workload provider，以及 fsb/fast-sandbox microVM 模板后端。`services/factory.py` **只注册这两种**，没有进程内/本地运行时。
* **数据面**：`components/execd`（Go ≥1.25、Gin；`pkg/web/router.go`）。`bootstrap.sh` 通过挂载/复制 execd 镜像内容将其注入用户容器，在 `44772` 端口启动。Docker bridge 模式中它还是**端口网关**：`pkg/web/proxy.go` 将 `/proxy/<port>/…` 的 HTTP、SSE、WebSocket 反向代理到沙箱的 `127.0.0.1:<port>`。因此任意端口的 endpoint 返回 `<host>:<execd-hostport>/proxy/<port>`（`server/…/services/docker/networking.py:335`）。**[源码][实测]**
* 其他组件：每沙箱 `networkPolicy` sidecar `components/egress`、k8s 网关 `components/ingress`、`components/nodeagent`、`kubernetes/` operator；server 与 execd 的契约位于 `specs/`。
* 第三方实现指南 `docs/api/implementation-compatibility.md` 明确以契约为接口，并要求固定目标规范 revision 和 SDK 版本。

### 1.3 生命周期 API — `specs/sandbox-lifecycle.yml`

基址为 `http://host:8080/v1`；服务也提供不带 `/v1` 的路由。

**鉴权 [规范][源码][实测]**：除 `/health`、`/version`、`/docs`、`/redoc`、`/openapi.json` 和 `…/proxy/…` 外均使用 `OPEN-SANDBOX-API-KEY: <key>`（`middleware/auth.py:37-120`）。缺失返回 `401 {"code":"MISSING_API_KEY"…}`，错误返回 `401 {"code":"INVALID_API_KEY"…}`。服务未配置 api_key 时跳过鉴权，但启动要求 `OPENSANDBOX_INSECURE_SERVER=YES` 或 TTY 确认，见 `configuration.md`。官方 SDK/CLI 使用 `OPEN_SANDBOX_API_KEY`、`OPEN_SANDBOX_DOMAIN`（host[:port]，默认 localhost:8080）、`OPEN_SANDBOX_PROTOCOL`、`OPEN_SANDBOX_USE_SERVER_PROXY`、`OPEN_SANDBOX_REQUEST_TIMEOUT`；定义见 `sdks/sandbox/python/src/opensandbox/config/connection.py:140-142`、`cli/src/opensandbox_cli/config.py:105-120`。

每个响应携带 `X-Request-ID`：

| 方法 + 路径 | 用途 | 请求 / 响应要点 | 成功 | 主要错误 |
|---|---|---|---|---|
| `POST /sandboxes` | 创建 | 下述 `CreateSandboxRequest` → `{id,status,metadata,expiresAt?,createdAt,entrypoint,extensions?,platform?}` | `202` **[实测]**，Docker 此时已 Running | `400 SANDBOX::INVALID_METADATA_LABEL`、FastAPI `422 {"detail":[…]}`（不是 ErrorResponse）、配额 403、409、池 429、500 DOCKER::SANDBOX_IMAGE_PULL_FAILED |
| `GET /sandboxes` | 列表 | `state` 可重复、OR；`metadata` 为单个 URL 编码 `k=v&k2=v2`、AND；`page≥1`，`pageSize` 1..200、默认20；返回 `{items,pagination{page,pageSize,totalItems,totalPages,hasNextPage}}` | 200 | 400、401 |
| `GET /sandboxes/{id}` | 详情 | `{id,image{uri}|snapshotId,platform?,status{state,reason?,message?,lastTransitionAt?},metadata,extensions?,allocation?,entrypoint,expiresAt?,createdAt}` | 200 | 404 DOCKER::SANDBOX_NOT_FOUND |
| `DELETE /sandboxes/{id}` | 销毁 | 无请求体 | 204 | **第二次删除404，不幂等 [实测]**；409 |
| `PATCH /sandboxes/{id}/metadata` | 合并元数据 | RFC7396 平面对象，null 删除；保留 opensandbox.io/ 前缀；返回完整 Sandbox | 200 | 400 |
| `POST /sandboxes/{id}/pause`、`/resume` | 暂停/恢复 | Docker pause/unpause；k8s 取决于运行时 | 202；Docker同步观察到 Paused ⇄ Running **[实测]** | 409 |
| `POST /sandboxes/{id}/renew-expiration` | 设置**绝对**到期时间 | `{expiresAt: RFC3339}` → `{expiresAt}`；可缩短，不受 max_sandbox_timeout_seconds 上限约束 | 200 **[实测]** | 400 |
| `GET /sandboxes/{id}/endpoints/{port}` | 解析端口入口 | `use_server_proxy=bool` 返回 `<server>/v1/sandboxes/{id}/proxy/{port}`；`expires=<epoch s>` 仅 k8s 网关签名路由；返回 `{endpoint:"host:port[/path]",headers?}`，**无scheme** | 200 **[实测]** | 400、404、500 NETWORK_MODE_ENDPOINT_UNAVAILABLE |
| `GET/PUT/PATCH/DELETE /sandboxes/{id}/networkpolicy` | 读/替换/合并/删出口策略 | 转发 sidecar；`{defaultAction:allow|deny,egress:[{action,target:FQDN或*.wildcard}]}` → PolicyStatusResponse | 200 **[实测]** | 无sidecar时502 BACKEND_CONNECTION_FAILED **[实测]** |
| `POST /sandboxes/{id}/snapshots`、`GET /snapshots`、`GET/DELETE /snapshots/{id}` | 持久快照，可作创建源 | `{id,sandboxId,name?,status{Creating|Ready|Failed|Deleting}}` | 202/200/204；实测创建202 Creating | — |
| `GET/POST/DELETE /templates[/{id}]` | **仅fsb microVM黄金镜像** | `{image,publish(s3://…),resourceLimits,…}` | — | Docker上 **501 FSB::API_NOT_SUPPORTED [实测]** |
| `POST /metrics/events` | SDK遥测接收 | MetricsEvent | 204 | 与适配无关 |
| `GET /health`、`GET /version` | 存活/版本 | `{"version":"1.1.1"}` | 200 **[实测]** | — |
| `GET /sandboxes/{id}/diagnostics/{logs,events}` | 诊断 | `specs/diagnostic-api.yml` 的日志/事件描述符 | — | 未使用 |

**`CreateSandboxRequest`**（规范约1710–1930行；✓表示历史实测字段）：

| 字段 | 类型/规则 | 说明 |
|---|---|---|
| `image` ✓ | `{uri,auth?{username,password}}` | 与 snapshotId、templateId（fsb）、extensions.poolRef 四选一；私有仓库用 image.auth |
| `entrypoint` ✓ | 至少一项的 string[] | **提供image时必填**；缺少得到422 `Entrypoint is required when image is provided.` ✓。须为持续进程，如 `["tail","-f","/dev/null"]`；OpenSandbox在其外包装execd |
| `resourceLimits` ✓ | 字符串映射，如 cpu:"500m"、memory:"512Mi"、gpu:"1" | 标准模式**必填**，缺少422 ✓。未知键如disk在Docker中被接受但**忽略** ✓ |
| `resourceRequests` | 同上 | 仅k8s，Docker忽略 |
| `timeout` ✓ | 秒整数 **≥60**；10返回422 ✓；null/省略表示**不自动过期，须手动清理** ✓ | 受服务max_sandbox_timeout_seconds限制。TTL后直接移除，GET为**404**而非Terminated ✓ |
| `env` ✓ | string→string | execd启动的命令可见 ✓ |
| `metadata` ✓ | string→string | 创建时校验K8s标签 ✓：键 `[prefix/]name`；值≤63字符且匹配 `[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?`，否则400 SANDBOX::INVALID_METADATA_LABEL。name通常做人类可读名称 |
| `networkPolicy` ✓ | 见上 | 要求服务配置 `[egress] image`，且Docker network_mode="bridge" |
| `platform` | `{os:linux|windows,arch:amd64|arm64}` | 平台选择 |
| `volumes[]` | `{name,mountPath,readOnly?,subPath?,host|pvc|ossfs}` | host绑定须被服务端 `[storage] allowed_host_paths` 允许 |
| `lifecycle` | `{preStart{command[],timeoutSeconds},periodic[…]}` | 由execd执行 |
| `secureAccess`、`credentialProxy`、`templateId`、`snapshotId`、`extensions{poolRef,…}` | — | k8s/网关/fsb专用 |

**状态 [规范]**：`Pending → Running ⇄ (Pausing → Paused → Resuming) → Stopping → Terminated`，任意状态可进入Failed；客户端须容忍未知值。Docker只产生Running、Paused、Pending、Terminated、Failed（`services/docker/docker_service.py:529-557`）。

**错误**：通常是 `{code,message}`，code带命名空间，如 `DOCKER::SANDBOX_NOT_FOUND`、`SANDBOX::INVALID_METADATA_LABEL`、`DOCKER::SANDBOX_IMAGE_PULL_FAILED`、`FSB::API_NOT_SUPPORTED`、`KUBERNETES::QUOTA_EXCEEDED`。例外是FastAPI请求校验，返回 `422 {"detail":[{type,loc,msg,input}]}` **[实测]**。错误映射还须兼容下述execd令牌失败的第三种 `{"error":"..."}`。

### 1.4 `execd` API

规范：`specs/execd-api.yaml`；路由：`components/execd/pkg/web/router.go:49-149`。

**鉴权 [规范][实测]**：通过 `-access-token` 或k8s secure-access启用时，使用 `X-EXECD-ACCESS-TOKEN`。错误/缺失返回 `401 {"error":"Unauthorized: invalid or missing header X-EXECD-ACCESS-TOKEN"}`。Docker默认**无令牌**且Endpoint.headers为空 **[实测]**；网关/secure-access会返回每次数据面请求必需的头，包括 `OpenSandbox-Ingress-To` 等路由头。插件须在**每次execd请求原样转发Endpoint.headers**。

**流格式 [实测]**：Content-Type是text/event-stream，但帧是**以空行分隔的裸JSON，没有 `data:` 前缀**。参考SDK `adapters/sse.py` 的legacy bare-JSON frames。读取器应同时接受 `JSON\n\n` 与标准 `data: JSON\n\n`。事件形状为 `{type,text?,timestamp,execution_count?,execution_time?,results?{mime→value},error?{ename,evalue,traceback[]}}`；type为 init、status、error、stdout、stderr、result、execution_complete、execution_count、ping之一。

```text
POST /command {"command":"echo out; echo err >&2; exit 3"}
{"type":"init","text":"<commandId>"}   ← 首事件给出命令ID
{"type":"ping","text":"pong"}
{"type":"stdout","text":"out\n"}  {"type":"stderr","text":"err\n"}
{"type":"error","error":{"ename":"CommandExecError","evalue":"3","traceback":["exit status 3"]}}
# 非零退出后不再有execution_complete
# 成功以 {"type":"execution_complete","execution_time":<ms>} 结束
# 超时：error evalue "-1"、traceback ["signal: killed"]，无法区别外部SIGKILL
# 启动失败：evalue为错误消息，例如uid/gid切换能力不足
```

| 组 | 方法 + 路径 | 语义（✓表示历史实测） |
|---|---|---|
| health | `GET /ping` →200空体 ✓；`GET /ready`、`POST /internal/init` | SDK轮询就绪，后者为运行时初始化门禁 |
| command | `POST /command {command|argv[],cwd?,background?,timeout?毫秒,uid?,gid?,envs?}` →SSE | command/argv二选一；argv要求比v1.1.0更新的execd ✓；cwd展开$VAR/~；**无stdin字段**，传入被忽略，cat挂起 ✓；gid须伴uid；切换需要CAP_SETUID/SETGID ✓；断连会SIGKILL进程组（runtime/command.go:300-330） |
| command status | `GET /command/status/{id}` | `{id,content,running,exit_code?,error?,started_at,finished_at?}`，保留≥24h ✓；未知ID404 `{code:"INVALID_REQUEST_BODY",message:"command not found: …"}` ✓ |
| command logs | `GET /command/{id}/logs?cursor=N` | text/plain，stdout+stderr**合并**，头EXECD-COMMANDS-TAIL-CURSOR ✓；只支持background:true，前台返回400 not running in background ✓ |
| command delete | `DELETE /command?id=` | 200，context cancel导致**整个进程组SIGKILL** ✓，不是温和的SIGINT |
| session | `POST /session {cwd?}` →{session_id}；`POST /session/{id}/run {command,cwd?,timeout?}` →SSE；`DELETE /session/{id}` | 有状态bash，cd/export保留 ✓ |
| files info | `GET /files/info?path=a&path=b` | `{path:FileInfo}`；**任一路径不存在则整个调用404 FILE_NOT_FOUND** ✓。FileInfo含path、type(file/directory/symlink/other)、size、modified_at、created_at、owner、group、mode；mode是**以十进制整数表示的八进制数字**（644/755） ✓ |
| files delete | `DELETE /files?path=…` | 仅文件；不存在200幂等 ✓；目录500 RUNTIME_ERROR path is a directory ✓ |
| files move | `POST /files/mv [{src,dest}]` | ✓；不覆盖，目标已存在500 RUNTIME_ERROR destination path already exists ✓；源缺失404；实测会建目标父目录，虽规范要求已存在 |
| files search | `GET /files/search?path=&pattern=` | 递归glob，如*.txt、**/*.txt、默认**；按模式返回文件和目录的FileInfo[] ✓ |
| files edit | `POST /files/replace[?verbose=true]`、`POST /files/permissions {path:{owner?,group?,mode?}}` | 内容替换、权限设置 |
| files upload | `POST /files/upload` multipart | 重复配对的metadata与file部件；metadata为JSON `{path,owner?,group?,mode?}`，**必须是有filename的文件部件**，普通表单字段400 metadata file is missing ✓；file为application/octet-stream；自动建父目录 ✓；3MB往返字节一致 ✓ |
| files download | `GET /files/download?path=` | application/octet-stream；支持Range/206；`?offset=&limit=`为从1开始的行模式text/plain ✓；缺失404；**目录也返回200**，插件须先stat ✓ |
| dirs | `GET /directories/list?path=&depth=1`；`POST /directories {path:{mode}}`；`DELETE /directories?path=` | list排除根、字典序、不跟随symlink，非目录400 ✓；POST是幂等mkdir -p ✓；DELETE递归移除，缺失404 ✓ |
| code | `POST /code/context {language}` →{id,language}；`GET /code/contexts[?language=]`；`GET/DELETE /code/contexts/{id}`；`DELETE /code/contexts?language=`；`POST /code {context{id?,language},code}` →SSE；`DELETE /code?id=`中断 | Jupyter后端，上下文跨调用保留，x=41再x+1为42 ✓；stdout/stderr/result（results:{"text":"42"}）/execution_count/error(ename,evalue,traceback)后execution_complete；异常为status:error+error+execution_complete ✓；省略context.id用每语言默认上下文 ✓。解释器镜像语言：python/java/go/typescript/javascript/bash |
| PTY | `POST /pty {cwd?}` →201 {session_id} ✓；`GET/DELETE /pty/{id}`；WebSocket `GET /pty/{id}/ws[?pty=0&since=&takeover=1&mode=viewer]` | 二进制帧0x00 stdin、0x01 stdout、0x02 stderr、0x03 replay；文本JSON为resize/signal/ping/exit；见components/execd/PTY.md。**不在OpenAPI中**，实现兼容指南确认该点 |
| metrics | `GET /metrics` →{cpu_count,cpu_used_pct,mem_total_mib,mem_used_mib,timestamp}；`GET /metrics/watch` SSE | ✓；反映宿主机而非cgroup限制 |
| proxy | 任意 `/proxy/<port>/<path>` | 到沙箱127.0.0.1:<port>的HTTP/SSE/WS代理 ✓，Docker任意端口入口机制 |
| isolated | `/v1/isolated/*`；每身份 `/v1/filesystem/{uid}/{gid}/…` | bwrap overlay会话；本研究范围外 |

**解释器可用性 [实测]**：无解释器的 `python:3.12-slim` 上，GET /code/contexts返回200 []（会误导探测），POST /code返回500 RUNTIME_ERROR，消息为 `error running codes language runtime server not configured, please check your image runtime`；POST /code/context**始终不返回**，10秒客户端超时。使用 `opensandbox/code-interpreter:v1.1.0` 且入口为 `/opt/code-interpreter/code-interpreter.sh` 时，Jupyter约25秒预热后工作正常。

### 1.5 官方 SDK 与工具（复用候选，见§7）

目录为 `sdks/sandbox/{python,javascript,go,kotlin,csharp}`、`sdks/code-interpreter/{python,javascript,csharp}`、`sdks/mcp/sandbox`、`cli/`（osb）。Python SDK由生成客户端和适配器组成：`adapters/{sandboxes,command,filesystem,health,egress,…}_adapter.py`；`api/{lifecycle,execd,egress,diagnostic}` 由规范生成；`adapters/sse.py`处理裸JSON帧，`adapters/endpoint_cache.py`缓存入口。历史研究未修改该SDK即通过本地服务的create→commands.run→get_info→get_endpoint(8000)，脚本为 `e2e/opensandbox/sdk_smoke.py`。

---

## 2. 逐操作映射

图例：**N**为1:1原生调用，**E**为客户端逻辑/额外调用模拟，**U**为类型化不支持。EPP方法名来自 [providers-and-credentials.md §7.4](../design/providers-and-credentials.md)。`base` 为生命周期基址（…/v1）；`execd` 是 `GET /sandboxes/{id}/endpoints/44772` 返回的Endpoint.endpoint加HTTP(S) scheme，每次调用均转发Endpoint.headers。

### 2.1 沙箱生命周期（sandbox.lifecycle、sandbox.timeout、sandbox.pause）

| Agent Sandbox 操作 / EPP | OpenSandbox调用 | 分类 | 映射要点 |
|---|---|---|---|
| `Sandbox.create(template,timeout,metadata,envs,cpu,memory,disk,gpu,secure)` / abx create；`sandbox.create` | POST base/sandboxes；非Running则在ready_timeout内轮询GET；随后解析44772入口并轮询execd/ping至200，遵循官方SDK | **N+E** | template→image.uri：默认镜像/别名见§3，含:或/视为镜像URI。timeout秒**至少60**，上调时data附警告；超过服务上限的400/422→-32006。envs→env；cpu整数核→resourceLimits.cpu:"<n>"；memory MB→"<n>Mi"；省略默认500m/512Mi，API要求必填。entrypoint默认tail -f /dev/null，解释器镜像用其启动脚本。metadata须校验标签，不合法→-32006并指出键和规则，不静默改写。gpu数字串→resourceLimits.gpu；"A10"等GPU类型→-32006。**disk拒绝为-32006**，不假装Docker已应用。secure=true→secureAccess:true，仅k8s网关，否则服务错误→-32006。provider_options/--opt包括entrypoint、network_policy JSON、platform、registry_username/password→image.auth。返回 `{sandbox_id:id,template:image,status,created_at,expires_at,metadata}`，timeout=null时不含expires_at |
| `Sandbox.connect(id)` / abx connect记录部分 / info；`sandbox.connect`、`sandbox.get` | GET base/sandboxes/{id} | **N** | 状态见§2.5；保留metadata，template=image.uri或snapshot:<id> |
| `Sandbox.list(status,limit,offset)` / abx list；`sandbox.list` | GET …/sandboxes?state=…&metadata=…&page=&pageSize≤200 | **N+E** | EPP cursor为下页页码；status反向映射为state；limit/offset分页后切片；metadata为服务端标签相等匹配 |
| `Sandbox.kill_by_id` / abx kill；`sandbox.kill` | DELETE …/sandboxes/{id} | **N+E** | 204；EPP要求幂等，故吞掉历史实测第二次删除404；409等待1秒重试一次，仍失败→-32000 |
| set_timeout(seconds) / refresh / abx sandbox timeout；`sandbox.set_timeout` | POST …/renew-expiration {expiresAt} | **E** | OpenSandbox用绝对时刻，Agent Sandbox用从现在算的TTL：expiresAt=server_now+timeout。先廉价GET沙箱，从Date头取server_now避免客户端时钟偏差。timeout=null原本无到期，调用renew后可转TTL ✓ |
| pause / resume；`sandbox.pause`、`sandbox.resume` | POST …/pause或…/resume；30秒内轮询到Paused/Running | **N** | 202；Docker同步pause、cgroup freezer实测可用。状态不对409→-32000；501或k8s不支持→-32003 |
| 元数据patch、快照（snapshotId创建源）、出口策略读/patch | PATCH …/metadata、POST …/snapshots、…/networkpolicy | — | 未来sandbox.snapshot/network.policy候选，v1不声明；创建时network_policy选项已可传 |

### 2.2 命令与进程（exec.run、exec.stream、process.manage、pty）

| Agent Sandbox 操作 / EPP | OpenSandbox调用 | 分类 | 映射要点 |
|---|---|---|---|
| commands.run(cmd,cwd,envs,user,timeout) / abx exec、run；`exec.run {cmd,args,env,cwd,user,timeout,stdin?}` →{exit_code,stdout,stderr} | POST execd/command SSE | **N+E** | init.text为命令ID；拼接stdout/stderr；execution_complete退出0；CommandExecError时将evalue转int；无法转整数的启动失败→126，stderr带消息。插件设置timeout且收到-1/signal:killed→-32005 CommandTimeoutError。支持时cmd+args→argv；v1.1.0的400 Command required则回退shlex.join([cmd,*args])，每沙箱探测一次并缓存。cwd原样、env→envs、秒→毫秒。新版text保留换行；旧版每行移除换行：若整个流无\n/\r且多事件，则以\n拼接并补末尾\n；单片段歧义时原样返回。实测固定latest/≥380322ba验证字节一致。execd为文本，不提供stdout_b64/stderr_b64 |
| user= | POST /command的uid/gid | **E** | 数字直接uid及gid；用户名先通过argv执行id -u、id -g，多2次调用并缓存。须CAP_SETUID/SETGID，Docker默认drop_capabilities保留；拒绝时错误指出能力并给-32000建议 |
| 单次run的stdin | 无原生stdin | **E** | 上传 `/tmp/.abx-stdin-<uuid>`，以shell重定向给命令，捕获rc、删除临时文件后原rc退出；argv模式包装exec "$@"。交互stdin不能模拟，-32003，改用PTY |
| commands.stream / shell-stream；exec.start + exec.output/exec.exit | POST /command SSE | **N** | 每个stdout/stderr事件立即发exec.output，process_id=init.text；最后且只发一个exec.exit，退出规则同run。断连会杀前台进程，故attached streaming要求宿主保持插件存活 |
| commands.start(background=True) / abx sandbox process start；exec.start及建议detached:true（§6） | POST /command {background:true}立即init+execution_complete；后续GET /command/{id}/logs?cursor= | 启动**N**、追随**E** | ID为32位十六进制**字符串**，但ProcessInfo.pid是int，见§6。每250毫秒轮询模拟exec.output；后台日志合并，无法分stdout/stderr，报告stream:"stdout"；用EXECD-COMMANDS-TAIL-CURSOR推进 |
| commands.list / process list；process.list | 通过exec运行 `ps -eo pid=,ppid=,user=,etime=,args=` | **E** | 无列表API；兼容ps变体或busybox的/proc遍历；解析pid:int、ppid、user、elapsed、cmd。镜像须含ps；原CLI的process info/ports已调用ps/ss（历史sandbox_process.py:143、sandbox_system.py:190） |
| commands.kill(pid) / process kill；process.kill | 数字PID执行kill -9；execd命令ID用DELETE /command?id= | **N/E** | DELETE是进程组SIGKILL ✓ |
| commands.send_signal(pid,sig) / process signal；process.signal | 数字PID执行kill -<sig>；命令ID仅sig=9可DELETE | **E** | 其他信号对命令ID返回-32003，提示须数字PID；除PTY signal帧外无信号API |
| commands.send_stdin(pid,data)；process.stdin | 无 | **U** | -32003；/command无stdin通道，使用pty.*或bash session。拒绝用/session/{id}/run模拟，因语义会改变 |
| process info | CLI已通过exec.run运行ps -p | **E** | 保持原CLI行为 |
| get_terminal / connect --pty；pty.open/write/resize/close与pty.output | POST /pty后GET /pty/{id}/ws | **N** | RFC6455客户端：Python标准库无现成实现，需约120行处理客户端mask、ping/pong、文本/二进制帧，或延后到v1.1并不声明pty。resize→{type:"resize",cols,rows}；close→DELETE /pty/{id} |
| run_code与有状态create/list/remove_context；EPP/1缺方法（§6） | POST /code/context（**10秒超时防挂起**）、GET /code/contexts、DELETE /code/contexts/{id}、POST /code SSE | **N** | stdout/stderr/result/error映射CodeResult；500 runtime not configured或创建上下文超时→-32003。restart_context用DELETE+POST模拟，ID改变，须文档说明 |
| 无解释器镜像的run_code | 无 | **E** | SDK的CodeContextModule.run（api/code.py:60-160）在无代码服务时回退“写临时文件+shell运行解释器”，故仍可通过exec.run/files.write工作 |

### 2.3 文件（files.rw；不提供files.watch、files.transfer）

| Agent Sandbox 操作 / EPP | OpenSandbox调用 | 分类 | 映射要点 |
|---|---|---|---|
| files.read/read_bytes/download；files.read→{content_b64,size} | 先GET /files/info检查类型，再GET /files/download | **N+E** | 目录下载也200，须先stat并对目录抛FileOperationError（-32006/E4000）；404 FILE_NOT_FOUND→-32002、sdk_code=E4001。base64-in-JSON会放大体积，EPP每行8MiB；服务支持Range，可按offset每次≤4MiB分块，见§6 |
| files.write/upload；files.write {path,content_b64,mode?} | POST /files/upload multipart：metadata文件部件+file | **N** | metadata={path,mode}且必须有filename ✓；自动建父目录；mode从0o644转为数字644。用标准库email或手写multipart |
| files.list(path) / abx sandbox files list；files.list→entries | GET /directories/list?path=&depth=1 | **N** | entries含name、path、type、size、mtime；name取basename；symlink/other按file并加symlink:true；modified_at→mtime；非目录400→-32006；缺失404→-32002/E4001 |
| files.stat/get_info / stat；files.stat | GET /files/info?path= | **N** | 响应以路径为键，mode是八进制数字 |
| files.exists | 同stat，由SDK组合 | **E** | 404 FILE_NOT_FOUND→false |
| files.make_dir/mkdir；files.mkdir | POST /directories {path:{mode:755}} | **N** | mkdir -p幂等 ✓；路径是文件500 not a directory→-32006 |
| files.remove/rm；files.remove | 先GET /files/info，再按文件/symlink选DELETE /files，目录选DELETE /directories | **E** | 端点按类型分开，文件端点删目录会500 ✓；缺文件200；缺目录404→-32002/E4001。是否吞缺失须与内置provider的remove契约一致 |
| files.move/rename/mv；files.move | POST /files/mv [{src,dest}] | **N+E** | 文件和目录均可 ✓；无覆盖，目标存在500→-32006 destination exists。若Agent Sandbox约定覆盖，先DELETE目标模拟 |
| files search --pattern --max-depth | GET /files/search?path=&pattern=；CLI原用find | **N+E** | glob递归，客户端按路径段数过滤max-depth，仅文件筛type==file。CLI可保留原find回退 |
| files.watch(path)；files.watch | 无 | **U** | -32003/ProviderFeatureNotSupportedError；无watch API，不用目录轮询假冒事件类型 |
| upload_url/download_url；files.transfer | 无 | **U** | -32003；普通download URL未签名且需要头，不能等同签名/过期链接 |
| chmod/replace，EPP尚无方法 | POST /files/permissions、/files/replace | 可用**N** | EPP未加files.chmod前，仅能exec.run chmod |

### 2.4 端口、能力、模板

| Agent Sandbox 操作 / EPP | OpenSandbox调用 | 分类 | 映射要点 |
|---|---|---|---|
| network.get_url(port) / abx url / system ports的URL部分；ports.url→{url,headers?} | GET base/sandboxes/{id}/endpoints/{port}[?use_server_proxy=true] | **N** | 返回host:port[/path]无scheme，按base_url的https/http补齐；secure-access/gateway头原样返回。use_server_proxy使入口经过生命周期服务，适合容器内服务或无网关k8s导致宿主端口不可达。Docker bridge任意非8080端口均经execd /proxy/<port> ✓；仅HTTP/SSE/WS，不是原生TCP |
| system ports监听列表；exec.run | ss -tlnp | **E** | 保持CLI已有shell行为 |
| resolve_capabilities / system capabilities；initialize.features及建议sandbox.capabilities | 静态manifest features+每沙箱探测 | **E** | SDK api/capability.py现从模板推导，OpenSandbox无模板元数据。shell←exec.run、files←files.rw、ports←ports.url、terminal←pty；仅POST /code {context:{language:"python"},code:"None"}返回200+execution_complete时加入code；500 runtime not configured不加入。不能用GET /code/contexts（任意镜像200 []）或POST /code/context（挂起）探测。按沙箱缓存到进程结束 |
| template镜像 / templates.read（list/info） | 无目录API | 读取**U**、使用近似**N** | template是镜像URI，创建时原生使用；Docker GET /templates是fsb microVM目录，501 FSB::API_NOT_SUPPORTED ✓。不声明templates.read，对其abx template list→E8004。未来可把image_aliases作为只读列表 |
| templates.build（build/deploy/delete）、deploy、install | 无 | **U** | 按设计§7.7在任何Docker工作前报E8004。镜像自行构建推送后 `abx create --template <image-uri> --provider opensandbox`。无法拉取→500 DOCKER::SANDBOX_IMAGE_PULL_FAILED（pull access denied/not found）→-32002、sdk_code=E2001 TemplateNotFound |
| storage.mount、network.vpc、ports.domain扩展 | volumes[]、k8s | v1 **U** | host/pvc/ossfs存在，但不等同Agent Sandbox的OSSMount契约，故不声明 |

### 2.5 横切映射

**SandboxRecord.status**：Pending→creating、Running→running、Pausing→paused（此时exec已会失败）、Paused→paused、Resuming→creating、Stopping→stopping、Terminated→stopped、Failed→error；未知→error并把原状态放data。列表筛选反向为 running→Running、paused→Paused/Pausing、creating→Pending/Resuming、stopping→Stopping、stopped→Terminated、error→Failed。

| OpenSandbox信号 | EPP错误 | 宿主异常 |
|---|---|---|
| 生命周期401 MISSING_API_KEY/INVALID_API_KEY、execd401 {error} | -32001，sdk_code E1001 | InvalidAPIKeyError |
| 生命周期404 *SANDBOX_NOT_FOUND、execd404 FILE_NOT_FOUND/command not found | -32002；文件为E4001，沙箱/命令不附sdk_code | SandboxError家族 |
| 501、execd NOT_SUPPORTED、代码运行时未配置500、上下文创建超时 | -32003 | ProviderFeatureNotSupportedError（E8004） |
| 403 KUBERNETES::QUOTA_EXCEEDED、池429 | -32004；429可重试 | QuotaExceededError |
| 客户端/读取超时；已设置插件超时时execd -1/signal:killed | -32005 | CommandTimeoutError / ProviderTimeoutError |
| 400、422 detail、INVALID_METADATA_LABEL、不支持选项 | -32006，data.details含field/loc/msg | ProviderConfigError |
| Paused状态的execd拒绝/重置连接 | -32000，提示恢复沙箱 | SandboxError |
| 5xx、409、502 BACKEND_CONNECTION_FAILED | -32000；502/503/504且幂等调用时retryable:true | SandboxError |

---

## 3. 凭据与配置键（沿用provider设计文档命名的提案）

ID为 **opensandbox**，满足 `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` 且非保留字。规范环境名 `ABX_OPENSANDBOX_<KEY>`（设计§2原则3）。native别名是官方SDK/osb已有变量，便于复用环境；按manifest规则均不以ABX_、E2B_、ALICLOUD_开头。插件**不消费核心凭据**：`[core] inherit=[]`，绝不能接收ABX_SANDBOX_API_KEY或阿里云AK，见§4.6隔离。

| 键 | 类型 | 秘密 | 规范环境变量 | native环境变量 | 默认 | 含义 |
|---|---|---|---|---|---|---|
| base_url | url | 否 | ABX_OPENSANDBOX_BASE_URL | — | http://127.0.0.1:8080 | 生命周期根地址；接受末尾/v1并规范化，服务同时提供两类路由 |
| api_key | str | **是** | ABX_OPENSANDBOX_API_KEY | OPEN_SANDBOX_API_KEY | 无 | 发送OPEN-SANDBOX-API-KEY；**不标credential=true**，本地可无key运行并确认不安全模式，doctor须精确报401 |
| domain | host[:port] | 否 | ABX_OPENSANDBOX_DOMAIN | OPEN_SANDBOX_DOMAIN | 无 | protocol://domain替代基址；同时设置时base_url优先。可选，若面太宽可从v1删去 |
| protocol | http/https枚举 | 否 | ABX_OPENSANDBOX_PROTOCOL | OPEN_SANDBOX_PROTOCOL | http | domain与endpoint URL使用的scheme |
| use_server_proxy | bool | 否 | ABX_OPENSANDBOX_USE_SERVER_PROXY | OPEN_SANDBOX_USE_SERVER_PROXY | false | execd与端口入口经过endpoints?use_server_proxy=true；用于宿主端口不可路由场景 |
| default_image | str | 否 | ABX_OPENSANDBOX_DEFAULT_IMAGE | — | python:3.12-slim | 通用template=base时的镜像 |
| image_aliases | csv name=image | 否 | ABX_OPENSANDBOX_IMAGE_ALIASES | — | code=opensandbox/code-interpreter:v1.1.0 | 短模板名映射镜像URI |
| entrypoint | shell-split字符串 | 否 | ABX_OPENSANDBOX_ENTRYPOINT | — | tail -f /dev/null | 普通镜像入口，API要求必填 |
| ready_timeout | ≥1整数秒 | 否 | ABX_OPENSANDBOX_READY_TIMEOUT | — | 60 | 创建后等待Running与execd/ping |
| registry_username / registry_password | str / str | 否 / **是** | ABX_OPENSANDBOX_REGISTRY_USERNAME / ABX_OPENSANDBOX_REGISTRY_PASSWORD | — | 无 | 私有镜像image.auth，不写日志，宿主脱敏错误 |

http_timeout、max_retries等公共调优键保持生效。不写 `[auth] any_of`，原因见api_key。每次创建的entrypoint、network_policy（NetworkPolicy JSON对象）、platform（linux/arm64）、secure_access、image_auth通过--opt/provider_options传入而不持久化。

仅含OpenSandbox部分的历史manifest草图：

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
             "process.manage", "files.rw", "ports.url"]   # §6缺口解决后再加pty/code.interpret
[security]
network = ["*"]                 # 服务地址由用户配置
filesystem = ["data_dir"]
env_passthrough = []
spawns_processes = false
[core]
inherit = []
```

---

## 4. 不支持的事项与限制

1. Docker忽略磁盘规格，因此拒绝disk。
2. 无文件监听、签名传输URL、每进程stdin和真实进程表；列表只能shell模拟，镜像须有ps。
3. TTL最小60秒，而Agent Sandbox允许1秒。
4. 元数据必须符合Kubernetes标签语法，值最多63字符。
5. execd输出帧和argv取决于镜像版本（§1.1）；abx须说明字节一致输出的最低版本，历史建议latest或release-1.1.1后的首个版本。
6. 代码上下文要求解释器镜像；探测应避开会挂起的端点。
7. 前台命令在连接断开后被杀，因此进程需要超过CLI生命周期时必须background:true，需detached提示（§6）。

---

## 5. 测试计划

### 5.1 能否本地真实运行？——历史Docker运行时实测可以，且无需秘密

历史环境：Ubuntu24.04、内核6.12、4vCPU、16GB、overlayfs根文件系统；普通用户具备免密sudo，能访问PyPI与Docker Hub。**以下表格和命令记录的是当时环境，不是对当前环境权限的要求，也不是本次执行记录。**

| 问题 | 历史结果 |
|---|---|
| 初始docker --version / docker ps | docker不存在，无/var/run/docker.sock，也无podman |
| 能否安装Docker | 当时可执行 `sudo apt-get install -y docker.io iptables`，版本29.1.3 |
| systemd | PID1为tini，systemctl显示offline，因此手动nohup启动dockerd |
| 默认overlay根目录能否跑容器 | 不能，overlay-on-overlay导致failed to mount overlay invalid argument；当时通过20GB稀疏ext4镜像loop挂载/mnt/dockerdata，配置data-root、overlay2并关闭containerd-snapshotter解决 |
| OpenSandbox权限 | 服务用户访问Docker socket；历史设置socket模式666，容器使用默认drop_capabilities；bridge、端口发布、docker pause、egress DNS均实测可用。此处只保留历史事实，不作为当前权限调整建议 |
| 无Docker的dev/local服务运行时 | 没有；factory仅docker/kubernetes，DockerSandboxService启动即连daemon。未尝试k8s，因为无集群，需要kind/k3s、CRD及operator |
| Python/uv安装服务 | uv venv --python3.12加安装opensandbox-server==1.1.1可行；FastAPI0.143；init-config --example docker生成配置；普通用户运行 |
| 拉取镜像 | execd:v1.1.0/latest（35MB二进制）、python:3.12-slim、code-interpreter:v1.1.0、egress:v1.1.7均成功 |
| 无Docker运行真实execd | 从镜像docker cp取出/execd后，`./execd --port 44790 [-access-token T]` 可作为非特权进程提供完整命令、文件、SSE、proxy数据面 **[实测]**；无Jupyter则无代码上下文。latest/v1.1.0二进制提取到$WORKDIR/bin/ |

历史成功命令如下。译文将原文非秘密的一次性本地key替换为 `REPLACE_ME` 占位；这不改变鉴权配置和历史验证含义。`$WORKDIR`即脚本的OSB_WORKDIR，默认 `~/.cache/agent-sandbox/opensandbox-local`；`$ORIG_REPO`为研究时Agent Sandbox源码检出目录。均由 `e2e/opensandbox/local-up.sh` 包装，可重复执行；热启动约5秒、冷拉镜像约70秒。

```bash
# 历史Docker环境准备记录；本次翻译未执行
sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io iptables
sudo truncate -s 20G /var/lib/docker-loop.img && sudo mkfs.ext4 -q -F /var/lib/docker-loop.img
sudo mkdir -p /mnt/dockerdata /etc/docker && sudo mount -o loop /var/lib/docker-loop.img /mnt/dockerdata
echo '{"data-root":"/mnt/dockerdata","storage-driver":"overlay2","features":{"containerd-snapshotter":false}}' | sudo tee /etc/docker/daemon.json
(sudo nohup dockerd >"$WORKDIR/dockerd.log" 2>&1 &); sleep 8; sudo chmod 666 /var/run/docker.sock
docker run --rm alpine echo ok
# OpenSandbox服务：PyPI安装、普通用户运行
pip install --user uv && export PATH=$HOME/.local/bin:$PATH
uv venv $WORKDIR/venv --python 3.12
uv pip install --python $WORKDIR/venv/bin/python opensandbox-server==1.1.1
docker pull opensandbox/execd:latest python:3.12-slim opensandbox/egress:v1.1.7
# run_code另需opensandbox/code-interpreter:v1.1.0
cat >$WORKDIR/server.toml <<'CONFIG'
[server]
host = "127.0.0.1"
port = 8080
api_key = "REPLACE_ME"          # 一次性本地示例值在译文中统一占位
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
CONFIG
(nohup $WORKDIR/venv/bin/opensandbox-server --config $WORKDIR/server.toml >$WORKDIR/server.log 2>&1 &)
curl -s localhost:8080/health   # {"status":"healthy"}
curl -s localhost:8080/version  # {"version":"1.1.1"}
```

随后设置 `OPENSANDBOX_BASE_URL=http://127.0.0.1:8080/v1`、`OPENSANDBOX_API_KEY=REPLACE_ME`，运行仅标准库的 `python3 e2e/opensandbox/live_smoke.py`：历史35项全通过，约5秒。它也是§2映射的可执行规范：鉴权、create/get/list/endpoint、SSE执行/退出码/超时、后台日志游标/中断、mkdir/upload/stat/list/search/mv/rm/rmdir、renew、pause/resume、kill与第二次kill的404。另做过服务代理入口、egress策略（默认deny+allow pypi.org，阻止example.com但放行pypi.org，以及PATCH合并）、快照202 Creating、官方Python SDK端到端、execd访问令牌行为验证。

local-up脚本参数为up/down/status/env；配置变量OSB_SERVER_VERSION、OSB_EXECD_IMAGE、OSB_PORT、OSB_API_KEY、OSB_WORKDIR、OSB_WITH_EGRESS、OSB_WITH_CODE_INTERPRETER。历史down会停止服务并移除全部sandbox-*容器，不能误解为仅清理本次创建的资源。服务harness位于本仓库 `e2e/opensandbox/`；当前插件源码位于 [awesome-providers/opensandbox](https://github.com/alibaba-agent-sandbox/awesome-providers/tree/main/opensandbox)。

### 5.2 当时设计的插件测试金字塔

| 层级 | 内容 | 前提 | 执行位置 |
|---|---|---|---|
| **T0 单元** | 状态/错误映射、标签校验、timeout/memory/mode换算、裸JSON和data:SSE解析（分块/CRLF/不完整/大事件）、换行启发式、multipart、endpoint URL、metadata编码、Date头TTL运算 | 无 | 每PR离线 |
| **T1 mock契约** | 整个插件经真实stdin/stdout JSON-RPC EPP调用mock_opensandbox.py（§5.4） | Python标准库 | 每PR离线 |
| **T2 EPP一致性** | agent_sandbox.providers.testing的ProviderContractTests（设计§10.8）：已声明可用、未声明-32003、幂等kill、未知沙箱-32002 | T1 | 每PR离线 |
| **T3 真实execd** | mock生命周期+每沙箱临时目录里的真实execd进程；无Docker验证命令/文件/SSE | 固定镜像提取的execd或OPENSANDBOX_EXECD_BIN | CI有二进制缓存时运行，否则skip |
| **T4 live** | local-up启动真实opensandbox-server+Docker；T1用例通过OPENSANDBOX_LIVE=1复用；加pause/resume、TTL到期、egress、OSB_WITH_CODE_INTERPRETER=1及v1.1.0/latest矩阵 | Docker、约1.5GB镜像 | pytest -m live显式启用；夜间/标签CI，ubuntu-latest有Docker；不需秘密 |

历史CI提案要求T0–T2离线必跑，T3可选但建议，T4发布前及每夜对execd:latest通过，以发现§1.1所示上游漂移。**这是研究提案，不替代当前目录的provider测试层级规则。**

### 5.3 免Docker的真实数据面（T3）设计

为每个假沙箱启动 `execd --port <p> [-access-token <t>]`，cwd/HOME/TMPDIR均在该沙箱临时目录内。命令以测试用户运行，因此测试绝对路径要改写到沙箱根或避免使用。mock生命周期返回endpoint=127.0.0.1:<p>；kill终止进程组；计时器实施TTL；pause/resume分别SIGSTOP/SIGCONT进程组，作为足够接近docker pause的类比。这可验证§2.2/2.3，但不覆盖解释器、Docker中PTY差异及egress。

### 5.4 无execd二进制或Docker时的保真mock（T1）设计

单个标准库http.server/ThreadingHTTPServer模块，建议 `tests/mock_opensandbox.py` 约600行；生命周期与每沙箱execd分别占端口，状态留内存。

* **保真来源是录制fixture，而不是猜测。** 从live smoke录制并清理ID/时间后重放：202且Running、422 detail、404 DOCKER::SANDBOX_NOT_FOUND、二次DELETE404、裸JSON SSE的init/ping、CommandExecError/evalue退出信号、-1/signal:killed、以路径为键且mode用八进制数字的files/info、删目录走/files得500、mv覆盖500、metadata须文件部件否则400、后台合并日志与游标、501 FSB::API_NOT_SUPPORTED、无scheme的endpoint及headers、GET /code/contexts为200 []、运行时未配置500，以及POST /code/context挂起（可配置停顿以验证超时）。
* **行为用小型真实模型实现。** 沙箱状态/TTL表，到期移除；临时目录为虚拟文件根；subprocess执行shell/argv，按精确SSE帧输出，可切换新版/v1.1.0移除换行模式和argv接受标志；后台命令注册表、renew、pause/resume、标签校验、pageSize≤200、API key与execd token校验；网关模式返回必须逐请求重放的headers，遗漏即拒绝。
* **离线规范一致性门禁。** 固定a6a0135…，vendor两份规范并保留Apache-2.0头；只在开发依赖使用openapi-core或jsonschema，对解析$ref后的schema校验插件请求与mock响应。tests/SPEC_PIN记录提交及hash，规范hash不同即失败，让升级显式。已知规范/实测差异用有注释的明确例外：422 detail、execd401 error、mv自动建父目录、规范未含pty、v1.1.0不支持argv。
* **差分规则。** 每个T1用例也在T4运行；mock行为修改须同时重跑live并通过make record-fixtures脚本更新tests/fixtures/*.json。

### 5.5 优先契约测试

1. exec退出0/3/127、超时、启动失败矩阵。
2. 两种帧模式对 `printf 'a\r\nb\n'` 产生相同stdout。
3. 上传下载字节一致：包含 `\x00\xff`、空文件、3MB。
4. 文件/目录/缺失删除、移到已存在目标、搜索深度。
5. 即使客户端时钟偏移，set_timeout后的expiresAt也在服务时间±2秒内。
6. kill幂等。
7. 元数据标签错误指出键名。
8. 能力探测不能无超时调用挂起端点。
9. 每次execd调用（含SSE、上传）均重放Endpoint.headers。
10. 超过200项时的list分页。
11. exec.start的全部exec.output在唯一exec.exit之前。
12. 接受ErrorResponse、detail、error及非JSON的502 HTML等不同错误形状。

---

## 6. 此provider暴露的EPP/1草案缺口（供provider设计维护者）

1. **进程ID是字符串。** execd为32位hex，ProcessInfo.pid为int。EPP应把process_id声明为string|int，kill/signal均接受两者；本文按数字走OS kill、hex走execd命令ID。
2. **exec.start缺detached/background提示。** 前台断连被杀，超过CLI生命周期的后台进程须background:true加日志轮询。建议可选布尔detached；进程始终分离的provider可忽略。
3. **有code.interpret feature但无code.*方法。** 建议code.run接受sandbox_id/code/language/context_id?/envs?/timeout，流式code.output后返回results/error；增加code.context.create/list/remove/restart。解决前不声明code.interpret，run_code仍可用SDK shell回退。
4. **大文件。** files.read/write以base64放JSON，行上限8MiB，而OpenSandbox原生支持Range及3MB以上。可选read offset/length、write append分块；或SandboxRecord提供可选直接数据面描述符 `{base_url,headers}`，OpenSandbox Endpoint正合适；草案envd_url混合模型只适用于envd协议。
5. **每沙箱能力。** 当前能力来自模板，而镜像型provider是否有code取决于镜像。建议 `sandbox.capabilities{sandbox_id}→{tokens:[…]}`，无该方法时回退静态features。
6. 其他：EPP缺files.search/files.chmod（OpenSandbox原生，CLI用find模拟）；须定义sandbox.list的metadata相等且AND语义；手动清理实例要求SandboxRecord.expires_at可省略；429/502错误需data.retryable。

---

## 7. 可复用部分：包装官方SDK还是直接REST

| 标准 | Python opensandbox 1.1.1 | JS @alibaba-group/opensandbox 1.1.1 | 标准库直接REST |
|---|---|---|---|
| 许可 | Apache-2.0 | Apache-2.0 | 不适用 |
| 运行依赖 | pydantic≥2.4.2及**pydantic-core原生wheel**、python-dateutil、attrs、httpx、httpcore、httpx-sse、opentelemetry-api；总18包**15MB**，SDK自身393个.py/3.1MB | @opentelemetry/api、openapi-fetch、undici，共4包**8.1MB/897文件**；Node≥20、仅ESM | 0 |
| 是否符合安装不跑pip/npm、≤2000文件/50MiB、单文件≤10MiB、无symlink（设计§8） | **否**，按OS/架构/Python ABI区分的原生扩展无法可移植vendor | 需esbuild打包为约1–2MB单文件，构建步骤由插件仓库维护并保证可复现 | **是** |
| 与EPP匹配 | 异步池/遥测未使用；create-and-hold、自动health、endpoint缓存、metrics POST的Sandbox对象不适合每次调用的无状态RPC | 同左 | 恰好覆盖§2约20类调用 |
| 必需行为 | 生命周期/exec/files/code及裸JSON SSE | 同左 | 须实现SSE读取约40行、multipart约30行、PTY WS约120行、错误映射约60行 |
| 维护风险 | 跟随服务频繁发布（python/sandbox/v0.1.x到1.1.x），与pydantic/httpx版本耦合 | 同左 | 规范倾向新增兼容变更（specs/AGENTS.md）；固定提交+每夜live |
| 遥测 | 尽力POST /metrics/events | 同左 | 无，不主动启用 |

**历史决定：直接REST、仅标准库、单provider.py约700–900行。** 官方SDK用于可读参考（sse.py、command_adapter.py、filesystem_adapter.py、endpoint_cache.py）以及T4测试判据：SDK创建后插件操作，反向亦然；仅开发依赖，不随插件交付。Python标准库http.client/json/threading/base64/ssl与local-process参考插件一致，Python SDK环境均可用；若目标是无Python的CLI机器，可替换为Node provider.mjs、全局fetch、无依赖，EPP允许互换，也可用第二manifest交付两种实现。插件进程内部保留HTTP keep-alive，execd入口/代码探测仅内存缓存到本次CLI进程结束。

### 7.1 建议布局与顺序

```text
providers/opensandbox/
  abx-provider.toml           # §3
  provider.py                 # EPP循环、方法表、配置、错误映射，约250行
  _osb_http.py                # request、仅幂等重试、SSE、multipart、入口缓存、Date偏差
  tests/{unit,contract,live}/ # T0、T1/T2、T4
  tests/mock_opensandbox.py   # T1，及T3桥接
  tests/fixtures/ specs/      # 录制响应、固定规范与SPEC_PIN
  scripts/opensandbox-local-up.sh  scripts/opensandbox_live_smoke.py
```

顺序：(1) initialize/生命周期/ports.url对T4；(2) exec.run/start兼容两种帧；(3) files.*；(4) process.*、timeout/pause；(5) 从T4录制fixture建立T1 mock；(6) PTY WebSocket及EPP缺口3解决后的code.*；(7) 用 `abx provider install alibaba-agent-sandbox/awesome-providers//opensandbox` 或本地目录安装。**实际交付插件是该目录的Node树，不是上述Python草图。**

---

## 8. 附录：历史证据与产物

| 产物 | 位置 |
|---|---|
| 研究源码a6a0135…及release-1.1.1=531700c… | $WORKDIR/opensandbox-src |
| 服务venv、配置、日志、down/up脚本 | $WORKDIR，默认~/.cache/agent-sandbox/opensandbox-local；e2e/opensandbox/local-up.sh |
| 标准库live smoke，35项 | e2e/opensandbox/live_smoke.py |
| 官方SDK smoke | e2e/opensandbox/sdk_smoke.py |
| v1.1.0/latest真实execd二进制 | $WORKDIR/bin/execd、$WORKDIR/bin/execd-latest |
| 关键源码 | 生命周期specs/sandbox-lifecycle.yml；execd specs/execd-api.yaml；鉴权server/opensandbox_server/middleware/auth.py:37-120；路由server/opensandbox_server/api/{lifecycle,proxy,network_policy,templates}.py；Docker入口解析server/opensandbox_server/services/docker/networking.py:300-345；状态services/docker/docker_service.py:529-557；运行时services/factory.py；execd路由components/execd/pkg/web/router.go:45-149；上传components/execd/pkg/web/controller/filesystem_upload.go；命令取消components/execd/pkg/runtime/command.go:285-335；proxy components/execd/pkg/web/proxy.go；PTY components/execd/PTY.md；SDK配置sdks/sandbox/python/src/opensandbox/config/connection.py；SSE sdks/sandbox/python/src/opensandbox/adapters/sse.py；兼容指南docs/api/implementation-compatibility.md；服务配置server/configuration.md |
| 映射使用的Agent Sandbox接口 | 历史$ORIG_REPO/src/agent_sandbox/{api,protocol,models}、cli/commands/sandbox*.py；覆盖create/list/info/kill/exec/connect/upload/download/run、files list/stat/mkdir/rm/mv/search、process list/start/info/signal、system ports/capabilities/metrics |

## 9. 2026-10-13实测评审后的状态

本节记录的是**Node exec插件**；当前适配器是页首链接指向的引擎内provider。不能把下列旧插件结果当作当前交付路径。

当时§2映射已实现为opensandbox插件，在真实opensandbox-server1.1.1+Docker上，经abx与 `Sandbox.create(provider="opensandbox")` 驱动。证据：[2026-10-13-opensandbox-provider-e2e](https://github.com/alibaba-agent-sandbox/agent-sandbox/blob/main/.agents/evidence/verify/2026-10-13-opensandbox-provider-e2e.md)。

| 范围 | 历史状态 |
|---|---|
| 生命周期：镜像URI创建、get/list/connect/kill、销毁后E2009 | 两个宿主均可用 |
| exec：缓冲/流式、退出码、stderr、env | 可用 |
| 文件：文本、300KB二进制、Unicode、list/stat、CLI上传下载、类型化E4001 | 可用；未声明files.watch和签名URL，返回E8004 |
| timeout/pause/resume | SDK可用；CLI无pause/resume命令 |
| 端口URL | network.resolve(9000)返回服务代理URL |
| 进程控制 | list可用；send_stdin为E8004 |
| 模板 | 创建时template由default_image/image_aliases映射镜像URI；无[template] profile，该表只用于模板创作；当时CLI template命令尚不感知provider |
| 网络策略 | 存在每次创建network_policy选项；该次运行未测egress sidecar |
| 凭据 | ABX_OPENSANDBOX_API_KEY、ABX_OPENSANDBOX_BASE_URL；native别名OPEN_SANDBOX_API_KEY、OPEN_SANDBOX_DOMAIN |
| 安装 | 本地克隆的固定git安装可用；当时公共目录仍为ebx-provider.toml，需abx更名补丁cli/e2e/providers/awesome-providers-abx-rename.patch |
