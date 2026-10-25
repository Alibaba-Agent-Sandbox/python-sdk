# Verification: 0.4.0a1 publication preflight

- Date: 2026-10-25
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/108
- Result: PASS for the read-only preflight; no merge, tag creation or publication.

At the time of this check, PR 108 was draft/open and mergeable without conflicts.
Its head `14fad5c4a37ec01e41f859ea318f27353faf6421` passed all 11 remote CI jobs.
Both public PyPI version endpoints for client/server 0.4.0a1 returned HTTP 404,
as did the remote `v0.4.0a1` tag and GitHub release endpoints. This records absence
at inspection time, not a claim about subsequent availability.

`python scripts/check_release.py candidate --tag v0.4.0a1` passed. Both package
versions and the required client dependency on the server are 0.4.0a1. The repository
has the `PYPI_API_TOKEN` Actions secret name configured; its value was not read or
printed, and this check does not establish its upload validity. The `pypi`
environment reported no protection rules. No publication credential was copied.

The publication procedure remains the existing one in CONTRIBUTING: after merge
and required checks, bind an immutable matching tag; run tag CI; build and preserve
four artifacts; verify their metadata, installation and any existing public hashes;
upload server before client; verify public hashes and a fresh exact-version client
installation with the matching server dependency. A GitHub prerelease triggers the
existing release workflow; manual tag runs default to dry-run.

The current English and Chinese installation guides now state the matching package
requirements without the time-sensitive claim that the version is unpublished.
Both specify CLI 0.5.0 for specification 5 template launch; the Chinese page's stale
0.4.16 reference was corrected. Source-checkout installation remains available.
Package README installation commands do not pin an obsolete release. Historical
verification records were not rewritten.

Documentation checks: repository health 106 passes / 1 warning / 0 failures;
local-path/credential hygiene and whitespace checks passed. The new documentation
head still requires its own remote checks. No unrelated cloud tests were repeated.
The unexplained extra full CLI run remains tracked separately in
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/109; the focused file
check and unified-template startup passes do not erase that history.
