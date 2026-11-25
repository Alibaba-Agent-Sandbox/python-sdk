# Verification: Python package inventory without pip

- Date:2026-11-25
- Issue:[184](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/184)
- Result:PASS for the scoped local HTTP behavior; full candidate CI remains separate.

## Original failure and cause

The initial full server suite had885passed,1skipped,6failed; one failure was TestPackages.test_pip_returns_structure. The fresh uv environment contained the SDK and pytest but no pip module. Source inspection confirmed handle_packages ignored the subprocess nonzero exit and converted JSON parse failure into200/empty packages. This is a real existing bug, not merely a missing test dependency.

## Verification

- Seven package-related route regressions passed,20deselected: existing API shapes, actual installed pytest listing while subprocess.run is forbidden, sanitized metadata failure, duplicate and unnamed distribution handling.
- Created a fresh virtual environment with uv and installed editable server-sdk with uv pip. Only server0.5.0a0 and websockets17.4 were installed, with pip absent by importlib.util.find_spec.
- `python e2e/verify_package_inventory.py` used the real SandboxServer and HTTP request in an isolated loopback network. Result: pip_installed=false, http_status=200, server_listed=true, dependency_listed=true.
- The local listener shut down and its thread joined. No cloud resources or package publication.

## Review

Round1 independently checked standard metadata semantics, missing names, duplicate pairs, stable ordering and sanitized error behavior. The patch adds no dependency and leaves npm handling unchanged. Final code/test review and complete CI are recorded in the associated PR.


## Second review

The independent reviewer approved current-interpreter semantics, missing-name handling, exact-pair deduplication, sanitized500 and no pip process. A final original-name tie-break makes set-derived output deterministic when names differ only by case. Full lint/typecheck/format passed; the complete final-tree matrix is checked by CI. The fresh pip-less HTTP probe, package-route regressions and cleanup were not replaced with synthetic metadata-only evidence.
