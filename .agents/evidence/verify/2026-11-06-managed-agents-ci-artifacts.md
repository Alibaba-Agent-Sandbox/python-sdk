# Verification: Managed Agents CI artifacts

- Date: 2026-11-06
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/156, runtime commit `2ee960cb919d640c282cbbeff24d15aa051b7495`.
- Result: PARTIAL — required remote CI and exact CI-wheel installation passed; publication and managed FC acceptance are coordinated separately.
- Package under test: matching client/server 0.4.0a7, downloaded unchanged from the successful GitHub Actions artifact.
- Environment: GitHub Ubuntu matrix on Python 3.10/3.11/3.12; fresh local CPython 3.12.13 wheel-install environment. No credential values recorded.

## What was verified

The [complete CI run](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/42157232742)
and [documentation-link run](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/42157232731)
both completed successfully at the exact runtime commit. The CI distribution archive was
downloaded and its SHA-256 compared with GitHub's artifact digest before inspecting its members.
The exact CI wheels were then installed together in a new environment outside the source tree.

The preceding [local/component/cloud checkpoint](2026-11-06-managed-agents-release-candidate.md)
is preserved. Its locally built packages and the CI packages have identical uncompressed wheel
members, including code, `METADATA`, `WHEEL` and `RECORD`, but different ZIP external mode attributes:
local files are `100755`, while CI files are `100644`. The shared development filesystem does
not preserve normal file modes. These archives therefore have different bytes and must not be
described as the same tested artifact. The CI originals are the selected publication candidates;
earlier local artifacts remain a separate comparison, without overwriting either set.

## Commands run

- Fetch the exact commit's Actions runs/jobs and distribution artifact through GitHub.
- Verify archive SHA-256 against the returned artifact digest.
- Compare wheel members and ZIP metadata without executing downloaded code.
- Create a new Python 3.12 environment and install both exact CI wheels, selecting the managed extra.
- `uv pip check` in that environment.
- Isolated interpreter probe: matching versions, native provider import without upper managed application imports, identical lower/old public `ManagedError`, server import, and a real SQLite transaction.

## Results

| Check | Result | Scope |
| --- | --- | --- |
| Six client/server matrix jobs | PASS | Python 3.10, 3.11 and 3.12; lint, formatting, mypy and complete non-integration tests. |
| Pinned E2B callable contract | PASS | Public signatures and sync/async shapes. |
| Python to Node provider engine | PASS | Required cross-language scenarios using the pinned CLI/provider fixtures. |
| Public runtime fixtures | PASS | Both `python-hello` and `agents-cli` build, run actual HTTP checks and clean up their owned containers. |
| Hygiene, build and distributions | PASS | Complete CI artifact checks. |
| Documentation links | PASS | Independent workflow. |
| Artifact identity | PASS | Artifact 13475860199; archive SHA-256 `26548e9e5a11a59fda47bd664dcf3acec97c773125fa492f198decaf76e2dd61`. |
| CI versus local wheel payload | SAME FILE BYTES, DIFFERENT ARCHIVE | All 368 client and 65 server uncompressed entries match; only ZIP file-mode metadata differs. |
| Fresh exact-CI-wheel install | PASS | CPython 3.12.13, consistent dependencies, same error class, no upper application imports from native provider, real SQLite transaction. |
| PyPI upload/readback and joint managed FC deployment | PENDING | No publication or FC success is inferred from CI. |

### Selected exact CI distributions

| File | SHA-256 |
| --- | --- |
| `agent_sandbox_client-0.4.0a7-py3-none-any.whl` | `1fa30ec182465753d9b538b3837d625325da9b4340ba220cfbc0764de6fbca00` |
| `agent_sandbox_server-0.4.0a7-py3-none-any.whl` | `210db5e796f4fc63e84156d19076c946d261b48c47ec6c8c1db82b8b60691f08` |
| `agent_sandbox_client-0.4.0a7.tar.gz` | `7e2c9c33d7efa0cc7c89f417ef853089af4fb70e48a25e1661fca761980a1539` |
| `agent_sandbox_server-0.4.0a7.tar.gz` | `f2e1f4fb6e8e17d272ad35e52e02df26a640c7adcb6e909515b501de517ac063` |

## Cleanup

This continuation performs read-only GitHub access and a bounded local installation/SQLite
probe. It creates no cloud resource, management key, tag or public release. Temporary database
files are removed by their context manager. The CI fixture jobs independently confirm deletion
of their owned containers. The exact distribution archives remain as review artifacts.

## Problems found

Shared-filesystem mode normalization makes local archive hashes differ from canonical CI builds.
No source or package-metadata content difference was found. Downstream validation must select
and record one exact distribution set rather than silently treating the two archives as identical.

## Not verified

Public PyPI installation, active managed FC deployment and model business acceptance are not
certified by this record. The management-key preparation E2E remains intentionally excluded
pending its separate explicit consent. The generic cloud E2E checkpoint records its actual skips
and corrected replays independently.
