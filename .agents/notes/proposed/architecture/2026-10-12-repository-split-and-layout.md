# Decision: Two-repository split (python-sdk + cli) and repository layout

Status: proposed

## Problem
The original single repository mixed the Python SDK, the Python server runtime, the Python CLI and the Node.js CLI
rewrite. Publishing it as two repositories needs one agreed answer for packaging, documentation ownership,
`.agents/` ownership, tooling and cross-repository links, otherwise pages are duplicated, ADRs dangle and local
paths leak into published files.

## Decision
The full review with measurements lives in
[`docs/en/design/repository-layout.md`](../../../../docs/en/design/repository-layout.md). Summary:

- Keep two PyPI distributions in this repository (`easy-sandbox`, `easy-sandbox-server`) sharing the
  `easy_sandbox` namespace; release them together as 0.3.0.
- This repository owns the contract pages (template.yaml spec, error codes, server HTTP API) and the ADRs that
  document SDK or server code. The Node.js CLI lives in `easy-sandbox/easy-sandbox`.
- `.agents/` is split by code ownership. Four ADRs moved here from the CLI repository
  (`transport-config`, `server-command-registry`, `custom-commands-schema`, `docker-builder-acr-push`).
- Cross-repository references are absolute `https://github.com/Easy-Sandbox/<repo>/blob/main/...` URLs.
- Repository tooling: `.editorconfig`, `CODEOWNERS`, a tooling-only root `pyproject.toml` / `ruff.toml`,
  `scripts/e2e/` for manual end-to-end scripts, `client-sdk/benchmarks/`.

## API Design
N/A — this decision does not involve API changes.

## Alternatives considered
- **Compat shim with a distinct `easy_sandbox_server` import package** — permanent shim and double module identity.
- **Single distribution with extras** — pulls the full client stack into every template image.
- **Umbrella monorepo** — couples release cycles of the Python SDK and the npm CLI for no gain.

## Dependencies
`scripts/check-repo-health.sh` (definition of done), GitHub repository rename `easy-sandbox` -> `python-sdk`.

## Test Strategy
`scripts/check-repo-health.sh --strict` in CI; per-package pytest and ruff stay unchanged.

## Acceptance criteria
- Health script exits 0 with `--strict`.
- No relative link leaves the repository; no dangling ADR slug; no machine-local path in tracked text.
