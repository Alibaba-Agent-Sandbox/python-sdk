# Releasing the Python package pair

Publish `agent-sandbox-server` first, then `agent-sandbox-client`, from the same source tag. The client pins the matching server dependency. The unrelated PyPI project `agent-sandbox` is never a publication target.

## Candidate and versions

The current published pair is **0.4.0a3**, an opt-in alpha. The public release
workflow, artifact hashes and fresh-install readback passed; this does not certify
all templates, cloud account features or production workloads. Use a new lockstep
version and reviewed tag for the next release; never replace published files.
Provider-plugin integration additionally needs the compatible separately installed
CLI and the selected provider's configuration.

Keep four locations equal; existing version-lockstep tests enforce them:

- `client-sdk/src/agent_sandbox/_version.py`
- `server-sdk/src/agent_sandbox/server/_version.py`
- `client-sdk/pyproject.toml`: `agent-sandbox-server==<version>`
- `client-sdk/src/agent_sandbox/agent/mcp.py`: `SERVER_VERSION`

Update CHANGELOG and run the repository CI and real-component acceptance gates before tagging the reviewed commit. A blocked gate remains blocked for the release review.

## Build and inspect

```bash
# First update the lockstep version and substitute its actual reviewed tag below.
make build dist-check
python scripts/check_release.py candidate --tag 'v<next-version>'
python scripts/check_release.py preflight
```

Both wheels and sdists must pass metadata checks; a fresh wheel install must expose the standard clients, ProviderSandbox, template YAML parser and server imports. `dist/` is generated and must not be committed. The server owns only `agent_sandbox/server/`; the client owns the root namespace. A different file already published under a candidate filename fails preflight rather than being silently skipped.

## Authentication and execution

Store a PyPI API token authorized for both distributions as GitHub repository secret `PYPI_API_TOKEN` (or the same secret in the `pypi` environment). The two upload steps pass it directly to the PyPA action; no local export, token in source or OIDC publisher is required. Token mode does not create OIDC attestations. The job targets PyPI, not the separate TestPyPI service.

The publish job depends on the complete reusable CI for the same tag, then builds and verifies the candidate, preserves it as a workflow artifact, runs public-file preflight, uploads server then client, verifies every public SHA-256 and installs only the pinned client in a fresh environment. Automatic installation of the matching server, public imports and `pip check` must pass.

Manual dispatch **defaults to dry_run=true** and accepts a version tag, not a branch:

```http
POST /repos/Alibaba-Agent-Sandbox/python-sdk/actions/workflows/publish.yml/dispatches
{"ref":"v<next-version>","inputs":{"dry_run":"true"}}
```

After dry-run validation, publish a GitHub **prerelease** for that reviewed tag, or dispatch the same tag with `dry_run=false`. Publishing a GitHub Release triggers upload. Merely creating a draft release does not. Do not publish a stable release for an alpha version.

## Recovery and public verification

If one upload fails, preserve and reuse the exact candidate artifact from that run. Preflight compares existing filenames and SHA-256 before `skip-existing` can resume the missing files. Rebuilding is not proof of identical bytes; if hashes differ, stop and investigate instead of overwriting or silently accepting them. Only call the release published after both projects' public metadata, downloads and fresh installation pass.
The workflow retries missing public metadata and fresh official-index installation
at most six times, ten seconds apart. Artifact digest mismatches fail immediately;
pip check and import failures are not retried.

After verified publication, consumers can explicitly opt in:

```bash
python -m pip install --index-url https://pypi.org/simple 'agent-sandbox-client==0.4.0a3'
python -m pip check
```

## 中文发布说明

client/server 必须同版本发布，先上传 server。当前已公开配套版本为 `0.4.0a3`
alpha，发布流程、产物摘要及全新公开安装验证均已通过；这不代表所有模板、账号能力
或生产负载已完成验证。下一次发布须选择新的同版本双包和已审查标签，不得替换任何已公开文件。Provider 插件还需兼容的独立 CLI 和所选提供方配置。

四处版本（两个 `_version.py`、client 的 server 精确依赖、MCP `SERVER_VERSION`）一起更新。先通过同一标签的完整 CI、产物检查和真实组件验收。将 token 保存在 GitHub repository 或 `pypi` environment 的 `PYPI_API_TOKEN` secret 中，由上传步骤直接引用；不要复制到源码或日志。此流程发布到正式 PyPI 的预发布版本，不是 TestPyPI，也不声明 OIDC 证明。

手动执行默认 `dry_run=true`，必须选择实际已审查的 `v<next-version>` 版本标签，选择 main 会失败。验证后创建该标签的 GitHub prerelease，或显式设置 `dry_run=false`。工作流保存本次产物，先检查已有公开文件摘要，再按顺序上传；最后仅安装固定版本 client，验证 server 自动依赖、导入与 `pip check`。

部分上传失败时保留并使用同一批候选文件。重新构建后如摘要不同，应停止调查，不得依赖 skip-existing 掩盖差异。全部公开包下载与安装验证通过后，才更新对外的发布状态。
