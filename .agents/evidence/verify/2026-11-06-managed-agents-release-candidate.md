# Verification: Managed Agents release candidate continuation

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156; base candidate `3ba9bd3c8cdb46a7ce8366c4058221d11d4c11f0` plus the scoped import/type-boundary corrections and conditional E2E contract update.
- Result: PARTIAL — local gates and the recorded cloud scenarios passed; remote CI, public release and complete managed FC/template delivery remain separate gates.
- Package under test: matching client/server 0.4.0a7 source candidate; no public artifact overwritten.
- Environment: CPython 3.12.13 on Linux, isolated task environment and PID namespace; pytest 9.2.0, Ruff 0.17.4, mypy 2.4.1, psycopg 3.3.8 and pgserver 0.1.4. Credential values are not recorded.

## What was verified

The continuation reuses the existing managed Session implementation rather than replacing the
older run-only draft. The current main commit `c6351c7d6bf1654ae590c9eda7e410cb21d56764` is already
an ancestor of the feature branch. Its original worktree and historical evidence remain intact.

A fresh interpreter importing `ManagedExpressBackend` loaded the upper managed service/store
through the error import. Cross-review accepted the narrow correction: define `ManagedError`
in the models layer and retain the exact same public class through the old import path.
No error code, HTTP envelope or exception inheritance changes.

Fresh dependency installation also exposed existing type errors with psycopg 3.3.8/mypy 2.4.1.
The PostgreSQL kwargs now have an exact `TypedDict` for `options` and optional `sslrootcert`;
the internal numeric timeout intermediate has a `float` annotation. The executed expressions,
libpq options and rejection of malformed deadlines are unchanged. Cross-review rejected a
runtime float conversion because it would also accept previously rejected string deadlines.

The generic provider E2E still asserted that `base.pause()` must fail locally with E8004,
although main already implements conditional pause. Its actual cloud HTTP 400 was preserved.
Cross-review accepted removing that obsolete assertion; eligible-template pause/resume remains
the responsibility of the existing opt-in test and was not verified by this run.

## Commands run

`SDK_VERIFY_ENV` identifies the isolated task environment; it is not a required user path.

- `uv venv --python 3.12 "$SDK_VERIFY_ENV"`
- `uv pip install --python "$SDK_VERIFY_ENV/bin/python" --index-url https://pypi.org/simple -e './server-sdk[dev]' -e './client-sdk[dev,managed-agents]' build twine pre-commit 'pgserver==0.1.4'`
- `python -m pytest client-sdk/tests/test_providers/test_managed_import_boundary.py -q --disable-warnings`
- Scoped `ruff check` and `ruff format --check` over the four import-boundary files.
- `PATH="$SDK_VERIFY_ENV/bin:$PATH" bwrap --unshare-pid --bind / / --dev /dev --proc /proc make ci`
- From `client-sdk/`: `pytest tests/test_managed_agents.py tests/test_providers/test_managed_import_boundary.py -q`
- From `client-sdk/`: `pytest tests/integration/test_e2e.py -m integration -q`
- From `e2e/`, with existing Sandbox credentials loaded only into the child: `python -m pytest -m 'e2e and not e2e_slow' --ignore=test_managed_api_key.py -vv -ra`
- Focused actual-cloud replay after the reviewed test correction and invoking the candidate CLI with Node: `python -m pytest test_08_providers.py::test_alicloud_express_sdk_live test_08_providers.py::test_alicloud_express_cli_live -vv -ra -s`
- `python scripts/e2e-cleanup.py --run-id "$E2E_RUN_ID"` (dry run only), for each run; independent exact-ID GET and successful list readback followed.
- `python scripts/check_release.py candidate --tag v0.4.0a7` and `python scripts/check_release.py preflight` (read-only PyPI comparison, no upload).
- Fresh CPython 3.10.20 environment: install both final wheels with the managed extra, `uv pip check`, isolated import/exception identity and real SQLite transaction probes.
- `bash scripts/check-repo-health.sh --quiet`, `bash scripts/check-no-local-paths.sh`, `git diff --check`.

## Results

| Scenario / test | Result | Notes |
| --- | --- | --- |
| Import-boundary regression on original source | FAIL, expected | The real fresh process loaded managed application modules before the fix. |
| Import-boundary regression after correction | PASS | One test; same old/new error class, unchanged catch behavior/status/code/param/envelope. |
| Scoped Ruff and format | PASS | Four scoped files. |
| Initial namespace environment | FAIL, environmental | Reusing the host device mount prevented random initialization and access to the null device. It is not counted as a product pass. |
| Corrected namespace environment | PASS | An isolated device mount provides random/null access without changing host configuration. |
| First complete local CI attempt | FAIL | Server 875 passed/1 skipped; client mypy found nine errors in existing PostgreSQL kwargs and numeric return inference. The original failure remains recorded. |
| Final complete local CI | PASS | Server 875 passed/1 skipped; client 2426 passed/27 skipped/10 deselected. Both packages pass Ruff, format, mypy, build, twine, typed-marker and fresh combined-install checks. |
| Managed API focused regression | PASS | 41 tests, 24.92s; real SQLite/PostgreSQL, private bridge, public API and fresh provider import. |
| Integration-marked mock scenarios | PASS | All 10 tests, 2.74s; these are mock tests, not additional cloud evidence. |
| Initial real fast E2E | FAIL | 131 passed, 10 skipped, 2 deselected, 2 failed in 234.79s. Failures were the stale pause refusal assertion and a non-executable borrowed source CLI entry. |
| Reviewed real provider/CLI replay | PASS | Two tests, 32.88s, using `node` to launch the unchanged candidate CLI. The base pause HTTP 400 remains a recorded failed capability observation, not a pause pass. |
| E2E exclusions/skips | NOT VERIFIED | Management-key creation explicitly excluded from collection; it requires separate consent. Slow cases deselected. Missing optional providers, storage, eligible pause/Snapshot template and optional CLI-native entry account for the recorded skips. No skip is counted as a pass. |
| Independent cloud cleanup | PASS, observed scope | Both run-specific janitor dry runs list zero candidates. Independent exact GET confirms both recorded provider IDs absent; successful account listing returns zero sandboxes and zero matching run tags. No shared-tag deletion performed. |
| Frozen a7 package candidates | PASS | Four distributions pass twine; final CI rebuild is byte-identical to the frozen candidates used for downstream validation. Client requires server `==0.4.0a7`. |
| Fresh installed wheels, Python 3.10.20 | PASS | Dependency consistency, lower/old error identity, no upper application import from provider, real SQLite transaction and unchanged malformed-deadline rejection. This is a local wheel install, not a public PyPI install. |
| Release candidate/preflight | PASS | Correct tag and matching versions; no conflicting existing same-name artifact found by the release check. No artifact uploaded. |
| Repository gates | PASS with warning | Health: 106 PASS, 1 WARN, 0 FAIL; warning is the pre-existing missing maintainer release guide. Hygiene and diff checks pass. |
| Remote CI, public release/install, full managed FC deployment | PENDING | Coordinated as separate gates; source-only or general E2E success is not publication or FC qualification. |

### Frozen wheel identity

| Distribution | Version | SHA-256 |
| --- | --- | --- |
| `agent_sandbox_client-0.4.0a7-py3-none-any.whl` | 0.4.0a7 | `7b1d64f1b00dab453127f6d0c8450de75b90dfee55bf116761076e0d5cdaa4a9` |
| `agent_sandbox_server-0.4.0a7-py3-none-any.whl` | 0.4.0a7 | `a7787cd7632f771109cb08da6e71283a8500372c6d670537aab16cedf67ab185` |

### Release path reviewed, not executed

The existing publishing workflow runs the full CI, builds both packages, checks the exact tag,
rejects different bytes under an existing artifact name, uploads server before client and verifies
public metadata plus fresh installation afterward. It uses the protected `pypi` environment and
`PYPI_API_TOKEN`; it is not an OIDC upload. Manual dry-run is the default and requires the exact
`v0.4.0a7` tag. Publication, tag creation and merging were not performed by this verifier.

## Cleanup

The import regression creates only a bounded interpreter subprocess. Component tests use an
isolated PID namespace and own their temporary database/process teardown. No cloud resource is
created by the local unit checks. The separately authorized actual E2E uses only the existing
Sandbox API key and temporary sandbox resources. Private intent/logs remain on the local private
filesystem; the shared workspace does not provide Unix file-mode enforcement. Returned IDs and
run tags are not copied into public evidence. The suite's scoped finalizers ran, followed by
read-only janitor and independent cloud queries. No owned test process remains running.

The first independent probe used a nonexistent native `get_info` name and recorded `AttributeError`;
it was not treated as absence. The corrected public `get_info_by_id` query confirmed typed absence.

## Problems found

The native provider had an upper-layer import dependency. It is corrected without changing the
public error contract. Fresh dependency type failures and the outdated conditional pause assertion
were corrected after independent review. No performance conclusion is inferred from the import probe.

## Not verified

No new package has been published and no management key was created or renewed by this reviewer.
No OpenAI SDK interoperability claim is made. Remote CI, public installed-template model completion,
complete managed FC lifecycle and its own independent cleanup remain required. General sandbox E2E
does not substitute for those gates or for skipped conditional provider capabilities.
