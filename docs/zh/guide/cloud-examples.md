# 云上端到端练习

当前 SDK 安装使用[配套源码安装指南](install-python.md)。

在默认提供方 **阿里云极速版**（`alicloud-express`）上，用真实沙箱把仓库里的云端示例跑一遍。不需要把镜像推到 ACR。

> English: [../../en/guide/cloud-examples.md](../../en/guide/cloud-examples.md)

Agents API 的完整案例不在本页。那一组请求、本地替身 CLI，以及不读取模型密钥的跑法，见 [Agents API](agents-api.md)。

## 准备

客户端读取 `ABX_SANDBOX_API_KEY`。旧名字 `E2B_API_KEY` 不会被当前客户端当成沙箱密钥。

```bash
python -m pip install \
  "agent-sandbox-server @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=server-sdk" \
  "agent-sandbox-client[declarative] @ https://github.com/Alibaba-Agent-Sandbox/python-sdk/archive/e86cb0be24e0083a27396b260298e7cf27b660d6.tar.gz#subdirectory=client-sdk"
export ABX_SANDBOX_API_KEY="your-api-key"
```

未设置 `ABX_PROVIDER` 时，`Sandbox.create` 使用 `alicloud-express`。下面的脚本自己把 `timeout` 传给 `Sandbox.create`（这是沙箱 TTL，单位秒，从 60 到 900），并在 `async with` 或 `@sandbox` 结束时销毁沙箱。

在本仓库里、尚未 `pip install` 时，把源码放到 `PYTHONPATH`：

```bash
export PYTHONPATH=client-sdk/src:server-sdk/src
```

## 照着跑

在 `python-sdk` 目录：

```bash
python examples/quickstart/03_web_service.py
python examples/quickstart/04_data_analysis.py
python examples/quickstart/05_decorator_usage.py
python examples/compat-demos/comparison.py
python examples/compat-demos/e2b_data_analysis.py
python examples/compat-demos/e2b_web_scraper.py
python examples/compat-demos/modal_compute.py
python examples/compat-demos/modal_data_analysis.py
```

| 脚本 | 它在云上做什么 |
|---|---|
| `examples/quickstart/03_web_service.py` | 模板 `node-web`。写入 Express 应用，`npm install`，在沙箱内请求 `localhost:3000` |
| `examples/quickstart/04_data_analysis.py` | 模板 `base`。安装 pandas，分析 CSV，再用 `run_code()` 取前三名 |
| `examples/quickstart/05_decorator_usage.py` | `@sandbox`，模板 `code-interpreter-v1`。π、pandas 摘要、斐波那契、环境变量 |
| `examples/compat-demos/comparison.py` | 同一任务的命令式 `Sandbox.create` 与 `@sandbox` |
| `examples/compat-demos/e2b_data_analysis.py` | 命令式：上传 CSV，pandas 出报告，再把报告读回来 |
| `examples/compat-demos/e2b_web_scraper.py` | 命令式：在沙箱里请求 `https://example.com` |
| `examples/compat-demos/modal_compute.py` | `@sandbox`：蒙特卡洛 π、矩阵乘、分布拟合 |
| `examples/compat-demos/modal_data_analysis.py` | `@sandbox`：销售汇总、数据质量、产品排名 |

`04_data_analysis.py` 在 `base` 上调用 `run_code()` 时，代码解释器端口可能返回 HTTP 404。客户端会改走 shell，示例仍打印表格。

创建失败时看异常上的错误码（例如模板不存在是 `E2001`），停掉这个示例，不要改去推镜像。

## 两个 Agent 示例

它们不需要付费模型密钥也能启动。模型密钥只在你要调用真实模型时才设置。

- `examples/agents/codex_agent.py` 使用模板 `codex`。账户上没有这个模板时，`Sandbox.create` 以 `E2001` 失败，走不到脚本里的模拟分支。真实模型调用才需要 `OPENAI_API_KEY`。
- `examples/agents/browser_automation.py` 不读取模型密钥。它在 `base` 里 `pip install playwright`，再执行 `playwright install chromium`。若 `playwright` 不在 `PATH` 上，`commands.run` 抛出 `E3006`（`exec: "playwright": executable file not found in $PATH`）。`async with` 仍会销毁沙箱。

沙箱里的 Codex / Qwen Code HTTP 会话，用 [Agents API](agents-api.md) 的 `examples/agents/complete_case.py`。
