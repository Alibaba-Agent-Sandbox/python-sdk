# Decision: Synchronize maintained guidance with verified public a3

Status: implemented

## Problem

The readiness fix is now public as client/server 0.4.0a3, while current installation
pages, skills and offline fixture recipes still select a2. The primary engineering
record entry also starts with an older publication checkpoint.

## Decision

Update maintained installation examples to exact public a3 with official PyPI.
Use that same server version in both SDK fixture Dockerfiles and their existing
actual guest-version CI assertion. Add the completed release/public-cloud receipt
as a new record and primary navigation entry; preserve earlier evidence verbatim.

## API Design

No runtime/API, aliases, exports, schema or package-version changes. The decorator
example changes only its installation docstring. This does not rebuild the already
published a3 artifacts or make a new SDK release necessary.

## Alternatives considered

Recommending unpublished packages was avoided by waiting for actual publication,
four-file verification and a fresh installation. Replacing historical receipts
would lose their exact-version scope. Adding another installer path is unnecessary.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/122
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a3
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40209677091

## Test Strategy

Verify the four preserved/public hashes and actual fresh official-index imports;
run unchanged real-cloud readiness scenarios and independently confirm cleanup.
Run document/record checks, then the existing owner CI including both real Docker
fixture builds, actual guest a3 and application HTTP/cleanup checks.

## Acceptance criteria

All maintained installation pins select public a3; historical records and synthetic
release-validator fixtures remain historical/test data. Normal owner checks,
latest-head CI, independent review and verified merge complete. The broader browser
example Issue 111 is not closed by this documentation follow-up.

[Verification](../../../evidence/verify/2026-10-25-public-a3-docs.md).

## Implementation

PR 123 merged at 53956043008d0658340448c97fcb453387da62d1 after all 13 checks and independent review. Its public-a3 install/fixture criteria were delivered. Current guidance subsequently advances to public a4; the a3 evidence retains its original version scope.
