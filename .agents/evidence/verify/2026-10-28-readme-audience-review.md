# Verification: python-sdk README audience review

- Date: 2026-10-28
- Result: PASS — scoped local documentation verification. Remote checks and merge are reported separately on the PR.
- Base revision: `9fdeef5adeb22f64375ee29d04b54b206686347a`.
- Scope: `README.md`, `README.zh-CN.md`; repository-owned note and this evidence.
- Environment: Linux, Node.js 22.22.2, system Python 3.13.13; SDK/server and checker environment Python 3.11.15.

## What was reviewed

The opening mixed standard clients, provider internals, server packaging, migration and build details. A large architecture diagram and repeated documentation indexes obscured which Python client a reader should import.

Lead with Python use cases, installation and one interpreter example with deletion in finally. Explain Sandbox, AsyncSandbox, code_interpreter and ProviderSandbox in a small selection table. Link provider/template, server, authentication and migration guides. Keep client/server package ownership visible without namespace implementation details.

## Validation

`python "$README_AUDIT"` passed for 6 changed Markdown files, with zero failures. This temporary audit used the existing template repository's Markdown-target/heading parser at its checked-out base revision and a task wrapper (SHA-256 `fe8c34fd4ef2474ca7dfcfcc94d2a055e9ead01a92fe2695446cfe08341df7e6`). It checks changed local targets/fragments, incoming active README heading links, one H1 and reciprocal language links in each root README, balanced fences and Python snippet syntax. `README_AUDIT` denotes that temporary wrapper; no machine-local path is part of the repository. It does not validate cloud runtime behavior.

`git -c core.filemode=false diff --check HEAD` passed. The filesystem exposes executable bits on unchanged checkout files; ignoring those bits for task-local Git commands avoided including unrelated mode changes. The staged change was reviewed for prose-only scope, translation equivalence, current command/API names and preserved license links. Package registry checks on 2026-10-28 found CLI 0.5.8 and Python client 0.4.0a6; the Node SDK public npm metadata endpoint returned HTTP 404. No new package publication is claimed.

## Limits and cleanup

Documentation changes only. No provider API calls, sandboxes, templates, cloud keys, model calls, deployments or package releases were created by local verification. Existing historical receipts remain unchanged. CI and existing main-branch publication workflows retain their own scope.

## Repository checks

- `bash scripts/check-repo-health.sh`: PASS: 106 checks, 0 failures; 1 warning.
- `make hygiene`: PASS.
- `make test`: PARTIAL: server suite 872 passed, 1 skipped, 3 failed; make stopped before client suite.
- `pytest (three failed server tests after installing missing pip in the test environment)`: PARTIAL: package-list test now passes; malformed WebSocket and chunked-request tests still receive HTTP 501/502 instead of 400.
- `pytest tests/ (client-sdk)`: PASS: 2348 passed, 27 skipped.
- `make lint typecheck`: PASS: Ruff checks passed for both packages; mypy passed for 56 server and 101 client source files (one unused-section configuration note).

## Reviewed public-file identity

| File | SHA-256 |
| --- | --- |
| `CHANGELOG.md` | `f412ce3f97945f2bf7ea93da3b5cc1a05844a937cd2da362054228df5d408a66` |
| `README.md` | `fafd9d8ccf215f639cad22d099670e2be2063f430c09b0b2b8da7af2dd5ca584` |
| `README.zh-CN.md` | `2983f3a8cab891379e1a5f6ae60928f92ab9f7fd6b07b6f6626e95e9ee97ea76` |

## Final local review follow-up

The two raw HTTP server tests still fail locally with HTTP 501/502 instead of 400 after the missing-pip prerequisite was fixed. Their executable source is unchanged by this documentation PR. The reason for those responses is not established. The PR must pass the complete current-head remote matrix before merge; no local server-suite pass is claimed. The changelog entry was folded into the existing Unreleased/Changed group during review.
