# Verification: published a6 cloud and local examples

- Date: 2026-10-25
- Result: PASS for the stated examples; not whole-catalog or production certification.
- Source: `8e610a3658040d8d6973e7951f9590ea50a4d70a`, merged [PR131](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/131).
- Runtime: official PyPI client/server `0.4.0a6`; Linux, Python 3.13.13. One new isolated HOME shared by the 14 example child processes for this batch, outside checkout configuration; canonical ABX settings, no E2B overrides or source injection.

## What was verified

All 14 unchanged cloud examples exited zero with public packages. The real model
example used a configured OpenAI-compatible endpoint supporting `qwen3-coder-flash`,
executed generated quicksort code and compared five inputs with independent
`sorted()` results. It did not invoke the Codex CLI. The browser installed Chromium,
rendered its owned page, checked title/heading/link and retrieved an 11,473-byte PNG.
The [source/output manifest](2026-10-25-public-a6-example-manifest.json) freezes the
tested scripts; [cloud results](2026-10-25-public-a6-cloud-examples.json) retain
each outcome and cleanup observation without resource identifiers.

| Example | Result | Seconds | Owned resources |
| --- | --- | --- | --- |
| `examples/quickstart/01_hello.py` | PASS | 4.42 | 1 |
| `examples/quickstart/02_file_ops.py` | PASS | 4.73 | 1 |
| `examples/quickstart/03_web_service.py` | PASS | 4.31 | 1 |
| `examples/quickstart/04_data_analysis.py` | PASS | 37.29 | 1 |
| `examples/quickstart/05_decorator_usage.py` | PASS | 16.56 | 4 |
| `examples/compat-demos/e2e_capability_validation.py` | PASS | 7.67 | 2 |
| `examples/compat-demos/comparison.py` | PASS | 26.32 | 4 |
| `examples/compat-demos/e2b_data_analysis.py` | PASS | 22.97 | 1 |
| `examples/compat-demos/e2b_web_scraper.py` | PASS | 7.62 | 1 |
| `examples/compat-demos/modal_compute.py` | PASS | 32.28 | 6 |
| `examples/compat-demos/modal_data_analysis.py` | PASS | 21.43 | 4 |
| `examples/compat-demos/e2b_import_migration.py` | PASS | 3.21 | 1 |
| `examples/agents/browser_automation.py` | PASS | 84.44 | 1 |
| `examples/agents/codex_agent.py` | PASS | 10.34 | 1 |

The original local runner returned zero: 10 successful checks, zero failures,
11 explicitly needing a provider. Those 10 comprise one compilation check and
nine real local HTTP/file/process/script checks. Hosted Codex/Qwen checks use
controlled protocol fixtures, not real model calls. An observer shortened only
the hosted-Codex child budget: the original main returned one with nine successful
checks and one expected failure, continued to later cases and printed its final
table. A separate actual exit-7 child, actual 0.5-second timeout and successful
child produced `[7, 124, 0]` and `[fail, fail, ok]`. The earlier failure was retained;
`TimeoutExpired` did not abort the remaining cases. See [local results](2026-10-25-public-a6-local-examples.json).
The maintained runner hash is `642e2abbbb8a9ba6c43bef04ed4fc4c7ae3977c942ca6e48d7764dad5b1ea63e`,
unchanged from the earlier checkpoint; these are new actual a6 runs.

## Commands run and reproduction

Install public packages independently of the source checkout. No editable SDK
installation or PYTHONPATH is used. The cloud examples and local runner used
the same fresh official `agent-sandbox-client[all]==0.4.0a6` environment. The local
runner used a separate isolated HOME with provider/model credentials removed;
the non-all help/HTTP installation is a separate delivery check, not this runner
environment.

```bash
python3 -m venv public-sdk
. public-sdk/bin/activate
python -m pip install --index-url https://pypi.org/simple --no-cache-dir 'agent-sandbox-client[all]==0.4.0a6'
python -m pip check
git clone https://github.com/Alibaba-Agent-Sandbox/python-sdk.git source
git -C source checkout 8e610a3658040d8d6973e7951f9590ea50a4d70a
python source/examples/quickstart/01_hello.py
```

Repeat the final command with each exact table path. Supply your own documented
`ABX_PROVIDER=alicloud-express`, `ABX_SANDBOX_API_KEY`, `ABX_SANDBOX_BASE_URL` and
`ABX_SANDBOX_DOMAIN` through private environment configuration. Remove conflicting
E2B overrides and use one new isolated HOME outside checkout configuration for
the batch, shared by its example child processes.
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
owned identifiers: [independent cleanup summary](2026-10-25-public-a6-example-cleanup.json).
All 27 directly observed owned local child PIDs and unique-marker process scans
were independently absent; the timeout child was also checked individually.
Raw logs and ownership journals remain private; no IDs or credentials are copied.

## Problems found and limits

The browser took 84.44 seconds. Earlier a4 took 236.28 seconds, a3 observations
took 105.53 and 157.62 seconds, and a2 cold installation failed at 300 seconds.
Those historical receipts remain unchanged. This success does not establish the
earlier timeout's root cause or promise a stable cold-install duration. This is
an alpha package and scoped sample result.

These runs do not cover fresh CLI installation, all catalog templates, other
platforms, real hosted Codex/Qwen model invocations, PTY or desktop support.
They are not the complete `make e2e` suite. Local fixtures, real cloud calls and
static documentation checks retain separate scopes.

## Owner checks and current guidance

The following guidance PR changes the decorator example's installation docstring
from a4 to a6 only. Its executable AST is identical to the actually tested source;
these receipts retain the original full-file hash, not a claim to have executed
a later edited file. No API, runtime, example execution logic or version changes
are included in that documentation follow-up. Its exact-head CI/review/merge are
separate pending gates; no new package release is performed.
