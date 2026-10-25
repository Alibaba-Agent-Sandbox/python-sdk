# 运行云端示例

安装客户端时自动安装同版本服务端：

```bash
python -m pip install "agent-sandbox-client[all]==0.4.0a2"
export ABX_SANDBOX_API_KEY="your-express-sandbox-api-key"
# 非默认地域按需配置 ABX_SANDBOX_BASE_URL、ABX_SANDBOX_DOMAIN。
```

在克隆的 `python-sdk` 仓库中执行下列命令。示例导入已安装的公开包，无需注入源码目录。每个脚本创建并清理自己的沙箱，断言业务结果；失败时非零退出。

```bash
python examples/quickstart/01_hello.py
python examples/quickstart/02_file_ops.py
python examples/quickstart/03_web_service.py
python examples/quickstart/04_data_analysis.py
python examples/quickstart/05_decorator_usage.py
python examples/compat-demos/comparison.py
python examples/compat-demos/e2b_data_analysis.py
python examples/compat-demos/e2b_web_scraper.py
python examples/compat-demos/modal_compute.py
python examples/compat-demos/modal_data_analysis.py
python examples/compat-demos/e2e_capability_validation.py
python examples/agents/browser_automation.py
# Requires a real model key / 需要真实模型密钥
python examples/agents/codex_agent.py
```

Node HTTP 入门示例直接使用 `base` 自带的 Node，无需先部署另一个 Web 模板。数据示例使用 `code-interpreter-v1` 并核对实际结果。能力示例没有本地 registry 或模拟云端回退。

`codex_agent.py` 需要 `OPENAI_API_KEY`，可用 `OPENAI_BASE_URL`、`OPENAI_MODEL` 指定兼容模型。它在 `base` 中真实生成并执行 Python 代码，由本地独立排序结果校验。历史文件名不代表它运行 Codex CLI；缺少模型凭证会立即失败。

浏览器示例安装 Playwright 和真实无头 Chromium。默认页面由自有沙箱内的 HTTP 服务提供，可稳定验证标题、链接和截图。设置 `BROWSER_URL` 可访问外部站点，HTTP 失败或缺少预期内容会明确报错。安装仍需连接包和浏览器下载源。

标准客户端导入迁移示例使用配置为极速版账号的 `E2B_API_KEY`、`E2B_API_URL`、`E2B_DOMAIN`，然后执行 `python examples/compat-demos/e2b_import_migration.py`。这些配置名属于标准 E2B 兼容客户端；不要使用其他平台账号的密钥。上述 `ProviderSandbox` 和装饰器示例使用 `ABX_SANDBOX_API_KEY`。

本地 HTTP、会话示例执行 `python examples/run_examples_e2e.py`。它运行真实本地服务进程及受控 Codex/Qwen 协议程序，不调用模型；云端脚本会明确列为 `needs-provider`。另见[示例目录](../../../examples/README.zh-CN.md)和[模板 HTTP API](template-server-api.md)。
