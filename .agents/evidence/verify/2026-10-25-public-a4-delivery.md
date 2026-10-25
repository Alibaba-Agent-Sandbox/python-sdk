# Public a4 delivery and current guidance verification

Date: 2026-10-25
Result: PASS for immutable publication and actual public-package verification;
current guidance/metadata-window source delivery remains under review.

Base: merged PR 125, 100da4661809f91a5d50e2722d1f4a8d4da3b131. Annotated tag
v0.4.0a4 resolves to this source, whose tree equals independently reviewed 5b91f5d.
All 13 exact-head owner checks passed before normal merge. No new SDK runtime or
version change is made here. [Sanitized delivery receipt](2026-10-25-public-a4-delivery.json).

## Publication and retained failure

Run 40215483508 attempt 1: FAIL after successful uploads, at metadata verification.
Six probes from 17:21:19 to 17:22:09 UTC returned metadata HTTP404/exit75; the fresh
installation step was not reached. This is six probes over about 50 seconds,
not six separate 50-second waits. No checksum mismatch was observed. The precise
cache layer or first moment of global visibility is not established.

Later canonical official metadata returned 200 for both packages. Original
publisher artifact 12608120413, both public metadata records and all four actual
public downloads matched. A normal failed-job rerun on the same immutable tag
completed SUCCESS on attempt 2, skipping all four already-existing files.
Its preserved artifact 12608106130 contains the same four hashes as the original.
The original failure/log/artifact remain preserved, not upgraded to a pass.

## Actual public installation and behavior

A new ordinary Python 3.13 venv, new HOME and working directory outside Git ran
`python -m pip install --no-cache-dir --index-url https://pypi.org/simple agent-sandbox-client==0.4.0a4`.
Matching server a4 installed automatically; pip check and standard sync/async,
ProviderSandbox and server imports passed from the fresh environment. No
PYTHONPATH or source package was injected.

All 12 lifecycle async/sync docstrings matched unchanged signatures. All 24 actual
retired-keyword calls rejected before any network request. Installed provider API
bytes equal the reviewed source; standard ApiParams remain valid and unchanged.
Real public-package HTTP health, authenticated shell result 4 and file round-trip
passed. The owned server exited after SIGTERM (-15); its exact PID was independently
confirmed absent. No cloud sandbox or real model call was created for this prose fix.
Earlier cloud/catalog evidence remains scoped to its actual versions.

## Follow-up source verification

- Maintained install/skill/fixture pins now use exact public a4, official index intact.
- Existing release shell regression: 13 PASS, including propagation beyond the old
  six-probe boundary, 18-probe exhaustion, HTTP401/hard failures, unchanged six
  installation attempts and single pip-check/import verification.
- Current metadata window has 17 ten-second intervals (170s); it remains a finite
  allowance, not a guaranteed PyPI propagation deadline. Immutable v0.4.0a4 used
  the old six-probe workflow and is unchanged.
- Both-package lint, format and mypy: PASS. Release/docstring focused suite: 25
  PASS. Health: 106 PASS, one warning, zero failures; hygiene/diff checks: PASS.
  Decorator example executable AST is unchanged; only its install docstring moves
  to a4. No published artifact is rebuilt by this documentation commit.
- Exact latest-head CI and independent review remain delivery gates. Both real
  public-a4 Docker fixture jobs remain required; no local Docker is available.

Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/126.
