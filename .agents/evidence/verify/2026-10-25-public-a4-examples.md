# Verification: published a4 cloud and local examples

- Date: 2026-10-25
- Result: PASS for the stated examples; not whole-catalog or production certification.
- Source: `b1dbc5698ed42b9a87ab0ac6df452d5d187dd0a0`, merged [PR127](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/127).
- Runtime: official PyPI client/server `0.4.0a4`; Linux, Python 3.13.13. Separate fresh HOME per cloud example; canonical ABX configuration, no E2B overrides or source injection.

## What was verified

All 14 unchanged cloud examples exited zero with public packages. The real model
example used a configured OpenAI-compatible endpoint supporting `qwen3-coder-flash`,
executed generated quicksort code and compared five inputs with independent
`sorted()` results. It did not invoke the Codex CLI. The browser installed Chromium,
rendered its owned page, checked title/heading/link and retrieved an 11,473-byte PNG.
The [source/output manifest](2026-10-25-public-a4-example-manifest.json) freezes the
tested scripts; [cloud results](2026-10-25-public-a4-cloud-examples.json) retain
each outcome and cleanup observation without resource identifiers.

| Example | Result | Seconds | Owned resources |
| --- | --- | --- | --- |
| `examples/quickstart/01_hello.py` | PASS | 4.08 | 1 |
| `examples/quickstart/02_file_ops.py` | PASS | 4.96 | 1 |
| `examples/quickstart/03_web_service.py` | PASS | 4.03 | 1 |
| `examples/quickstart/04_data_analysis.py` | PASS | 24.28 | 1 |
| `examples/quickstart/05_decorator_usage.py` | PASS | 16.55 | 4 |
| `examples/compat-demos/e2e_capability_validation.py` | PASS | 7.76 | 2 |
| `examples/compat-demos/comparison.py` | PASS | 42.33 | 4 |
| `examples/compat-demos/e2b_data_analysis.py` | PASS | 65.56 | 1 |
| `examples/compat-demos/e2b_web_scraper.py` | PASS | 7.98 | 1 |
| `examples/compat-demos/modal_compute.py` | PASS | 33.0 | 6 |
| `examples/compat-demos/modal_data_analysis.py` | PASS | 22.94 | 4 |
| `examples/compat-demos/e2b_import_migration.py` | PASS | 2.98 | 1 |
| `examples/agents/browser_automation.py` | PASS | 236.28 | 1 |
| `examples/agents/codex_agent.py` | PASS | 17.63 | 1 |

The original local runner returned zero: 10 successful checks, zero failures,
11 explicitly needing a provider. Those 10 comprise one compilation check and
nine real local HTTP/file/process/script checks. Hosted Codex/Qwen checks use
controlled protocol fixtures, not real model calls. An observer shortened only
the hosted-Codex child budget: the original main returned one with nine successful
checks and one expected failure, continued to later cases and printed its final
table. A separate actual exit-7 child, actual 0.5-second timeout and successful
child produced `[7, 124, 0]` and `[fail, fail, ok]`. The earlier failure was retained;
`TimeoutExpired` did not abort the remaining cases. See [local results](2026-10-25-public-a4-local-examples.json).

## Commands run and reproduction

Install public packages independently of the source checkout. No editable SDK
installation or PYTHONPATH is used. Cloud examples used the all extra; the local
runner used ordinary `agent-sandbox-client==0.4.0a4` without extras.

```bash
python3 -m venv public-sdk
. public-sdk/bin/activate
python -m pip install --index-url https://pypi.org/simple --no-cache-dir 'agent-sandbox-client[all]==0.4.0a4'
python -m pip check
git clone https://github.com/Alibaba-Agent-Sandbox/python-sdk.git source
git -C source checkout b1dbc5698ed42b9a87ab0ac6df452d5d187dd0a0
python source/examples/quickstart/01_hello.py
```

Repeat the final command with each exact table path. Supply your own documented
`ABX_PROVIDER=alicloud-express`, `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and
`ABX_SANDBOX_DOMAIN` through private environment configuration. Remove conflicting
E2B overrides and use a fresh HOME outside checkout configuration for each run.
For the real model example additionally supply `OPENAI_API_KEY`, `OPENAI_BASE_URL`
and `OPENAI_MODEL=qwen3-coder-flash` for an endpoint that supports this model.
Never print credentials or publish ownership journals. Local checks require no
provider/model credentials:

```bash
python source/examples/run_examples_e2e.py
```

The timeout control calls the maintained runner's `run_script` on three temporary
scripts in order: `raise SystemExit(7)` with a two-second budget; a script writing
its own PID then `time.sleep(30)` with a 0.5-second budget; and `print('continued')`
with a two-second budget. Require row statuses `fail, fail, ok`, timeout exit124,
and `os.kill(pid, 0)` to raise `ProcessLookupError` for that owned timeout child.
This tests actual subprocess timeout handling; it does not mock `TimeoutExpired`.

## Cleanup

Each example's own cleanup had already removed every one of the 29 created
resources when observed. Recovery deletion was never counted as a passing example.
A separate public-SDK readback returned typed `SandboxNotFoundError` for all 29
owned identifiers: [independent cleanup summary](2026-10-25-public-a4-example-cleanup.json).
All 27 directly observed owned local child PIDs and unique-marker process scans
were independently absent; the timeout child was also checked individually.
Raw logs and ownership journals remain private; no IDs or credentials are copied.

## Problems found and limits

The browser took 236.28 seconds. Earlier a3 observations took 105.53 and 157.62
seconds; the earlier a2 cold installation failed at 300 seconds. The
[historical a2 evidence](2026-10-25-public-sdk-documentation.md) remains unchanged.
Success here does not establish the earlier timeout's root cause or promise a
stable cold-install duration. This is an alpha package and scoped sample result.

These runs do not cover fresh CLI installation, all catalog templates, other
platforms, real hosted Codex/Qwen model invocations, PTY or desktop support.
They are not the complete `make e2e` suite. Local fixtures, real cloud calls and
static documentation checks retain separate scopes. The later Template help
import audit is a separate known documentation defect, not fixed by these runs.

## Owner checks

These are completed public-a4 observations, not candidate-a5 results. The help
import correction and paired candidate version have their own separate checks;
this record does not imply that candidate is published or this PR is merged.
