# Decision: Build SDK fixtures with the published server runtime
Status: proposed

## Problem

Both offline fixture Dockerfiles require local wheel files before their shell
fallback could run. The fallback installs an unversioned server. Neither behavior
matches the documented public-package path. The agents fixture README also
incorrectly describes omitted-adapter requests as HTTP 400 rather than 200/default.

## Decision

Install the exact public server 0.4.0a2 from the official PyPI index in both images.
Remove the wheel COPY and fallback entirely. Correct the README and retain the
explicit offline-fixture and real-model prerequisites. Build both unmodified
Dockerfiles in the existing CI, check their actual guest runtime version and
HTTP application, then remove and independently confirm absence of owned containers.

## API Design

No product API, package version or source-fallback compatibility is added. Python
hello still serves its registered command; agents-cli still requires installed
real agent CLIs and model credentials for actual model execution.

## Alternatives considered

Supplying candidate wheels or manufacturing empty files preserves an unnecessary
second installation path. Merely checking Dockerfile text does not prove the build.
A new test framework or cloud service is unnecessary; use existing Docker CI.

## Dependencies

Docker, the existing public base images and the official PyPI server 0.4.0a2.
No cloud/model credentials or provider account are needed.

## Test Strategy

Run the actual Docker builds, verify package imports/version inside each image,
start the image unchanged and check health plus hello command or agents runtime
listing. Use owned container cleanup even on failure. The smoke does not claim
real Codex/Qwen model execution. Run owner health/hygiene and required CI.

## Acceptance criteria

- Both fixture images build without a local wheel or source fallback.
- Actual guest package is 0.4.0a2; expected HTTP behavior passes.
- Owned containers are removed and confirmed absent, including after failures.
- README accurately distinguishes protocol fixtures from actual agent execution.

## Evidence

- [Verification](../../../evidence/verify/2026-10-25-public-runtime-fixture-images.md)
