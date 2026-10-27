# Verification: Shared Express managed API keys in Python

- Date: 2026-10-27
- Change: [Issue #143](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/143); [decision](../../notes/proposed/architecture/2026-10-27-managed-api-key.md).
- Result: PARTIAL — client and cloud acceptance passed; unchanged server full-suite failure blocks local make ci.
- Packages: candidate client/server 0.4.0a6 built from main 5d855223e3ec8797b3c4ad7d01644a8a5145b501 plus this PR; no package publication.
- Environment: Linux, Python 3.12.13 (supplementary 3.13.13 checks), Node 22.22.2, real Express cn-hangzhou; candidate CLI from the companion feature branch. Credentials supplied through ignored environment configuration; values not recorded.

## What was verified

Express owns the official Sandbox 2026-08-20 key-resource API. A new or nearly expired key requires explicit consent; the literal `--ci` flag may provide it, while ambient CI does not. Explicit keys retain priority. Reuse is read-only, disabled/deleted keys are not replaced, and unknown writes remain pending. A 30-day resource is shared privately by CLI and Python consumers, with no background renewal promise. English/Chinese docs explain feature/action/resource scopes and RAM authorization.

## Commands run

```sh
python -m pip install -e './server-sdk[dev]' -e './client-sdk[dev]'
make ci
make lint typecheck
make format-check build dist-check
cd client-sdk && pytest tests/ -m 'not integration' -q
ABX_BIN='<candidate CLI>' pytest e2e/test_managed_api_key.py -q
bash scripts/check-repo-health.sh
bash scripts/check-no-local-paths.sh
```

## Results

| Scenario | Result | Detail |
|---|---|---|
| Full client suite, Python 3.12 | PASS | 2338 pass, 27 skip, 10 deselect |
| New managed-key unit coverage | PASS | Eight tests cover explicit priority, readonly resolution, explicit prepare consent, unsafe references and standard E2B override |
| Provider isolation/standard authentication regression | PASS | 29 focused tests after routing standard fallback through the registry composition root |
| Server suite, Python 3.12 | FAIL | 874 pass, 1 fail, 1 skip; malformed WebSocket upgrade expects 400 but gets 501 |
| Clean main comparison | FAIL, same baseline | Same malformed-upgrade failure on unchanged main, Python 3.12/3.13; removing proxy environment variables did not resolve it |
| Lint/format/typecheck | PASS | Ruff; mypy server 56 files and client 101 files |
| Distribution validation | PASS | Both wheels and sdists, twine checks, py.typed and combined clean installation/import |
| Health/hygiene | PASS | Health 106 pass/1 warning/0 fail; hygiene clean |
| Real SDK managed-key acceptance | PASS | One subprocess acceptance test: reject missing confirm before engine IO; explicit preparation; sync Sandbox, AsyncSandbox and ProviderSandbox create/exec/files/kill; shared engine and private storage |

An early direct concrete-provider import in the standard client failed the core isolation test; the final implementation uses the registry boundary, and the full client suite passed after that correction. The server baseline remains unchanged and is not counted as a passing make ci run.

## Cleanup

Acceptance uses an isolated user directory and only its tracked key/sandboxes. Each sandbox is killed in finally. The owned key is disabled/deleted through the real shared engine, its get operation confirms resource-not-found, and the test stops its isolated engine in finally. Companion CLI acceptance independently verified sandbox HTTP 404 and key DescribeApiKey 404. No general all-account janitor was invoked.

## Problems found

The pre-existing server malformed-WebSocket assertion prevents full local make ci success. See follow-up linked in the PR; no server behavior was changed by this client feature. This PR depends on the CLI's new api-key.resolve/api-key.prepare operations landing first. Existing direct API-key SDK use still needs no CLI.

## Not verified

Remote Python 3.10/3.11 matrix, Windows ACL behavior, alternate regions, the full slow cloud matrix and an independently restricted RAM identity were not verified here. Direct cloud SDK behavior is owned/tested by the companion CLI, not reimplemented in Python. No PyPI release was requested or performed.
