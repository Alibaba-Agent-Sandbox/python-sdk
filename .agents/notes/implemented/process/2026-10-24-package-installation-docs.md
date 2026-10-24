# Decision: Keep packaged installation guidance accurate

Status: implemented

## Problem

The package READMEs and installation guide still instructed users to install 0.3.1a2 and described publication as pending. A new wheel would carry these obsolete instructions into its PyPI description even if the website were corrected.

## Decision

Use an explicit prerelease opt-in command in package and root READMEs, and a fixed current version in the bilingual installation guide. Start the guide with public package installation; put development checkout instructions later and move publication mechanics into CONTRIBUTING. Keep the exact client/server dependency.

Stop the a4 publication before upload and preserve its tag. Package the corrected descriptions as matching 0.3.1a5 distributions; do not replace existing version contents. No application runtime behavior changes from a4.

## API Design

No public API change. The local client and server distributions remain versioned in lockstep.

## Alternatives considered

- Correct only the website: leaves obsolete commands in PyPI descriptions.
- Move the a4 tag or upload modified artifacts under it: breaks the tag-to-artifact relationship.
- Keep publication and verification state prose in the installation path: makes ordinary installation needlessly confusing.

## Dependencies

Existing package READMEs, release validator, build pipeline and exact same-version dependency.

## Test Strategy

Run package/release regressions and build/dist-check. Inspect the wheel metadata and source archive README for both distributions. Require full current-head CI, then verify public artifact digests, a fresh exact-version install, imports and pip check. Existing real proxy evidence applies to unchanged runtime code; final public-package template acceptance remains separately recorded.

## Acceptance criteria

- Both built descriptions give accurate installation commands.
- Bilingual guides use the public pair with no stale candidate state prose.
- a4 tag remains unchanged and no a4 upload occurred.
- a5 public distribution readback and fresh installation succeed.

## Evidence

- [Issue #101](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/101)
- [Local packaging and stopped upload](../../../evidence/verify/2026-10-24-package-installation-docs.md)
- [Public a5 release and clean installation](../../../evidence/verify/2026-10-24-python-a5-public-release.md)
