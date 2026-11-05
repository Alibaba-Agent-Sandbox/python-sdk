# 托管 Agents API

[English](../../en/guide/managed-agents-api.md)

应用只配置一个 Gateway 地址和业务 Bearer Token，即可让编码 Agent 在独立沙箱中运行。
Session 在首次输入时创建沙箱，后续轮次复用工作区。可选托管运行时支持内置极速版提供方与明确配置的
Codex、Qwen Code 模型。它采用部分 OpenAI 风格资源结构，不声明 OpenAI SDK 互操作或官方托管 harness 等价能力。

安装匹配版本的客户端、服务端与托管部署依赖：

```bash
python -m pip install --pre 'agent-sandbox-client[managed-agents]'
```

[agents-api 模板](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/tree/main/agents-api)
提供应用配置；使用匹配的 [abx CLI](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox) 部署。
应用连接返回的 Gateway endpoint，无需配置每个沙箱的 endpoint。

## 提交输入与读取结果

将 `AGENTS_API_URL` 设为 Gateway 地址，`AGENTS_API_KEY` 设为部署方签发的业务令牌。
它与 Sandbox API Key、云凭据、模型 Key、沙箱应用令牌分别使用。模板部署会自动准备私有沙箱应用令牌。

```python
import os
import httpx

with httpx.Client(
    base_url=os.environ["AGENTS_API_URL"],
    headers={"Authorization": "Bearer " + os.environ["AGENTS_API_KEY"]},
) as api:
    response = api.post(
        "/v1/agents/sessions",
        json={
            "agent": {"model": "your-deployment-model"},
            "input": "在 outputs/report.txt 中写一份简短总结。",
        },
        headers={"Idempotency-Key": "report-session-1"},
    )
    response.raise_for_status()
    session_id = response.json()["id"]
    print(session_id)
    print(response.headers["X-Agent-Sandbox-Submission-Id"])
```

创建返回 `201`。接收输入后生成持久 Submission，真正开始执行时才出现公开 Turn。
轮询 Session、`/turns` 和 `/artifacts` 集合，通过
`/v1/agents/sessions/{id}/artifacts/{artifact_id}/content` 下载已发布产物。
后续向 `POST /v1/agents/sessions/{id}/events` 提交 `{"input":"继续"}`，返回 `202`、空正文、
Submission ID 响应头和其 `Location`。相同幂等键与正文返回首次接收结果；新输入使用新键。

执行中直接输入返回 `409 active_turn_not_steerable`。显式排队使用
`POST /v1/agent-sandbox/sessions/{id}/submissions`，必须提供 `Idempotency-Key`，返回 `202` 与
Submission 对象。排队会创建下一轮，不会引导当前执行。

## 文件与事件

使用 multipart `POST /v1/files` 上传文件，字段为 `purpose=user_data` 与 `file`。
提交输入时附带 `x_agent_sandbox.input_files: [{"file_id":"file_...",
"path":"/workspace/input/data.csv"}]`。路径必须规范化且处于部署工作区的 `input` 目录内，
已有文件不能覆盖。提交接收时固定输入快照，删除公开 File 不撤销已经接收的附件。
只发布 `outputs/` 中普通文件的不可变产物快照；符号链接、不可读或读取期间变化的文件会被拒绝，
并报告部分发布结果。

通过 `GET /v1/agents/sessions/{id}/events` 订阅事件，用 `Last-Event-ID` 或 `after` 恢复。
`after=0` 从头回放；省略时只接收新事件。流会定期结束，客户端用最后收到的事件 ID 重连。
公开事件在结果保留期内持久保存。删除会阻止各 Gateway 实例开始发送新帧，已经进入网络的帧仍可能到达；慢读连接会断开，过大帧明确报告缺口，完整内容通过持久 items 接口读取。原生事件缺口会明确报告，不公开原始推理和提供方秘密。

## 取消、关闭与删除

通过 Submission 的 `/cancel` 取消排队输入。执行中按明确的 Turn 或 Submission ID 取消，
持续查询返回的 Operation，直到 `stop_confirmed` 为 true。接受取消请求并不证明执行已经停止。
合作进程观测能够确认停止时允许复用 Session；无法确认时销毁整个沙箱并关闭 Session。
提供方结果仍不确定时保留 `requires_reconcile`，并继续占用容量。

`POST /v1/agent-sandbox/sessions/{id}/close` 返回 `202` 与 Operation，停止该 Session 接收输入、
释放计算资源，结果保留至截止时间。`DELETE /v1/agents/sessions/{id}` 返回 `200` 后立即撤销公开访问；
执行中返回 `409`，应先取消或关闭。物理清理可能异步继续。关闭与删除含义不同。
使用完毕应关闭 Session，并检查 Operation 结果后再将资源清理视为完成。

## 支持范围与限制

| 资源 | 操作 |
| --- | --- |
| 平台 | 健康检查、能力、模型列表及详情、运行时列表 |
| Agent | 保存配置的创建、列表、读取、更新与删除 |
| Session | 创建、列表、读取、metadata 更新、删除、输入及事件、items |
| Turn | 列表、详情、所属 items、精确取消 |
| Artifact | 列表、元数据、下载、删除已发布快照 |
| File | multipart 上传、列表、元数据、下载与删除 |
| Environment | 只读列表与详情 |
| 托管生命周期 | 关闭、Operation、Submission 排队、列表、详情与取消 |

`GET /v1/agent-sandbox/capabilities` 返回支持路由与部署预算。
列表接受 `limit`、`order`、`after`，下一页使用 `last_id` 或限定范围的 `next_cursor`。
Session 仅支持更新 metadata。Function tools、任意 MCP 配置、subagents、steering、图像/音频输入、
动态模型和 settings 更新会明确拒绝；所选 CLI 自带的 shell、文件工具仍在沙箱内可用。
工具墙钟期限从观察到原生工具开始事件起计算。运行时 epoch 改变或提交收据不确定时冻结执行，
不会自动重放输入。

FC 部署要求 PostgreSQL；SQLite 仅用于明确的本地模式。存储、队列、执行时间、事件与订阅者均有有限预算，
额度不足返回 `429`。过期结果返回 `410`，已删除资源返回 `404`。
清理会保留解决不确定资源所需的私有归属记录。

## 部署方配置

入口为 `python -m agent_sandbox.managed_agents gateway|worker|dispatcher`。
沙箱镜像运行 `python -m agent_sandbox.server.managed --port 9000`，并需安装 Codex 或 Qwen Code。

以下每种配置只能选择一个 `_FILE` 或 `_JSON` 来源：

| 环境变量前缀 | 配置正文 |
| --- | --- |
| `ABX_MANAGED_CONFIG` | 编译后的 revision、application ID、模板、模型/adapter 白名单、`modelEnvAllowlist`、Session/存储/执行预算与保留 Worker 映射 |
| `ABX_MANAGED_AUTH` | `tokens: [{sha256,owner,scopes,expiresAt?}]`，scope 为 `agents:read`、`agents:write` |
| `ABX_MANAGED_MODEL_CONFIG` | 仅 Worker 使用 `{apiKey,baseUrl,model,adapter}` |
| `ABX_MANAGED_PROVIDER_CONFIG` | Worker/Dispatcher 使用 `{provider:"alicloud-express",apiKey,baseUrl,domain,region}` |

`ABX_MANAGED_DATABASE_URL` 指向 PostgreSQL。`ABX_MANAGED_INTERNAL_TOKEN` 认证私有角色调用，
保留旧 revision 排空期间应保持稳定。`ABX_MANAGED_FC_ENDPOINT` 指定派发所用 FC 服务主机。
`modelEnvAllowlist` 必须明确允许 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。
凭据仅交给需要它的角色，不写入镜像或公开资源。文件来源的业务认证每次重读以支持撤权，并执行可选到期限制。

TLS 始终校验证书，默认采用系统信任库且不继承 HTTP 代理设置。
私有 CA 使用 `ABX_MANAGED_TLS_CA_FILE` 指向可读 PEM CA bundle；CA 配置错误会失败，不会关闭证书校验。
