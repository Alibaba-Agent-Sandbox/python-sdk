# Verification: cloud examples on alicloud-express (2026-10-13)

Real `Sandbox.create` runs of the Python SDK examples that had not been executed against the cloud. Provider is the built-in default `alicloud-express` (`ABX_PROVIDER` unset). No image was pushed to ACR. Credential values are omitted.

## Credentials

- `/workspace/.env` does not define `ABX_SANDBOX_API_KEY` or `E2B_API_KEY`.
- `python-sdk/.env` still has `E2B_API_KEY` and does not have `ABX_SANDBOX_API_KEY`. The client reads `ABX_SANDBOX_API_KEY`. The runner copied that existing key into `ABX_SANDBOX_API_KEY` inside the test process only. `.env` was not rewritten.
- `E2B_API_URL` and `E2B_DOMAIN` in `python-sdk/.env` equal the client defaults (`https://api.cn-hangzhou.e2b.fc.aliyuncs.com`, `cn-hangzhou.e2b.fc.aliyuncs.com`), so the process did not set `ABX_SANDBOX_BASE_URL` or `ABX_SANDBOX_DOMAIN`.
- `OPENAI_API_KEY` was not exported. `examples/agents/codex_agent.py` can simulate without it. `examples/agents/browser_automation.py` does not read a model key. No paid model call was made.
- The examples already read `ABX_SANDBOX_API_KEY`. No example source change was required.

## How they were run

Working directory: `/workspace/python-sdk`. Interpreter: Python 3.12.3. `PYTHONPATH=client-sdk/src:server-sdk/src`.

Each example was started as `python <example>`. A thin wrapper logged `Sandbox.create` / `Sandbox.kill` (id, provider, template, TTL, elapsed) and, on create failure, stopped that example with exit 2 before another sandbox was created. After each example, `Sandbox.list` was checked for those ids.

Every create that returned an id used provider `alicloud-express`. Every such sandbox logged `KILL_OK` and was absent from the follow-up list. TTL is the `timeout=` each example already passes to `Sandbox.create` (seconds).

Preflight (not an example): `Sandbox.create(template="base", timeout=60)` then `kill`.

- Result: pass
- Elapsed: 3.66 s (create 1.75 s, kill 0.33 s)
- Sandbox id: `sbx-11aee2db-acb6-4c18-ac64-f0a6d5a73248`

## Results

| Example | Result | Elapsed | Sandbox id | TTL |
|---|---|---|---|---|
| `examples/quickstart/03_web_service.py` | pass | 54.1 s | `sbx-2dc507cd-9c84-4f31-abf4-9c4dee77f7fe` | 600 |
| `examples/quickstart/04_data_analysis.py` | pass | 69.1 s | `sbx-c6972a0c-4022-4542-98a6-d5e727821f98` | 300 |
| `examples/quickstart/05_decorator_usage.py` | pass | 29.7 s | four ids below | 300 / 300 / 120 / 300 |
| `examples/compat-demos/comparison.py` | pass | 74.0 s | four ids below | 60 / 60 / 120 / 120 |
| `examples/compat-demos/e2b_data_analysis.py` | pass | 101.6 s | `sbx-e99ef4aa-231c-4562-8164-d219b7bb09fd` | 300 |
| `examples/compat-demos/e2b_web_scraper.py` | pass | 12.2 s | `sbx-fed63cd5-58b0-447c-af31-e9d3a66e8e2e` | 300 |
| `examples/compat-demos/modal_compute.py` | pass | 63.9 s | six ids below | 120 |
| `examples/compat-demos/modal_data_analysis.py` | pass | 37.3 s | four ids below | 120 / 60 / 60 / 60 |
| `examples/agents/codex_agent.py` | fail | 1.3 s | none | 600 (not created) |
| `examples/agents/browser_automation.py` | fail | 105.1 s | `sbx-4e0f35a0-dab9-4333-96eb-58a91a4699d2` | 900 |

No example was skipped. Both agent scripts can start without a paid model key, so they were run. `codex_agent.py` failed at create, before its simulation branch.

### `examples/quickstart/03_web_service.py` — pass

Command: `python examples/quickstart/03_web_service.py`

Create 2.64 s, kill 0.92 s. Template `node-web`. A capability warning said `node-web` fell back to `DEFAULT_CAPABILITIES`. The example still computed a public URL and the in-sandbox curls succeeded. `X-Access-Token` was printed by the example and is redacted here.

```text
✓ 依赖安装完成
[node] Server running on port 3000
URL  : https://3000-sbx-2dc507cd-9c84-4f31-abf4-9c4dee77f7fe.cn-hangzhou.e2b.fc.aliyuncs.com
需要 Header: {'X-Access-Token': '[REDACTED]'}
GET /        {"message":"Hello from Sandbox!","timestamp":"2026-10-13T05:59:44.445Z","node_version":"v20.20.2"}
GET /health  {"status":"ok","uptime":5.999676709}
GET /api/echo {"query":{"foo":"bar","lang":"zh"},"headers":{"host":"localhost:3000","user-agent":"curl/7.88.1","accept":"*/*"}}
✓ 沙箱已自动销毁，服务已停止
```

### `examples/quickstart/04_data_analysis.py` — pass

Command: `python examples/quickstart/04_data_analysis.py`

Create 1.44 s, kill 1.05 s. Template `base`. pandas installed. `run_code()` logged `CodeInterpreter service unavailable (HTTP 404), falling back to shell execution` and still printed the top-3 table.

```text
总行数: 12
总销售额: $64,785.65
top_product: Widget A
top_region: North
Top 3 单笔收入: Widget C East 7499.25; Widget B West 7498.50; Widget A North 6597.80
✓ 沙箱已自动销毁
```

### `examples/quickstart/05_decorator_usage.py` — pass

Command: `python examples/quickstart/05_decorator_usage.py`

Four `code-interpreter-v1` sandboxes, each killed before the next call.

| Step | Sandbox id | Create | Kill |
|---|---|---|---|
| Monte Carlo π | `sbx-03143a02-5233-4bc5-9eb6-1c1b4b2fcc6b` | 2.03 s | 0.40 s |
| pandas summary | `sbx-6540bfef-b971-4b01-b33c-cb50651373ad` | 1.40 s | 0.36 s |
| Fibonacci | `sbx-d9b58496-7a58-4f4b-b083-fa8895b18647` | 1.39 s | 0.37 s |
| env | `sbx-cc0733f0-055c-400d-a538-ec496145d17e` | 1.39 s | 0.27 s |

```text
π ≈ 3.143256
误差: 0.001663
行数: 4
列名: ['name', 'age', 'score']
前 15 项: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377]
APP_MODE = sandbox-demo
HOME = /home/user
✓ 所有示例完成
```

### `examples/compat-demos/comparison.py` — pass

Command: `python examples/compat-demos/comparison.py`

| Step | Sandbox id | Template | TTL | Create | Kill |
|---|---|---|---|---|---|
| E2B Fibonacci | `sbx-c2607d4e-f2d0-4b72-acaf-83b1a95e60f0` | base | 60 | 1.49 s | 0.31 s |
| Modal Fibonacci | `sbx-d9bbed9b-0bf1-4c8e-868d-87b47a91d116` | code-interpreter-v1 | 60 | 1.26 s | 0.27 s |
| E2B sort/stats | `sbx-e9645473-0d24-40e7-a213-fc956e77b729` | base | 120 | 1.57 s | 0.97 s |
| Modal sort/stats | `sbx-67f9033b-32bc-42a4-9602-0a054fd7f33f` | code-interpreter-v1 | 120 | 3.54 s | 0.39 s |

Fibonacci n=20 matched on both styles: `[0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181]` (4.69 s and 6.17 s). Sort/stats matched: mean 47.15, median 49.70, std 30.97 (52.19 s and 10.78 s). `结果一致: True`.

### `examples/compat-demos/e2b_data_analysis.py` — pass

Command: `python examples/compat-demos/e2b_data_analysis.py`

Create 1.84 s, kill 1.01 s. Template `base`. 15 records, total revenue ¥46,350.00, daily average ¥3,090.00, top product Widget B ¥19,200.00. Report 769 characters. JSON summary begins `total_records: 15`, `total_revenue: 46350.0`.

### `examples/compat-demos/e2b_web_scraper.py` — pass

Command: `python examples/compat-demos/e2b_web_scraper.py`

Create 1.71 s, kill 0.30 s. Template `base`. `requests=2.34.2`, `bs4=4.15.0`. Fetched `https://example.com`: title `Example Domain`, HTTP 200, 1 paragraph, JSON result 379 characters.

### `examples/compat-demos/modal_compute.py` — pass

Command: `python examples/compat-demos/modal_compute.py`

Six `code-interpreter-v1` sandboxes, TTL 120, all killed.

| Step | Sandbox id | Create | Kill |
|---|---|---|---|
| Monte Carlo π | `sbx-f09e10a3-7767-4eba-905e-1c8e2c76cb49` | 1.61 s | 0.30 s |
| matrix 500 | `sbx-fbf1dd46-28c4-43ee-bc47-6cd99f80a0de` | 1.45 s | 0.31 s |
| matrix 1000 | `sbx-2b11d8a6-7e69-4179-b6d2-949cad5d7bc6` | 3.05 s | 0.33 s |
| normal | `sbx-39491ca6-de97-4f8e-8f43-49a6bd5850d2` | 1.53 s | 0.36 s |
| exponential | `sbx-95ef32d0-d3a5-4388-bd19-169cfb26cab5` | 1.32 s | 0.29 s |
| uniform | `sbx-9b5a73bf-845c-42aa-98d6-4604518ce0e3` | 2.01 s | 0.34 s |

```text
π ≈ 3.1416748   samples 10,000,000   abs error 0.000082   total 10.40s
[500x500] 0.0668s, GFLOPS=3.74
[1000x1000] 0.0263s, GFLOPS=76.09
normal μ=49.9896 σ=9.9414
exponential μ=4.9927 σ=4.9776
uniform μ=49.9877 σ=28.7393
✓ 所有计算示例完成
```

### `examples/compat-demos/modal_data_analysis.py` — pass

Command: `python examples/compat-demos/modal_data_analysis.py`

| Step | Sandbox id | TTL | Create | Kill |
|---|---|---|---|---|
| sales | `sbx-acfded8a-33c7-40a1-be23-e2966320537f` | 120 | 1.59 s | 0.31 s |
| quality | `sbx-7bee084d-2e11-49fb-a7c5-72766a121439` | 60 | 1.61 s | 0.34 s |
| rank by amount | `sbx-31baf48a-adaf-419e-b8df-c3da38cace51` | 60 | 1.38 s | 0.27 s |
| rank by quantity | `sbx-3b9eaa85-a483-47cc-ab05-9c74a9fafcbd` | 60 | 1.65 s | 0.32 s |

15 rows, total revenue ¥46,350.00, top product Widget B ¥19,200.00, peak day 2024-01-11 ¥5,250.00. No nulls, 0 duplicate rows, 3 products. Revenue rank Widget B, A, C. Quantity rank Widget B 128, Widget A 111, Widget C 35.

### `examples/agents/codex_agent.py` — fail

Command: `python examples/agents/codex_agent.py`

Create failed before a sandbox id existed. The runner stopped the example (exit 2). Error code `E2001`.

```text
CREATE_FAIL template=codex ttl=600 elapsed=1.10s code=E2001 type=TemplateNotFoundError
message=[E2001] template not found
Suggestion: Run 'abx template list' to see available templates.
```

`OPENAI_API_KEY` was absent from the process, so the paid branch would not have run. The script's simulation branch was not reached because create failed first.

### `examples/agents/browser_automation.py` — fail

Command: `python examples/agents/browser_automation.py`

Create succeeded (1.46 s), template `base`. `pip install playwright` completed. The next command, `playwright install chromium --with-deps`, did not return a failed `result`; `commands.run` raised `EnvdRpcError` `E3006`:

```text
[E3006] envd RPC /process.Process/Start failed (HTTP 500): exec: "playwright": executable file not found in $PATH
```

`async with` still killed the sandbox (kill 0.84 s). Follow-up list: absent. Exit 1. This script does not read `OPENAI_API_KEY`.

## Cleanup

24 sandboxes were created (1 preflight + 23 example sandboxes). Each logged `KILL_OK`. A `Sandbox.list(limit=100)` after each example reported `CLEANUP_ABSENT` for every id from that example. `codex_agent.py` created none.
