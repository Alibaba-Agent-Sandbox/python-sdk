# Verification: native server startup acknowledgement — 2026-10-19

Result: PASS for focused regression and local real-component acceptance; complete current-head hosted matrix required before merge.

Scope: native client helper/tests and matching bilingual server guide, based on SDK `27c84e2b87427664b3e5fcb707d7c52dda6e4252`; Python3.12.13, Linux x86_64. Client/server version0.3.0. Fresh paired wheels installed outside the source checkout, all extras and dependency compatibility checked.

- Before fix: meaningful lazy-reader regression FAIL (launch counter0); 12 existing tests PASS. The initial real probe reached native HTTP502 with no listener. A subsequent console-command probe correctly failed startup when the base image process environment did not provide its entry point. No failed attempt is relabeled.
- After fix: 16 focused helper tests PASS, including bounded missing acknowledgement, no private output in errors, wait=False dispatch, process exit during health, and reader release.
- Full local client checkpoint:2186 PASS/24 SKIP/10 integration deselected. Subsequent focused final helper tests16 PASS; full current-head hosted matrix remains required. Ruff/format and mypy105 source files PASS.
- Full unchanged server suite checkpoint:852 PASS/3 FAIL/1 SKIP. One failure was an audit venv missing pip; after installing pip, its isolated package-list test PASS. Two raw HTTP/WebSocket framing tests receive proxy HTTP502 in this controlled environment. Assertions are preserved; no local full-server pass claimed. Server lint and mypy56 files PASS.
- Real locally initiated Express acceptance from installed wheels plus actual installed npm artifact and SEA: wheel create/execute and file write/read; npm and SEA exec; native named hello through public port; reconnect after closing the creator client still invokes the retained remote server. All six checks PASS. Explicit module command used for the task-owned installed server. Native foreground process execution also PASS.
- Cleanup: owned sandboxes destroyed in finally and independently listed absent, zero residuals. No template or snapshot created; no cloud/model Actions or secret upload.

Build/twine and public source-pair checks are recorded with their actual result before publication. Version0.3.0 on source/wheels is not a claim of PyPI publication or current-main GitHub Release. Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/69 .

Final distribution/source checks: server and fixed-client sdist/wheel builds and twine metadata checks PASS. A second fresh seeded consumer installed the public immutable source archive `08c51248bb3c1a6f1380bdb3d33126cda23bb7ec` as a matching server + client[all] pair:52 dependencies resolved, pip check PASS, sync/async/native/server/interpreter imports PASS. Installed native implementation SHA256 `9d3db1f720028c3a4329bd52cd72439607b39203a2343fc285c674097c98659f` matches the exercised fix. All sixteen current install recipes point to that immutable implementation; package README guide links also render outside GitHub. Canonical website links use .cn. No package publication performed.
