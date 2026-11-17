# 托管 Agent Harness

托管 Gateway 对各 Harness 使用相同的 Session、输入、Turn、Item、事件、文件和产物协议。
部署应用时选择 `agents-api-codex` 等对应模板。Session 生命周期内原生 Harness 保持固定；
模型凭据通过私有 Worker 注入 Sandbox，与 Gateway 的客户端认证分开配置。

本文新增适配对应客户端／服务端 **0.4.0a8** 源码。构建镜像前先确认版本是否已经发布；
尚未发布的候选版本不能当作可安装的 PyPI 版本。只更新宿主客户端不会更新已有镜像内的服务端。

| 适配器 | 原生命令 | 凭据 | 模型端点 |
| --- | --- | --- | --- |
| `codex` | `codex exec --json` | `OPENAI_API_KEY` | 显式配置兼容 Responses 的 `OPENAI_BASE_URL` |
| `qwen-code` | `qwen --output-format stream-json` | `OPENAI_API_KEY` | 显式配置兼容 Chat Completions 的 `OPENAI_BASE_URL` |
| `claude-code` | `claude -p --output-format stream-json` | `ANTHROPIC_API_KEY` | 显式配置兼容 Messages 的 `ANTHROPIC_BASE_URL` |
| `qoder` | `qoder --print --output-format stream-json` | `QODER_PERSONAL_ACCESS_TOKEN` | Qoder 原生服务；此适配器不配置自定义模型端点 |
| `opencode` | `opencode run --format json` | `OPENAI_API_KEY` | 显式配置兼容 Chat Completions 的 `OPENAI_BASE_URL`，生成原生 `abx` Provider 配置 |
| `deepseek-harness` | `dsh --profile headless --json` | `DEEPSEEK_API_KEY` | 显式配置兼容 Messages 的 `DEEPSEEK_BASE_URL`；官方根地址为 `https://api.deepseek.com/anthropic` |

按对应模板的说明修改私有凭据来源和配置，不要将凭据写入镜像或提交到 `template.yaml`。
应用的模型 ID 绑定模板选定的 Harness。Qoder 的模型须属于该 PAT 账号可用的模型；
OpenAI 模型 Key 不能代替 Qoder PAT。PAT 从 [Qoder 账号集成页](https://qoder.com/account/integrations)
生成。Qoder BYOK 取决于账号套餐和模型目录，按官方 `/model` 向导配置；本适配器不编造手动 BYOK 配置。

原生模型名称传给对应 Harness。Codex／Qwen／OpenCode 使用 `OPENAI_MODEL`，
Claude 使用 `ANTHROPIC_MODEL`，DeepSeek Harness 使用 `DEEPSEEK_MODEL`。
Worker 仅注入所选适配器需要的变量，拒绝不匹配的模型／Harness 绑定和无关凭据名称。

每个 Turn 实际运行原生 CLI，后续 Turn 在同一个 Session Sandbox 中通过精确原生会话 ID 续接。
Close 释放计算并保留 Gateway 已存结果；新建 Sandbox 不能承诺恢复已经删除的计算资源内的
文件或原生历史。公开生命周期参见[托管 API 指南](managed-agents-api.md)。

Codex、Claude 和 Qwen 可以提供原生增量事件。OpenCode JSON 文本和 DeepSeek Harness
无头文本分别对应完整消息或已提交步骤，不等于逐 Token 输出。收到原生终态消息也不代表
所有进程均已退出；桥接同时检查进程退出与所属子进程清理，无法确认时保留不确定状态。

OpenCode 1.19.5 只在工具完成后报告工具记录，不能据此从工具真实开始计时执行单工具超时；
整体任务期限和所属进程清理仍生效。通用本地运行时中，此适配器支持 `read_only` 或
`full_access`，拒绝无法可靠映射的 `workspace_write`；托管 Session 在 Sandbox 内使用 `full_access`。

新增适配仍为实验能力。Qoder、OpenCode、DeepSeek Harness 暂未通过此适配器 API
映射外部 MCP 配置。Qoder 1.1.90 的实际 CLI 没有部分新文档所述的 `--max-turns`，
因此会拒绝配置该次数限制。Steering、函数、子 Agent 和工具能力取决于 Gateway 能力声明
与原生 Harness。使用某个 Provider、模型端点或账号类型前，查看对应模板的实际验证范围。

DeepSeek 适配器调用官方 `@deepseek-ai/dsh`。旧 `deepseek-harness` 命名命令模板是项目自研
工具循环，其模型实跑记录不能替代官方原生适配的验证。
