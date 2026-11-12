# Verification: managed Agent input contract

- Date: 2026-11-12
- Base revision: a9a572d81847fe99216bf1bb454b91810dacc676
- Branch: feat/agents-api-contract-20261112
- Owner issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/162
- Delivery tracker: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309
- Result: PARTIAL
- Environment: Linux, Python3.11.15; matching local client/server0.4.0a7 source candidates in an isolated virtual environment. No cloud/model credentials loaded by these checks. Local PostgreSQL uses pgserver0.1.4 with psycopg/psycopg-binary3.3.2.

## What was verified

The managed Gateway accepts the optional message discriminator, uses supplied saved Agent
IDs without coercion or truthiness fallback, preserves saved-plus-inline overrides, and
distinguishes429/503 error categories. This is a bounded API correction, not the complete
YAML migration, new adapter support or an OpenAI SDK compatibility claim.

## Commands run

- `python -m pytest client-sdk/tests/test_managed_agents.py -q -k 'typed_user_message or invalid_typed_input or saved_agent_overrides or explicit_agent_id or managed_error_types'`
  before production edits: exit1,10 failed/5 passed/52 deselected. Failures reproduce typed
  message rejection, empty/non-string ID fallback/coercion and429/503 category behavior.
- The same command after the correction: exit0,15 passed/52 deselected.
- With `or real_http_typed_message` added: exit0,16 passed/52 deselected. The added case uses
  a real local HTTP listener, actual quota admission, and a deliberately failing dependency
  to prove safe503 serialization; it is not a live cloud service failure test.
- `make test`: initial exit2 in the Server package,874 passed/1 skipped/1 failed. The failing
  `test_pip_returns_structure` found no installed packages because this uv-created environment
  lacked pip; Make stopped before the Client package. Installed pip26.1.1 and re-ran that
  exact case: exit0,1 passed. No product workaround was added.
- Installed optional pgserver0.1.4 and matching psycopg3.3.2, then parameterized typed-input
  and saved-override regressions over SQLite and actual temporary PostgreSQL. The focused
  four-case selection passed, exit0; fixtures shut down their temporary databases.
- `make test` after environment preparation: exit0; Server875 passed/1 skipped, Client2483
  passed/27 skipped. These counts are separate package runs, not cloud/model acceptance.
- `make lint`, `make typecheck`, `make format-check`, `make hygiene`: each exit0 for both packages.
- `make ci`: exit0; Server875 passed/1 skipped, Client2473 passed/27 skipped/10 deselected;
  hygiene, lint, format, typecheck, both wheel/sdist builds, twine checks, py.typed markers,
  clean client-only HTTP and optional-server combined installation passed. This is one
  Python3.11 interpreter, not the remote3.10/3.11/3.12 matrix.
- The full runs skipped the packaging modules because hatchling was absent from the test
  environment (isolated builds had their own backend). Installed the build's actual
  hatchling1.33.0 and ran each `tests/test_packaging.py` separately: Server5 passed, Client7
  passed, both exit0. No full suite was rerun solely to change skip counts.
- `bash scripts/check-repo-health.sh --quiet`: exit0,106 passes/1 existing recommended
  release-runbook warning/0 failures, including a final repeat after the result update.
- `make hygiene`, `git diff --check`, and staged `git diff --cached --check`: final exit0.
- `bash .githooks/check-secrets.sh`: exit0 against the ten explicitly staged scoped files;
  no sensitive information found. The follow-up instance design is outside this patch.

## Results

Input/ID/error regressions and required single-interpreter local gates PASS. Existing saved configuration
overrides were retained; missing/foreign nonempty saved IDs already returned404 before this
change. The newly corrected false-like fallback includes the empty string; its lookup now404.
Unknown input types/images/roles and the original text budget still reject atomically.

The remaining26 Client skips require an explicitly configured compatible Node engine command,
the legacy CLI sibling fixture location, or Node CLI/provider source/dependency prerequisites.
They are reported as skips rather than passes. The two packaging module skips in the full
runs were resolved by the separate12-test packaging run above. Remote matrix, cloud/model
E2E and publication are independent incomplete gates, so the overall result remains PARTIAL.

## Cleanup

Local test HTTP listeners close and threads join in finally. The selected regressions create
only temporary SQLite/PostgreSQL records and fixture directories; no cloud/model resources were created.
This is not an account-wide resource inventory.

## Problems found

An initial mutual-exclusion hypothesis was rejected by the current official Create Session
reference before implementation: saved Agent plus inline overrides are supported. The patch
does not introduce that incorrect restriction. Other HTTP error categories were deliberately
not inferred from SDK exception names or a stale local mapping.

One exploratory pytest command combined both packages and hit their same-named
`tests.conftest` modules (exit4). It was corrected to separate package commands, as the
Makefile does; this was a test invocation error, not a product failure.

## Not verified

Real cloud/model E2E, complete YAML migration, official SDK interoperability, remote CI/review,
PR merge and publication have not been completed by this patch. The decision remains proposed.
