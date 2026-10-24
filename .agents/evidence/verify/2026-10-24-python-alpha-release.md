# Verification: Python alpha candidate

- Date: 2026-10-24
- Result: PARTIAL (publication and remote checks pending at this commit)
- Candidate: client/server 0.3.1a1, prior runtime source ddc96d8 plus scoped release workflow/docs and real-doctor regression.
- Environment: Linux, Python 3.12.13, Node 22; source copied byte-for-byte to temporary local storage to avoid mounted-filesystem timeouts. Secrets loaded internally, never recorded.

## Results at candidate preparation

- Full client suite: 2,193 passed, 25 skipped. Cross-language prerequisites are optional in this generic suite; the separate strict job requires them.
- Full server suite: 873 passed, 1 skipped, 2 failed. Missing WebSocket key and policy chunked framing received managed-network 501/502 instead of expected 400; assertions were not weakened. Normal remote CI remains required.
- Actual strict Python-to-Node suite with CLI 0.4.11 source: real doctor valid initialization/close and invalid JavaScript both PASS. Existing Cube process-RPC/restart scenarios remain blocked locally by 501/502; not counted as passing.
- `make lint typecheck format-check build dist-check`: PASS, including both wheel/sdist pairs, Twine and fresh combined installation.
- `python scripts/check_release.py candidate --tag v0.3.1a1`: PASS. Both public project metadata endpoints currently return 404; no existing artifact collision was observed.
- The actual compatibility checker accepts 0.3.1a1 for sdk >=0.3 and correctly refuses 0.3.0a1.
- Real-cloud platform and lifecycle subset: 15 passed, 1 slow case deselected; existing owned-resource finalizers ran. Full non-slow E2E is being completed separately and will receive a new evidence entry; this subset alone is not described as complete E2E.

## Publication boundary

GitHub repository secret PYPI_API_TOKEN exists; its value is never exported to local tools. Workflow now explicitly consumes that secret, uses distinct upload concurrency, defaults to dry run and accepts a version tag only. No token authority is inferred from its mere presence; upload and public readback must establish success. No stable release is implied by this alpha.

The runtime fixes include real initialized-provider verification, content-based catalog update and rollback, load compatibility and strict cross-language CI. Companion CLI support must be delivered before recommending the new Node doctor. Complete provider/template image and native acceptance is independent of the alpha package publication.
