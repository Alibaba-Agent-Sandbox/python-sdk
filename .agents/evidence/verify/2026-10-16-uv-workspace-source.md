# Verification: uv workspace source

- Date: 2026-10-16
- Change: [SDK issue 28](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/28)
- Result: PARTIAL
- Package under test: agent-sandbox-client and agent-sandbox-server 0.3.0, both editable from this checkout
- Environment: Linux x86_64, Python 3.13.13, uv 0.11.28; uv package builds used Python 3.11.15. No credentials were needed or read for these checks.

## What was verified

The root workspace now identifies the local server SDK as the source of the
client's server dependency. The originally failing editable install succeeds
without `--no-sources`. Real uv parsing, Hatchling builds and wheel metadata checks
were exercised. These checks do not establish real-cloud runtime correctness.

## Commands run

`DEV_PYTHON` denotes the existing development virtual environment's Python;
`DIST_DIR` denotes a temporary output directory outside the checkout.

```bash
uv pip install --python "$DEV_PYTHON" -e ./server-sdk -e './client-sdk[dev]'
uv pip install --dry-run --no-deps --offline --no-build-isolation --python "$DEV_PYTHON" -e ./server-sdk -e './client-sdk[dev]'
uv build --all-packages --out-dir "$DIST_DIR"
twine check "$DIST_DIR"/*
cd client-sdk && pytest tests/test_packaging.py -q
cd server-sdk && pytest tests/test_packaging.py -q
make test
make lint
make typecheck
bash scripts/check-repo-health.sh --quiet
make hygiene
```

The development environment was also supplied with `hatchling`, `build` and
`twine` for actual package builds. A temporary copy of the workspace with only
the root source mapping removed provided the negative control. Both wheel
`METADATA` files were checked for absence of `file://`; the client was checked
for `Requires-Dist: agent-sandbox-server==0.3.0`.

## Results

| Scenario / test | Result | Notes |
|---|---|---|
| Original editable install, before fix | Expected failure | `agent-sandbox-server` is a workspace member but missing a `tool.uv.sources` entry |
| Original editable install, after fix | PASS | 59 packages resolved; both local SDKs built and installed |
| Offline metadata dry run | PASS | No installation or network access |
| Temporary workspace negative control | PASS | Removing the source mapping reproduces the missing-entry failure |
| Client packaging tests | PASS | 7 tests, including the real uv regression |
| Server packaging tests | PASS | 5 tests, run after Hatchling was installed |
| Workspace builds | PASS | Both SDK wheels and source distributions built |
| Distribution metadata and twine | PASS | Four artifacts passed; no local source URLs in wheel metadata; server version pin retained |
| `make lint` | PASS | Both packages |
| `make typecheck` | PASS | Server 56 files; client 83 files |
| `make test` | FAIL | Server: 7 failed, 843 passed, 1 skipped in 314.82 seconds; make stops before client tests |
| Independent complete client suite | PASS | `pytest tests/ -v --tb=short` from `client-sdk/`: 1896 passed, 21 skipped in 159.67 seconds |
| Repository health | FAIL | 105 checks passed, one warning, one pre-existing English/Chinese archive-page mismatch |
| `make hygiene` | PASS | No local paths or credential-like strings found |

## Cleanup

The negative-control workspace was deleted automatically. Distribution outputs
remain in a temporary directory outside the repository. The full server tests
left an untracked `server-sdk/out.txt`, which was removed. No cloud resources were
created by these packaging checks; no credential files or permission settings
were changed. No lockfile was generated.

## Problems found

The full server run has seven failures outside the changed packaging configuration:

- `test_app_agents_transport.py::TestResponsesWebSocket::test_upgrade_without_a_key_is_a_400_not_a_hang`
  and `test_token_is_required_for_the_upgrade`, plus
  `test_policy_pipeline.py::TestAuthentication::test_ambiguous_x_access_token_rejected`,
  received `HTTP/1.1 501 Not Implemented` with the platform response body
  `项目网络审计已关闭` (project network auditing is disabled). No platform settings were
  changed and no bypass was attempted.
- `test_http_hardening.py::TestContentLength::test_valid_still_works`,
  `TestPolicyModeFraming::test_transfer_encoding_rejected_in_policy_mode`, and
  `TestBodyLimit::test_lying_content_length_cannot_exceed_cap` parsed a raw HTTP
  response status of `0` rather than the expected `200`, `400`, or `413`.
- `test_routes_system.py::TestPackages::test_pip_returns_structure` found no
  `pytest` in the package listing. This uv-created environment has no pip module.

The server collection initially skipped its packaging module because Hatchling
was not yet installed. Its five packaging tests were subsequently run and passed.
The independent full client run, including the new regression, passed.

The health failure is the existing `docs/en/archive/provider-opensandbox-research.md`
without a Chinese counterpart. Its warning is the existing missing release guide.
Neither is changed by this packaging fix.

## Not verified

Real-cloud E2E has not been run for this SDK change. The repository's complete
definition of done remains open until its required verification and gate results
are resolved. This evidence records packaging validation only.
