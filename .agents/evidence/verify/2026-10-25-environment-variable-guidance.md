# Verification: Environment-variable guidance

- Date: 2026-10-25
- Result: PARTIAL — local document checks and actual-public-interface/local-HTTP
  checks pass; latest full PR CI and normal review/merge remain pending.
- Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/135
- Baseline: source `676ef0483706a2b1af717db8d6d08f19acd8d804`, public
  client/server0.4.0a6 and official standaloneCLI0.5.6, Python3.13.
- Scope: two bilingual environment guides and their engineering/changelog records;
  no source, docstring, package metadata, historical command-map or cloud change.

## Confirmed documentation errors

Official `abx --provider alicloud-express create --help` exposes a positional
platform template and describes `--env` as terminal-session configuration. Its
current dispatcher rejects the former `--template` example before any cloud
call. The standard create implementation passes env only to the terminal; the
detached create request does not receive it as creation envs.

Actual public SDK inspection confirms asynchronous ProviderSandbox.create,
run_code and run; synchronous root Sandbox.create; and real NetworkModule.get_url
and get_access_headers. Interpreter execution separately requires the selected
provider's declared operation. ServerClient.system.env(names) and
set_env(variables) use authenticated application transport. ExecProvider still
sends resolved config through EPP initialize and starts with an allowlisted
process environment plus optional explicitly declared passthrough.

## Local execution

- Both guides' Python blocks compile with top-level-await support: PASS.
- Actual official public SDK6 imports/signatures and local synthetic auth-header
  and exec-environment helpers: PASS; no network or provider lifecycle.
- First local HTTP attempt: FAIL before readiness. The initial health probe
  raised RemoteProtocolError (server disconnected without a response). Finally
  invoked owned subprocess terminate/wait. No environment-method PASS or host
  root cause is inferred; this attempt did not persist an independent absence
  receipt. A later run, if any, receives a separate result.
- A separately recorded local HTTP repeat: PASS. The same ten-second readiness
  budget encountered two pre-ready protocol resets; only pre-ready health probes
  retried. After readiness, typed GET/set/readback, wrong-application-token
  rejection, secret-name filtering and unchanged parent environment all passed
  without API retries. Owned local subprocess absence was independently checked.
- Local links, `git diff --check`, `make hygiene`: PASS.
- `bash scripts/check-repo-health.sh --quiet`: PASS106/WARN1/FAIL0 (existing
  missing maintainer release-guide warning).
- Public SDK imports and ten Python blocks in each translation compile: PASS.
- Local full make-ci was not run: this environment has no ruff/mypy/pytest and
  this scoped docs task does not install new dependencies. Normal full thirteen
  SDK PR checks remain required; local snippets do not replace that matrix.

Safe scope-specific receipts:
[initial startup failure](2026-10-25-environment-variable-local-initial-failure.json)
and [later actual local HTTP](2026-10-25-environment-variable-local-http.json).
The later local HTTP run uses the published ServerClient against a real local
server. It does not claim a cloud ProviderSandbox lifecycle or new provider
application-endpoint verification.

## Boundaries

No new cloud resource was created for this documentation fix. Existing bounded
platform environment observations remain in their owning template record and
are not copied here as a new SDK runtime or all-provider verification. The
public package stays0.4.0a6; no SDKa7 or additional runtime guarantee is claimed.
