# Verification: Final provider convergence after concurrent branch updates

- Date: 2026-10-18
- Result: PASS for convergence regressions, packaging and tested real Express behavior. Latest-head hosted checks remain a separate mandatory merge gate.
- Scope: ordinary branch merge on `8a4c76c7dfaae9e9824c032a5d1683a001c612da` plus the accompanying owned metadata/configuration changes. Source/test snapshot: 233 files, SHA256 `00641b9b5f03b39e43299f1572ac165f6337d55a68890d0fd8065ae6841962bd`.
- Delivery: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/35 and https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/38.
- Environment: same locked Linux/Node22/Python3.11 environment as the [earlier acceptance](2026-10-18-provider-isolation-acceptance.md). Secrets remain private; no cloud identifiers are published.

## Integration and ownership

A final record push was rejected because another contribution had advanced the shared
branch. Ordinary merges retain those commits, including the provider-owned Docker RUN
rewrite, authentication preflight, canonical auth exports, current native HTTP lifecycle
and independent engineering records. No force push or shared-history replacement occurred.

The integration had reintroduced wire URL formatting and Express configuration/profile
data into lower utility implementations. The accompanying reconciliation keeps pure data
inside the Express provider; lower utility paths are compatibility exports and generic
distribution composition. Historical URL helpers delegate to owned factories or provider
declared templates. The explicitly selected shared E2B adapter owns its own wire builder.
Neutral image profile types are defined in the CLI model layer and re-exported from the
historical provider path; lower configuration does not import higher runtime types.

A behavioral regression replaces the compatibility URL rule with an opaque provider-owned
path and proves the public helpers honor it, including literal dollar characters. Fresh
neutral Python import and async-only provider refusal regressions remain passing.

## Executed verification

- Merged Python full client: **2178 passed, 24 skipped**, 150.25 seconds. The appended owned-builder regression then passed in the **9-pass** isolation file; **40-pass** volume/isolation run also passed.
- Python package-scoped ruff/format/mypy: PASS, **104 client / 56 server** modules. Wheel/sdist build, twine, py.typed and combined clean install/import: PASS.
- CLI strict typecheck/build: PASS; ESLint zero errors, 250 warnings. Fresh convergence suite: **90 passed** across six actual collected files, including wheel structure, auth preflight, provider boundaries and command regressions.
- CLI final local aggregate: **3924 passed, 21 failed, 2 skipped**. Twenty failures reproduce the previously disclosed network-intermediary baseline. One extra failure was a test reading a compiled entry while a concurrent build removed it. Sequential build then the affected suite passed; the 90-pass convergence run includes this repair. This artifact race is not called a product or environment failure.
- CLI parity ledger: **907 passed, zero failed/skipped/missing**, 11 previously moved SDK entries reported separately.
- New CLI evidence capture: **114 cases, zero skipped, 17 documents**. Historical captures remain unchanged.
- Standalone build/version smoke: PASS; final executable SHA256 `b5b9fea2b33ca167424bb0d59c90ce6cbd62f0f7ca64c4f19a1cc9e5e1f7dca5`. Moving type-only declarations did not change the executable digest.
- npm10 dry-run content validation and both-owner health/hygiene are rerun with this commit; exact outcomes are exposed by its required checks.

## Real Express rerun

The merged Python source ran the published platform/lifecycle/commands/files/network/code
E2E files: **58 passed, 1 known xfailed, 1 non-strict xpassed** in 106.20 seconds. The xpass
is KI-008: a one-megabyte upload completed within the existing timeout in this run. It is
network dependent; no timeout changed. KI-009 still records the unavailable native Jupyter
trailing-expression behavior. The earlier 116-pass full run and fresh 2-pass OSS persistence
run remain separate evidence at their exact tested revisions, not relabeled as new runs.

The merged executable cloud/management scenarios all passed, including real process info
and metrics; **two created sandboxes, zero leaked**. The combined run was **142 pass / 2 fail /
1 guarded skip** because another branch retained older Commander-error expectations while
the actual converter preserved the public `not one of` wording. The corrected assertions
require the complete emitted error, all permitted choices and exit2. Fresh offline rerun:
**61 pass / 1 no-resource leak-check skip**. Production parsing and snapshots were not relaxed.

## Checkpoint failures and cleanup

The first focused Python run exposed an ignored retired-engine bytecode directory as a
namespace package (66 pass / 1 fail); a second probe before cleanup had39 pass /1 fail.
Only obsolete ignored `.pyc` files were moved to a task-private temporary backup. No source,
test assertion or user output file was deleted. The unchanged retired-engine regression
then passed, as did the full client aggregate. A first cross-filesystem rename failed
before mutation; the subsequent guarded move succeeded.

An independent current SDK query after all cloud reruns confirms no sandbox resources
remain. Storage/key/Volume/Bucket/policy/role deletion and not-found recovery from the earlier
same-day storage run are preserved in its immutable evidence. No new storage or key was
created by this convergence smoke. The pre-existing untracked server output remains untouched.

## Remaining scope

Latest-head hosted checks and mergeability must be inspected before merging. No required
review/check bypass or package publication is authorized by a local pass. Native E2B, Cube,
container and OpenSandbox prerequisites remain absent; optional native image factories stay
unactivated. This record does not claim all providers or all platform capabilities are live-tested.
