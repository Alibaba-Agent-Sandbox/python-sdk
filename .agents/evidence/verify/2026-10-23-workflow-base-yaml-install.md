# Verification: workflow YAML belongs to the base installation

Date: 2026-10-23. Result: PASS for corrected distribution installation; prepared-image Docker rerun remains required.

Real OpenSandbox [run39940863279](https://github.com/alibaba-agent-sandbox/awesome-providers/actions/runs/39940863279), job120371660728, reproduced a product installation defect. Portable source preparation/build/push, owned sandbox readiness, CLI named-command hello and Python connect/application_client hello passed. `launch_workflow(manifest_path)` then failed with ModuleNotFoundError for yaml because the base client did not install its path parser. Cleanup succeeded. This is not an upstream OpenSandbox capability failure.

Move pyyaml>=6.0.3 from the declarative extra into required client dependencies. A YAML path is a documented core workflow input, so requiring users to add an unrelated extra would hide the defect. Delete the resulting empty extra and remove it from all; do not preserve a compatibility shell. Update bilingual installation guidance and the decorator demo's current sandbox_api_key option/ABX_SANDBOX_API_KEY configuration. The existing immutable source examples receive a separately verified refreshed pin; they are not silently relabeled as tested current source here.

Checks:

- PASS: real wheel/sdist packaging tests, 7 passed. Metadata requires PyYAML unconditionally and exposes neither retired server nor declarative extras.
- PASS: make build dist-check. Both wheels/sdists and all twine checks pass; py.typed markers exist. A fresh base-only combined wheel installation imports yaml and the workflow API without extras and parses YAML. No development environment package can mask this check.
- PASS: scoped Ruff for packaging tests, distribution check and the updated decorator example; the example imports all four wrappers with current public options without creating cloud resources. The first broader example lint exposed its pre-existing misplaced import/formatting and retired api_key argument; these were corrected in the changed example, rather than ignored.
- PASS: git diff --check.

There is no tracked repository lockfile to update; package metadata and the existing reproducible distribution checks remain the authority. The Provider T4 fixture must keep the base SDK install and rerun with this exact new commit; adding a test-only PyYAML pip install is not acceptance. The pinned standard SDK implementation is unchanged.
