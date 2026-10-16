# Decision: Validate stacked pull requests with the complete CI workflow

Status: proposed

## Problem

The main CI workflow listens only to pull requests targeting `main`. PR #33
targets a feature branch and has only a Markdown check, leaving the product matrix
unexecuted. See [issue #37](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/37).

## Decision

Remove only the `pull_request.branches` filter from `.github/workflows/ci.yml`.
Keep push filtering, job definitions, matrix versions and all assertions unchanged.
Document the latest-head requirement in English and Chinese contributor guidance.

## API Design

N/A — this decision does not involve API changes.

## Alternatives considered

- Retarget stacked work to `main` prematurely: rejected because it obscures dependency ordering.
- Treat Markdown success as full validation: rejected because no product jobs ran.

## Dependencies

Existing GitHub Actions CI jobs and the already authorized contribution branches.
No cloud credentials are supplied to these workflows.

## Test Strategy

Parse the workflow, verify unrestricted pull-request selection and unchanged main-only
push selection, compare all jobs to the previous revision, run hygiene and health
checks, then inspect actual latest-head GitHub Actions results. Real-cloud lifecycle
evidence remains separate and does not replace missing matrix jobs.

## Acceptance criteria

- Pull requests against feature branches start the full existing matrix.
- Main-only push selection and existing CI jobs remain unchanged.
- Actual latest-head results and remaining product gates are recorded honestly.

## Evidence

- [Verification](../../../evidence/verify/2026-10-16-stacked-pr-ci.md)
