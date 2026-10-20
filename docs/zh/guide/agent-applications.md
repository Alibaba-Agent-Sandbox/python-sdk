# Agent 应用：外部运行与 sandbox 内运行

可选上层模块 `agent_sandbox.applications` 提供独立的应用控制面。它与现有
sandbox 内 Agents API 分开运行。默认 SDK 导入、`Sandbox.create()` 和
`ProviderSandbox.create()` 不会部署应用或执行模板 hooks。应用配置保留在
单一 `template.yaml` 的可选 `application:` 区块，不新增应用清单文件。

模板规范与宿主部署流程分别属于
[模板仓库](https://github.com/alibaba-agent-sandbox/awesome-templates) 和
[abx CLI](https://github.com/alibaba-agent-sandbox/agent-sandbox)。本指南介绍 Python
运行时；当前源码能力仍需真实云验收，不能认为已发布的 wheel 已包含它。

## 两种运行位置

- **外部运行**：可信 Python Agent 循环运行在 worker，命令、文件工具访问每次运行
  独占的远程 sandbox。模型生成代码不会在网关或 worker 进程执行。
- **Sandbox 内运行**：现有核心 Agents API 在 sandbox 内驱动本地 CLI。直接客户端
  继续使用该 API。`InSandboxAgentExecutor` 另支持托管网关，仅调用属于该运行的
  session、输入、turn、items，并检查实际 discovery；清理时销毁整个独占 sandbox。
  不代理全部本地端点，不声称完整转发本地内存事件；P0 只发布最终输出。

网关部署到 FC 不等于 Agent 循环迁出 sandbox。`runtime.driver` 表示
`python-remote-tools` 或 `sandbox-local-api` 集成类型；本地 CLI 由
`ABX_APP_LOCAL_AGENT` 另选，默认 `codex`。托管适配器仅接受
`server-core-agents`，不兼容覆盖核心路由的旧模板协议。

## 安装与入口

在当前源码仓库安装：

```bash
pip install -e ./server-sdk -e './client-sdk[applications-fc]'
python -m agent_sandbox.applications gateway
python -m agent_sandbox.applications worker
python -m agent_sandbox.applications dispatcher
```

三个角色分别运行在独立容器/函数，监听 `ABX_APP_BIND` / `ABX_APP_PORT`，默认
`0.0.0.0:9000`。网关提供六个业务操作；worker、dispatcher 只提供私有
`POST /invoke`。Worker 完成执行和清理后才返回，不依赖返回 `202` 后继续后台工作。
FC Custom Container 将 InvokeFunction 请求转发到这个固定路径。
[FC 官方协议](https://www.alibabacloud.com/help/en/functioncompute/code-development-in-custom-container-runtimes)。

`GET /healthz`（兼容 `/health`）返回 `status: ok`、revision、
`protocol: agent-sandbox-runs/v1` 和真实操作列表。Factory 初始化状态存储后才就绪；
健康检查不能替代 IAM、模型和 sandbox 实际执行验收。`--once` 支持 worker/dispatcher
从 stdin 读取一次 JSON 后退出，仅用于本地验证。

## 部署配置与凭据

可用 `ABX_APP_FACTORY=module:function` 加载打包好的可信工厂，返回
`ApplicationRuntime`。默认值是 `agent_sandbox.applications.config:default_factory`。
业务请求无法指定模块、路径或 Factory。

| 环境变量 | 含义 |
| --- | --- |
| `ABX_APP_SPEC_JSON` | 从单一模板编译的非敏感 runtime/sandbox/state/bindings/limits |
| `ABX_APP_REVISION` | 不可变应用版本 |
| `ABX_APP_SANDBOX_TEMPLATE` | Provider 实际准备好的模板/资源引用 |
| `ABX_APP_SANDBOX_PROVIDER` | 对应 Provider 标识 |
| `ABX_APP_DATABASE_URL` | 部署环境解析绑定后注入的 PostgreSQL 连接秘密 |
| `ABX_APP_AUTH_FILE` | 挂载的 token 摘要、owner、revision、scope 白名单 |
| `ABX_APP_INTERNAL_TOKEN` | 独立私有调用凭据，至少 32 字符 |
| `ABX_APP_FC_ENDPOINT` | 账户 FC API 主机名，不带协议 |
| `ABX_APP_WORKER_FUNCTION` | 已部署 Task 函数名 |
| `ABX_APP_MODEL_ENDPOINT` | 外部模式的 HTTPS Chat Completions 兼容模型地址 |
| `ABX_APP_MODEL` / `ABX_APP_MODEL_API_KEY` | 外部模型标识及独立注入的访问凭据 |
| `ABX_APP_LOCAL_AGENT` | 内部模式的本地 CLI 类型 |

YAML 中 binding 是引用名，不是秘密值；由部署环境解析为变量或挂载文件。
Sandbox API 使用 SDK 现有鉴权配置。B 模式中的 CLI/模型凭据须由模板或可信自定义
sandbox 工厂单独注入。控制面数据库、云和业务鉴权凭据不得注入生成代码的工作区。
同一 sandbox UID 内的 CLI 与代码之间没有凭据隔离保证。

FC sender 使用官方 `alibabacloud-fc20230330` SDK、默认凭据链/函数角色、异步调用，
以 run ID 作为原生 task ID。调用体使用区分角色的 HMAC JSON 信封，不传递原始私有凭据，
不依赖 FC 转发自定义 API 头。直接私有 HTTP 调用也可使用
`X-ABX-Internal-Token`。部署须配置私有入口、最小权限角色和异步 Task。Dispatcher 须由外部周期
触发，配置 `sign_invocation({"limit": 20}, token, role="dispatcher")` 产生的签名信封。
FC 定时器将信封 JSON 放在 payload 字符串中，运行时拆开 triggerTime/triggerName/payload
元数据后校验内部签名；重放受 run/outbox claim 保护，轮换密钥须协调队列中调用。
[定时事件官方格式](https://www.alibabacloud.com/help/en/functioncompute/time-triggers)。它未运行时网关仍可持久接受任务。每批最多 100 条，调度时间窗 20 秒加一次
受限 SDK 调用，函数超时至少 60 秒；worker 超时须覆盖运行预算及清理余量。

鉴权文件只保存足够随机 bearer token 的 SHA256 摘要，例如以下占位结构：

```json
{"tokens":[{"sha256":"REPLACE_ME_SHA256","owner":"team-a","revisions":["revision-a"],"scopes":["runs:read","runs:write"]}]}
```

每次请求及 SSE 轮询重新读取文件以支持撤销；也可通过可信 Factory 接入带到期验证
的 OIDC/JWT。

## 六个 API 与客户端

| 操作 | 路径 |
| --- | --- |
| 接受输入 | `POST /v1/agent-runs` |
| 读取状态 | `GET /v1/agent-runs/{id}` |
| 请求取消 | `POST /v1/agent-runs/{id}/cancel` |
| 持久事件 | `GET /v1/agent-runs/{id}/events` |
| 最终结果 | `GET /v1/agent-runs/{id}/result` |
| 下载产物 | `GET /v1/agent-runs/{id}/artifacts/{artifact_id}/content` |

```python
from agent_sandbox.applications import ApplicationClient

async def submit(base_url: str, business_token: str) -> str:
    async with ApplicationClient(base_url, business_token) as client:
        run = await client.create("revision-a", "分析文件", idempotency_key="request-1")
        async for event in client.events(run.id):
            print(event.seq, event.type)
        return run.id
```

创建必须提供 1–128 个可打印 ASCII 的 `Idempotency-Key`，请求只接受
`{"applicationRevision":"revision-a","input":{"text":"..."}}`。Owner 来自鉴权，
业务请求不能修改。同 owner/revision/key/body 重放返回原任务，body 改变返回 409。
不存在与他人的任务统一 404；未鉴权 401、scope 不足 403、容量不足 429、状态服务
不可用 503；未结束读取结果返回 409。修改操作不自动重试。

SSE 每次连接最多 20 秒，使用 `Last-Event-ID` 或客户端 `after` 显式重连；断开不会
取消任务。事件提交后才发送，不保证恰好一次投递。P0 保留预算内全部事件，尚未实现
TTL 自动删除、过期游标 410 或对象存储产物转存。

## 持久性、取消与预算

PostgreSQL 在同一事务提交 run、首个事件和 outbox。不可变快照包含准备好的模板、
运行位置、模型标识、绑定引用及执行/准入预算；同 revision 改配置会拒绝。应用行锁
在多个进程间限制准入与并发。原生 task 可重复投递；条件 claim 只产生一个 attempt。
发送失败保留 outbox 并受限退避到运行截止时间；未 claim 的任务可安全到期。

取消先持久记录意图。Worker 在模型、工具和资源调用前检查，取消协作式协程，并确认
远程 sandbox 停止/清理后才记录终态。先提交的取消胜过随后成功；清理失败、创建结果
不明或 lease 过期进入 `requires_reconcile`，不在同一工作区启动新 worker。
数据库 lease 无法阻止远程 shell。须由运维检查/终止带运行标签的独占 sandbox，并证明旧原生 worker 连同待返回的
创建请求已停止。可信 `Store.resolve_uncertain(run_id, expected_attempt, verify_quiesced)`
在数据库锁外执行运维验证，提交前再次比较 attempt/resource；创建不明时须按运行
标签搜索资源，不能以缺失 receipt 作为证明。验证失败保持隔离并占用容量；此操作
不通过业务 HTTP 暴露。P0 尚不提供自动资源 reconciliation、恢复或 checkpoint。Sandbox TTL 限制
生命周期，不代表 worker 消失时副作用立即停止。

外部循环默认最多 30 个模型步骤，工具仅为部署授权的远程 shell/read/write/artifact。
工具使用 `maxToolSeconds`，其余运行、事件、输出、并发、队列和速率预算均进入快照。
最终文本限制为 `maxOutputBytes` 与 65,536 UTF-8 字节的较小值。P0 小型产物复制进
PostgreSQL，默认最多 100 个、总计 10 MiB，以 octet-stream 下载；业务 API 不接受
任意路径或 URL。这不是大文件对象存储接口。

## 本地验证与剩余门禁

SQLite 只接受显式 `Store(url, local=True)` / `ABX_APP_LOCAL=1`，检测到 FC 函数/实例
环境标识时拒绝。FC 临时文件系统不能作为持久控制数据库。

```bash
cd client-sdk
pytest tests/test_applications -m 'not integration'
# 以下只为本地真实 PostgreSQL 验证工具，不是产品依赖：
pip install pgserver==0.1.4 'psycopg[binary]>=3.2,<4'
pytest tests/test_applications/test_postgres.py
```

子进程集成使用真实 gateway/worker/dispatcher HTTP 进程、真实 SandboxServer 文件 API、
确定性模型夹具，覆盖重启、幂等、产物和 SSE。它不能证明云网络/IAM、FC 镜像兼容、
真实 LLM 或操作系统 sandbox 隔离。真实 FC、模型、Provider 验收及远程 CI/Review
仍是发布门禁。

自定义 executor 回调须响应 asyncio 取消，阻塞代码需进程隔离。清理时间窗后仍运行
的任务保持 requires_reconcile。事件预算至少五条，为取消、不确定与确认恢复预留终态。
