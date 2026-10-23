# Cloud end-to-end practice

Run the repository's cloud examples against a real sandbox on the default provider, **Alibaba Cloud Express** (`alicloud-express`). Do not push an image to ACR.

> 中文版: [../../zh/guide/cloud-examples.md](../../zh/guide/cloud-examples.md)

The Agents API case is not repeated here. For the request sequence, the local stand-in CLIs, and a run that does not read a model key, see [Agents API](agents-api.md). The Chinese page is [Agents API（中文）](../../zh/guide/agents-api.md).

## Setup

The client reads `E2B_API_KEY`. The current client does not treat `E2B_API_KEY` as the sandbox key.

```bash
pip install "agent-sandbox-client[declarative]"
export E2B_API_KEY="your-api-key"
```

When `ABX_PROVIDER` is unset, `Sandbox.create` uses `alicloud-express`. The scripts below pass `timeout` to `Sandbox.create` (sandbox TTL, in seconds, from 60 to 900) and destroy the sandbox when the `async with` block or the `@sandbox` decorator finishes.

From this repo, before `pip install`:

```bash
export PYTHONPATH=client-sdk/src:server-sdk/src
```

## Run these

From the `python-sdk` directory:

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

| Script | What it does in the cloud |
|---|---|
| `examples/quickstart/03_web_service.py` | Template `node-web`. Writes an Express app, runs `npm install`, curls `localhost:3000` inside the sandbox |
| `examples/quickstart/04_data_analysis.py` | Template `base`. Installs pandas, analyzes a CSV, then `run_code()` for the top three rows |
| `examples/quickstart/05_decorator_usage.py` | `@sandbox` on `code-interpreter-v1`: π, a pandas summary, Fibonacci, environment variables |
| `examples/compat-demos/comparison.py` | The same tasks with imperative `Sandbox.create` and with `@sandbox` |
| `examples/compat-demos/e2b_data_analysis.py` | Imperative: upload a CSV, write a pandas report, read the report back |
| `examples/compat-demos/e2b_web_scraper.py` | Imperative: request `https://example.com` from inside the sandbox |
| `examples/compat-demos/modal_compute.py` | `@sandbox`: Monte Carlo π, matrix multiply, distribution fit |
| `examples/compat-demos/modal_data_analysis.py` | `@sandbox`: sales summary, data quality, product rank |

The data-analysis example explicitly writes and runs Python scripts through `commands.run()`. Interpreter calls require a matching interpreter workflow and never fall back to shell.

If create fails, read the error code on the exception (a missing template is `E2001`) and stop that example. Do not switch to pushing an image.

## Two agent examples

Both can start without a paid model key. Set a model key only when you want a real model call.

- `examples/agents/codex_agent.py` uses template `codex`. If that template is not on the account, `Sandbox.create` fails with `E2001` and the script's simulation branch never runs. `OPENAI_API_KEY` is required only for the live model branch.
- `examples/agents/browser_automation.py` does not read a model key. It `pip install`s Playwright on `base`, then runs `playwright install chromium`. If `playwright` is not on `PATH`, `commands.run` raises `E3006` (`exec: "playwright": executable file not found in $PATH`). The `async with` block still destroys the sandbox.

For Codex and Qwen Code HTTP sessions inside a sandbox, use `examples/agents/complete_case.py` from [Agents API](agents-api.md).
