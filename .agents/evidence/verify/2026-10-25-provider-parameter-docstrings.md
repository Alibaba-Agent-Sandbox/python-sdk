# Provider lifecycle parameter documentation verification

Date: 2026-10-25
Result: PARTIAL (candidate checks; publication and final delivery pending)

Base: main 53956043008d0658340448c97fcb453387da62d1. Issue:
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/124.
Candidate client/server 0.4.0a4; not yet public. Current public install recipes
remain a3. No old publication evidence was edited.

## Actual scope

Fresh installed public a3 exposed four stale original lifecycle docstrings and
four copied synchronous docstrings. create/connect/list documented removed
api_key/api_url (and domain on create/connect); kill_by_id additionally listed
sandbox_domain absent from its actual signature. No compatibility behavior exists.
get_info_by_id/set_timeout_by_id themselves list no stale parameters, but refer
to kill_by_id for override help.

Candidate introspection: all 12 create/connect/list/kill/info/timeout async/sync
signatures equal the public-a3 signatures; all documented argument names match
those signatures. All 24 actual calls with retired api_key/api_url/domain fail
with TypeError before any coroutine/provider/network request. The standard
ApiParams contract still contains all three valid standard-client names.
Executable AST of api/sandbox.py equals the base after removing docstrings.
[Sanitized contract receipt](2026-10-25-provider-parameter-docstrings.json).

## Checks

- New signature/help regression: 12 PASS.
- Focused lifecycle, standard-contract and documentation suite: 101 PASS.
- Both packages lint, format and mypy: PASS.
- Full client `pytest tests -m "not integration"`: 2277 PASS, 26 SKIP, 10 deselected.
- Full server: 878 PASS, 2 FAIL. The same previously observed local raw-HTTP
  expectations fail: Responses WebSocket upgrade without a key returns 501 rather
  than 400; policy Transfer-Encoding framing returns 502 rather than 400.
  No assertion was weakened and no server executable statement changed. Required
  remote Python 3.10/3.11/3.12 matrices must independently pass before merge.
- Four candidate wheel/sdist builds, `make dist-check`, fresh combined-wheel
  installation/imports and pip check: PASS. A uv-created runtime environment
  initially had no pip module; seeding pip fixed that tooling prerequisite.
- Real HTTP from the installed candidate wheels: health, authenticated shell
  result 4, file round-trip and owned server SIGTERM -15: PASS. Exact owned PID
  independently absent. [Local HTTP receipt](2026-10-25-provider-parameter-docstrings-wheel-http.json).
- Document/record health: 106 PASS, one warning, zero failures; hygiene and diff
  checks: PASS.
- Exact latest-head 13-check CI, independent review, normal merge and immutable
  a4 publication/official fresh install: pending.

This change does not alter provider/server behavior or the readiness fix. No new
cloud resources/model calls were created for docstrings; existing real Docker
fixture jobs remain required owner gates. Earlier real public-a3 cloud results
retain their original version scope and do not become a4 evidence.
