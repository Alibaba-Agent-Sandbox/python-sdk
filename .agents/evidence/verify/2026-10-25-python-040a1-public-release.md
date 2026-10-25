# Verification: public Python 0.4.0a1 pair

- Date: 2026-10-25
- Implementation: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/108
- Source and immutable tag: `11e7e93486f852edd1fe23366c52936058d9d446`, `v0.4.0a1`.
- Result: PASS — both alpha distributions are public and independently installed.

## Publication gates

The final PR head `97888a7a8008053ecef2eb252324a0e8fa165dd6` passed all 11 checks.
The PR was merged with that expected head, and the actual merge SHA was confirmed.
[Main CI](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40179926574)
passed all 10 jobs before the new matching tag and
[GitHub prerelease](https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a1)
were created. Neither an existing tag nor a public version was replaced.

[Publication run 40180399513](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/40180399513)
passed on its first attempt: complete tag CI, paired build, artifact checks and
preservation, existing-public-file preflight, server upload, client upload, public
file verification and fresh installation. No upload or readback failure occurred
in this publication run. The configured repository credential remained in Actions;
its value was not copied into the workspace or written to evidence.

## Independent public readback

Both exact-version PyPI JSON responses contained one wheel and one sdist. Each was
downloaded independently, hashed, and compared against both the public SHA-256 and
the exact `python-release-candidate` artifact preserved by the successful workflow.
All four comparisons passed:

| Public file | SHA-256 |
| --- | --- |
| `agent_sandbox_server-0.4.0a1-py3-none-any.whl` | `475422904a2f8f11a883ceefc02e5acd2bbfbe9c83ee2b9e7d0d04fec4982473` |
| `agent_sandbox_server-0.4.0a1.tar.gz` | `2ad964bf12c28ee60f2fab46f7ae73c2d582d2b2b5978f51767ed6a3d4d3b461` |
| `agent_sandbox_client-0.4.0a1-py3-none-any.whl` | `1db89a5ba669bb52d51844a07cc2180e13df790b215833f2db758114fb9a8eb2` |
| `agent_sandbox_client-0.4.0a1.tar.gz` | `335c10dcddb759c2f9e54294daabf0944171b39a28c1d12ae9dc0e6444533b71` |

To reproduce: fetch `https://pypi.org/pypi/<distribution>/0.4.0a1/json` for
`agent-sandbox-server` and `agent-sandbox-client`; download each `urls` entry; compare
`hashlib.sha256(content).hexdigest()` with `digests.sha256`. Download the preserved
candidate from the linked publication run and compare the same filenames and hashes.

## Fresh public installation

From outside the source checkout, create a new virtual environment and run:

```sh
python -m pip install --no-cache-dir --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a1'
python -m pip check
python -c "from importlib.metadata import version; print(version('agent-sandbox-client'), version('agent-sandbox-server'))"
python -c 'from agent_sandbox.api import launch_template, TemplateSession, TemplateLaunchError; from agent_sandbox.server import start'
```

The independent check used Python 3.13.13. Installation and `pip check` exited 0;
both installed versions were 0.4.0a1, the client automatically required the exact
matching server, and module loading came from the new environment's `site-packages`.
The new template API and existing standard sync/async/Provider creation exports
imported successfully. The installed `launch_template` signature has no
`workflow_id`, and its packaged validator accepted a specification 5 native `base`
manifest. These are installed-distribution checks, not a new cloud acceptance claim.

## Scope and retained limitations

The previously recorded five real unified-template startup cases, original full
CLI pass, additional unexplained CLI failure, and focused successful file check
remain separate in the [runtime diagnostic evidence](2026-10-25-unified-template-cli-diagnostic.md).
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/109 remains open; this
release does not invent a cause or erase the failure. Local environment-intercepted
test failures also remain recorded in earlier evidence.

The release is alpha. It does not certify all providers, every template operation,
or production readiness. Installing this host package does not update runtime
packages inside existing images. The public catalog/CLI cutover is coordinated in
their owner repositories; no catalog-dependent cloud experiment was run during
this documentation follow-up.

Documentation-only verification: repository health 106 passes / 1 warning / 0
failures, hygiene and whitespace checks passed. Historical evidence was preserved.
