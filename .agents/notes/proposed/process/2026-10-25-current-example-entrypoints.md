# Decision: Use current public package entry points throughout the examples
Status: proposed

## Problem

Fresh public client/server 0.4.0a1 installation exposed old keyword arguments,
source-path injection, retired HTTP routes and scripts that printed failures but
returned success. The former capability script mixed obsolete installation paths
with cloud fallback claims. Local agent protocol fixtures were also confused with
real model execution.

## Decision

Use current `ProviderSandbox` and decorator arguments consistently. Keep the
standard E2B import-migration example explicitly separate because it demonstrates
an external API migration, not a retired project API. Remove source-path injection,
old request routes, simulated model fallback and swallowed failures. Run local
examples with the installed public runtime. Start the HTTP quickstart directly
with Node on `base`; reduce the capability example to observable SDK operations.
Use real Chromium with an owned HTTP page by default and an explicit optional
external target. Record model calls and controlled protocol fixtures separately.
Bump both Python distributions from 0.4.0a1 to 0.4.0a2 in lockstep.

## API Design

No SDK public API is added or changed. Examples use `sandbox_api_key` and
`ABX_SANDBOX_API_KEY`; the standard-client migration example documents its E2B
configuration names. The E2B provider verifier uses its actual documented
`ABX_E2B_API_KEY`, without accepting the erroneous doubled-prefix name.

## Alternatives considered

- Retain keyword aliases or catch-and-fallback code: rejected; these project
  examples have not been released as a stable compatibility contract.
- Install source silently while claiming a public-package run: rejected.
- Introduce a new general scenario framework: rejected; keep executable examples
  and the existing local runner, plus ordinary cloud commands in the guide.

## Dependencies

Published paired Python packages, Express account, public CLI for CLI verification,
package/browser download access, and an explicitly supplied model account for the
real code-generation example. No credentials are committed or newly uploaded.

## Test Strategy

Execute all twenty client entry points in their actual local/cloud scopes. Test
real local HTTP/session/process behavior separately from real model generation.
Assert business values, binary equality, browser artifacts and command failures;
independently verify absence of owned cloud resources. Run owner CI, health,
hygiene, package checks and the real-cloud suite. After publishing, repeat from a
fresh exact-version public installation; candidate passes do not prove publication.

## Acceptance criteria

- Current examples, guides and configuration names agree without old aliases.
- All intended client/server/fixture entry points have explicit executed evidence.
- Required CI and real-component gates pass, with failures and skips retained.
- Both 0.4.0a2 distributions are published and installed together from PyPI;
  released examples are rerun from the public installation.

## Evidence

- [Current example verification](../../../evidence/verify/2026-10-25-current-example-entrypoints.md)
- [Issue 111](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/111)
