# Verification: Python 0.3.1a3 public release

- Date: 2026-10-24
- Change: [Issue #97](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/97), following [PR #96](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/96).
- Result: PASS for public publication, installation and the four managed workflow cases. Initial publication readback failures are preserved below.
- Release source: `6398c6fdd777ff6c8ae9c7b2acb4cc52d457a633`, tag [`v0.3.1a3`](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.3.1a3).
- Packages: public PyPI `agent-sandbox-client==0.3.1a3` and its exact matching `agent-sandbox-server==0.3.1a3` dependency.
- Environment: fresh Python 3.12.13 environment, public PyPI index, real Alibaba Cloud Express. Credentials supplied through environment variables; values excluded.

## What was verified

The uploaded packages install without editable source checkouts, expose standard sync/async clients, ProviderSandbox and the server entrypoint, and launch the two native managed templates through both supported provider-selector forms.

## Commands run

```bash
python -m pip install --no-cache-dir --index-url https://pypi.org/simple agent-sandbox-client==0.3.1a3
python -m pip check
python -m pytest e2e/test_managed_workflow.py -q -ra
```

Imports were checked outside the source checkout, including a `site-packages` path assertion and equal client/server distribution versions. The E2E runner used the same fresh environment and installed public packages, not editable SDK sources.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Final PR checks | PASS | CI [40106958479](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40106958479), docs [40106958477](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40106958477), exact head `a7928e785b9f175dcf3641b08313e1c465281a88` |
| Publication attempt 1 | FAIL | [40107539046](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40107539046/attempts/1): validation, upload of both packages and all four public artifact digest checks passed; the immediate pip readback still saw only a1/a2 in the public simple index |
| Publication attempt 2 | FAIL | Existing public artifact digest comparisons passed; the installation index still returned only a1/a2 at 15:44 UTC |
| Publication attempt 3 | PASS | [Final run](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40107539046/attempts/3), retried after independent JSON and HTML simple-index responses exposed a3; unchanged release source and artifact digests, successful public pip readback |
| Independent public installation | PASS | Both 0.3.1a3 wheels installed using `--no-cache-dir`; `pip check` reported no broken requirements |
| Imports and version lockstep | PASS | Standard sync/async clients, ProviderSandbox and server start callable; both distribution versions 0.3.1a3 |
| Public-package live rerun | PASS | 4 passed in 17.82s: `base` and `code-interpreter-v1`, each via string and actual built-in Provider object |

## Public artifacts

The public version metadata exposed these SHA256 values. Both packages' wheel and sdist uploads completed on 2026-10-24 at 15:40 UTC.

| File | SHA256 |
| --- | --- |
| `agent_sandbox_client-0.3.1a3-py3-none-any.whl` | `c4a75cc0cc5518bc45233b12a04520d44d38c865a051f082ccd0407031ac3773` |
| `agent_sandbox_client-0.3.1a3.tar.gz` | `0fd2e3ab90a8f645bab4b070d2be1c439161985807c92cc39c6a0bfc21d1982b` |
| `agent_sandbox_server-0.3.1a3-py3-none-any.whl` | `0fdcd17a015748e6e2dcf477a08aef9b884fcc93c98c65845ce7865f03a9184a` |
| `agent_sandbox_server-0.3.1a3.tar.gz` | `5571073bf5bc2abeb73ba7b001483f2062986a4598da09f1d72060a01bd7f863` |

## Cleanup

Every successful live case left its owning workflow context and used a fresh control-plane query to confirm SandboxNotFoundError. No owned sandboxes remained; no new template or image was created. The runner's fallback tracker remained available for failures.

## Problems found

PyPI JSON metadata and its installation index exposed the new release at different times. The first publication job's metadata retries eventually passed, but the following immediate pip install failed. The second attempt observed the same old installation index. After independent JSON and HTML simple-index requests included a3, the third attempt passed. These failures are preserved. No tag moved and no published artifact was replaced; recovery compared existing digests before skipping already published files.

## Not verified

These live cases exercise shell execution, native template creation and cleanup. They do not validate the code interpreter API, all source-template applications, PTY or real-model tasks. This is an alpha release, not a production certification.
