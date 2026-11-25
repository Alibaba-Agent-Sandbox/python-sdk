# Verification: Python0.5.0a1 release preflight

- Date:2026-11-25
- Issue:[186](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/186)
- Status:Candidate preparation; not a publication record.

## Source acceptance

PR185 head e4edd6fd7d6f8bd3c22bae92da64f4a6c7c075fe passed CI45593792026 and Docs45593792059 before ready/merge. Merge76f28aa8168c03833a83169eafe17df77865b518 was independently verified as merged. Both Python3.10/3.11/3.12 package matrices, build, pinned E2B contract, Python/Node provider engine and both public runtime fixtures passed. The scoped real Express HTTP cleanup and real pip-less inventory checks are recorded in their owning verification files.

## Version and distribution scope

Official PyPI JSON metadata reported both latest packages as0.5.0a0, each with two files;0.5.0a1 was absent. Candidate updates the two version sources, optional server exact pin, packaged READMEs and current bilingual installation/SDK guides. Historic evidence and template image pins remain unchanged.

## Required remaining gates

Local candidate/tag and distribution checks, exact-head release PR CI, existing tag-bound publication workflow, matching public artifacts and fresh client-only plus optional-server readback. The publish workflow validates the tag, preserves the built artifacts, checks existing hashes, uploads server then client and performs public metadata/install verification. No credential value is recorded or changed here.

## Final documentation cross-review

The Python MCP tool catalog and dispatch contain no `submit_template_build` or `envd_inject` input. The CLI MCP correction belongs in its owning repository; no Python runtime feature was invented or removed. Current bilingual conditional-acceptance examples now omit the misleading `envd_inject:false` input rather than implying it disables cloud injection. Background-task guides describe Python-specific parameters without falsely claiming the CLI lacks similarly named tools; CLI `src/agent/operations.ts` independently declares all three tools with different inputs. Historical evidence is preserved.

## Local candidate verification

Candidate/tag equality and PyPI-absence preflight passed. Paired wheel/sdist build, twine/typing metadata checks and fresh client-only/optional-server installs passed. Lint, type checks and format checks passed for both packages; repository health passed; bilingual doc health reported106pass,1existingwarning,0fail. Initial packaging tests skipped the wheel-build case because the test environment lacked hatchling; installed the project build backend and reran those checks rather than counting the skip as a pass.

Separate package invocations passed20client packaging/release checks and5server packaging checks after the build backend was installed. A combined pytest invocation first failed collection because both package suites own a `tests.conftest` module; rerunning separately follows the repository's normal package isolation. The repository health script is the existing document/link checker; its actual106/1/0 result is retained.
