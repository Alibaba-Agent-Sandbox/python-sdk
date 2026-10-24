# Verification: public Python a5 release

- Date: 2026-10-24
- Result: PASS for publication, public artifact integrity and clean installation; this is not a complete template/model certification.
- Source: `1b235830bc4a8cbec275b530bf2dc2869e8d0c4b`, immutable `v0.3.1a5` tag.
- Changes: [PR #100](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/100), [PR #102](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/102); [Issue #99](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/99), [Issue #101](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/101).
- Environment: Linux, clean Python 3.12 virtualenv, official PyPI, no cached package install; credentials are not recorded.

## What was verified

Both 0.3.1a5 distributions are public. The client automatically installs exactly the matching server. All four downloaded artifacts match public SHA-256 values; the publication job also verifies those files against its preserved build artifacts. Both PyPI descriptions contain the corrected prerelease opt-in commands rather than the old a2 pin.

The [release](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.3.1a5) tag matches the actual merge commit. [Main CI 40114095872](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40114095872) passed. [Publish 40114135163](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40114135163), attempt 2, passed after all required reusable CI checks.

## Commands and results

The disposable virtualenv path is normalized below as `<fresh-venv>`.

```bash
python3.12 -m venv <fresh-venv>
<fresh-venv>/bin/python -m pip install --no-cache-dir --index-url https://pypi.org/simple 'agent-sandbox-client==0.3.1a5'
<fresh-venv>/bin/python -m pip check
```

The fresh installation and `pip check` exited 0. Outside the source checkout, imports of `Sandbox`, `AsyncSandbox`, `ProviderSandbox`, `ServerClient` and `SandboxServer` passed. Distribution metadata reported client and server 0.3.1a5, and the loaded module came from the virtualenv's site-packages.

Read the exact-version JSON for both distributions at `https://pypi.org/pypi/<distribution>/0.3.1a5/json`; download each returned file and compare `hashlib.sha256(content).hexdigest()` with `digests.sha256`. All four comparisons passed:

| Artifact | SHA-256 |
| --- | --- |
| `agent_sandbox_client-0.3.1a5-py3-none-any.whl` | `cb27f4dcc5cf7a15dabba6f680868ab87478b6084b59c40ba938e3756618eb51` |
| `agent_sandbox_client-0.3.1a5.tar.gz` | `7814849399bc83678153e635ea78176b0235c0c50dbc3367ae39f962414d25cf` |
| `agent_sandbox_server-0.3.1a5-py3-none-any.whl` | `96405446aa84d4eb939536d90355f614bce468b745784def823b29781c638a1a` |
| `agent_sandbox_server-0.3.1a5.tar.gz` | `49f87ba4ad8552794eee43329b4ba1bfcdc07eb2dd502b5e0fb6707ceb0208f0` |

Local record checks initially rejected an absolute scratch path in the command transcript. Normalizing that path fixed the record; no path or secret guard was relaxed. Corrected `make hygiene` and `git diff --check` passed; repository health reported 106 PASS, 1 existing warning and 0 failures.

## Preserved failed attempt

Publication attempt 1 uploaded both wheel/sdist pairs, then failed its post-upload readback. Metadata initially returned HTTP 404 and the subsequent clean pip resolution could not yet find server 0.3.1a5 in the public index. Independent later readback and a fresh no-cache install succeeded before requesting `rerun-failed-jobs`. Attempt 2 reran only the failed publication job, verified existing file digests and passed. No release artifact or tag was replaced. The initial failure remains visible in the workflow history; it is not counted as a pass.

The [a4 stopped-upload history](2026-10-24-package-installation-docs.md) remains unchanged: that tag was preserved and no a4 PyPI upload executed.

## Runtime evidence and limits

[OpenSandbox T4 40110372103](https://github.com/Alibaba-Agent-Sandbox/awesome-providers/actions/runs/40110372103) verified default/direct, portable/direct and default/proxy application calls, independent Node HTTP calls and cleanup on the unchanged application runtime. The a5 change only corrects package instructions and version metadata. Public-package template runs are owned and recorded in the template repository; this release record does not claim all templates, model tasks, interpreters or PTY paths passed.

## Cleanup

These publication/readback checks created no cloud resources. They did not modify shared templates, images or account configuration. Existing runtime-run cleanup evidence remains in the linked T4 run.
