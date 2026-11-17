# Managed Agent harnesses

The managed Gateway uses the same Session, input, turn, item, event, file and artifact
protocol for every supported harness. Choose a template such as `agents-api-codex`
when deploying the application. A Session's native harness stays fixed for its lifetime;
model credentials are supplied to its private Worker and Sandbox, separately from the
Gateway's client authentication.

The harness additions described here are source changes for client/server **0.4.0a8**.
Check package availability before building images. An unpublished candidate does not
provide a working PyPI installation command. Installed older servers do not gain new
adapters when only a host client is updated.

| Adapter | Native command | Credentials | Model endpoint |
| --- | --- | --- | --- |
| `codex` | `codex exec --json` | `OPENAI_API_KEY` | Explicit Responses-compatible `OPENAI_BASE_URL` |
| `qwen-code` | `qwen --output-format stream-json` | `OPENAI_API_KEY` | Explicit Chat Completions-compatible `OPENAI_BASE_URL` |
| `claude-code` | `claude -p --output-format stream-json` | `ANTHROPIC_API_KEY` | Explicit Messages-compatible `ANTHROPIC_BASE_URL` |
| `qoder` | `qoder --print --output-format stream-json` | `QODER_PERSONAL_ACCESS_TOKEN` | Native Qoder service; no custom endpoint in this adapter |
| `opencode` | `opencode run --format json` | `OPENAI_API_KEY` | Explicit Chat Completions-compatible `OPENAI_BASE_URL`, configured as native provider `abx` |
| `deepseek-harness` | `dsh --profile headless --json` | `DEEPSEEK_API_KEY` | Explicit Messages-compatible `DEEPSEEK_BASE_URL`; official root is `https://api.deepseek.com/anthropic` |

Use the corresponding template's private credential source and configuration guide.
Do not put credentials in the image or commit them in `template.yaml`. The application
model ID selects the template's fixed harness. For Qoder, use a model available to the
PAT's account, such as the account's native model choice; an OpenAI model key cannot
replace a Qoder PAT. Obtain a PAT from [Qoder integrations](https://qoder.com/account/integrations).
Qoder BYOK depends on the account's supported plan and catalog and is managed through
its `/model` wizard; this adapter does not invent a manual BYOK configuration.

Native model names are passed to the selected harness. Codex/Qwen/OpenCode use
`OPENAI_MODEL`; Claude uses `ANTHROPIC_MODEL`; DeepSeek Harness uses `DEEPSEEK_MODEL`.
The Worker injects only the names required by its selected adapter. It rejects a
different model/harness binding and unrelated credential names.

Each turn runs the real native CLI. Later turns restore its exact native session ID in
the same Session Sandbox. Close releases compute while retaining the Gateway's stored
results; opening a fresh Sandbox cannot promise restoration of files or native history
from deleted compute. Use the public lifecycle described in the [managed API guide](managed-agents-api.md).

Codex, Claude and Qwen can provide partial native events. OpenCode's JSON text and
DeepSeek Harness's headless text represent complete messages or committed steps; they
are not token deltas. A terminal native message alone does not prove that every process
has exited. The bridge also observes process exit and owned process cleanup, preserving
an uncertain state when it cannot establish completion.

OpenCode 1.19.5 reports tools only after they complete. Its tool items represent completed
records; a live per-tool timeout cannot be enforced from this stream. The overall run
deadline and owned process cleanup still apply. In the general local runtime, this adapter
supports `read_only` or `full_access` and rejects `workspace_write`, which cannot be mapped
reliably to this native CLI. Managed Session execution uses `full_access` inside its Sandbox.

The new adapters are experimental. Qoder, OpenCode and DeepSeek Harness do not yet map
external MCP server configuration through this adapter API. Qoder 1.1.90 does not expose
the `--max-turns` flag described by some newer documentation, so a configured turn count
is rejected. Steering, functions, subagents and tools remain subject to the Gateway's
capabilities and native harness behavior. See the template's actual verification scope
before relying on a provider, model route or account type.

The DeepSeek adapter invokes the official `@deepseek-ai/dsh` package. The older
`deepseek-harness` named-command template implements a separate project-owned tool loop;
its model execution history does not certify the official native adapter.
