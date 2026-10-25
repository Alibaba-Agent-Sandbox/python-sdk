# Run the cloud examples

Install the public Python pair through the client dependency:

```bash
python -m pip install "agent-sandbox-client[all]==0.4.0a2"
export ABX_SANDBOX_API_KEY="your-express-sandbox-api-key"
# Configure ABX_SANDBOX_BASE_URL and ABX_SANDBOX_DOMAIN for your region if needed.
```

Run these commands from the cloned `python-sdk` repository. They import the installed packages; no source-path injection is needed. Each script creates and cleans up its own sandboxes, asserts business results and exits nonzero on failure.

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

The Node HTTP quickstart uses Node already present in `base`; it does not require deploying a separate web template. The data examples use `code-interpreter-v1` and compare actual results. The capability example has no local-registry or simulated-cloud fallback.

For `codex_agent.py`, set `OPENAI_API_KEY`; optionally set `OPENAI_BASE_URL` and `OPENAI_MODEL`. It generates and executes real Python code inside `base`, with an independent local sorting oracle. Despite the historical filename, it is not a Codex CLI session. Missing model credentials fail immediately.

The browser example installs Playwright and real headless Chromium. Its default HTTP page runs inside the owned sandbox, providing deterministic title/link/screenshot checks. Set `BROWSER_URL` for an external site; non-success HTTP responses and absent expected content fail visibly. Installation still needs outbound access to package/browser repositories.

The standard-client import migration example uses the same project `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and `ABX_SANDBOX_DOMAIN` configuration as the other examples. Run `python examples/compat-demos/e2b_import_migration.py`. These values must belong to the Express account; do not reuse credentials from a different provider.

For local HTTP/session examples run `python examples/run_examples_e2e.py`. That runner uses real local server processes and controlled Codex/Qwen protocol executables, not model calls. Cloud scripts are explicitly listed as `needs-provider` there. See the [example catalog](../../../examples/README.md) and [template HTTP API](template-server-api.md).

Command `timeout` bounds total execution time, including a process that continually writes stdout/stderr. On expiry the client closes its stream, attempts to stop the owned process and raises `CommandTimeoutError`; cleanup can add a short request delay. This is separate from sandbox lifetime and HTTP read inactivity.
