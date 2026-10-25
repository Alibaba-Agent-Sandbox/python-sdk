# Verification: current public SDK documentation

- Date: 2026-10-25
- Tested base: dab0e3194e3f790fab28307d9fd126b8239bcbd7 plus scoped documentation changes.
- Package under test: official PyPI agent-sandbox-client/server 0.4.0a2.
- Environment: Linux, fresh Python 3.13.13 venv, Express account configured via
  canonical environment variables; values and resource IDs are not recorded.
- Result: PASS for documentation-specific execution below; broader example suite
  remains PARTIAL because the browser cold installation failed.

## From-page real execution

- Install: fresh venv, official-index exact `agent-sandbox-client==0.4.0a2`, pip
  check, public sync/async/provider/server imports all PASS. Both distribution
  versions are exactly 0.4.0a2. Source import injection was not used.
- Extract the first Python fence from each actual `getting-started.md` page,
  save it as a script outside the checkout and run with the fresh environment.
  Both complete scripts PASS: create base, command output/exit status, file
  write/read, download, upload, content equality and context-manager kill.
- Independently call `ProviderSandbox.get_info_by_id` for each created ID:
  typed `SandboxNotFoundError` PASS. No owned sandboxes remain.
- [Machine-readable source hashes and results](2026-10-25-public-sdk-documentation-cloud.json).

## Public signature and local HTTP execution

- Inspect published `sandbox` and `create_mcp_app` signatures: sandbox_api_key,
  sandbox_base_url and sandbox_domain present; api_key/api_url/domain absent.
- Confirm native `ProviderSandbox.create_sync` remains callable; retain it.
- Install exact `agent-sandbox-client[mcp]==0.4.0a2` from official PyPI, as the
  HTTP guide requires. Construct its documented create_mcp_app with the corrected
  sandbox_api_key argument: real ASGI `/health` 200 and unauthenticated `/mcp` 401 PASS.
- Construct a decorator with all three canonical configuration arguments: PASS.
  This only validates configuration, not another remote function execution.

## Independent broader public example rerun

The maintainer's new public-a2 rerun executed all fourteen cloud examples: thirteen
PASS; browser example FAIL while installing Chromium and dependencies on base
under its 300-second command deadline (406.73 seconds total including preceding pip).
Every owned sandbox was independently confirmed absent with typed 404. The real
Qwen-generated sorting example passed. Local protocol fixtures are not real agent
executions. These observations do not certify a new template image or the entire
template matrix. The failure is retained, and browser setup/default-template policy
is pending user choice. This documentation change does not close
[Issue 111](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/111).

## Published deadline verification

The independent public-a2 check observed typed CommandTimeout for silent output
(1.353 seconds) and continuous output (1.159 seconds). Each exact observed owned
PID was absent from process.list afterwards, a subsequent command worked, and
the owned sandbox was independently absent with typed 404. This closes the runtime
deadline acceptance scope of [Issue 113](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/113),
separately from the unfinished browser scope in Issue 111.

## Example README correction

The EN/ZH core API overview previously put interpreter and hello named-command
calls inside a base ProviderSandbox context. Split this confirmed misleading
example into base shell execution, the actual standard interpreter entry, and
a separately launched python-hello application bound with application_client(token).
No runtime helper or fallback is added. Correct the example table, decorator
template ID, writable file path and canonical configuration wording together.

## Repository skills

The current SDK/provider SKILL.md files now use published a2 instead of claiming
a1 is awaiting publication. Their installation/Dockerfile pins and shared ABX
configuration agree with the user guides. Original public client/server wheels
and sdists contain neither skill file, so this Git documentation fix does not
replace or require rebuilding the immutable published a2 artifacts.

## Static checks and limits

- PASS: repository health 106 PASS / 1 warning / 0 failures; hygiene PASS.
- PASS: scan maintained docs/READMEs for retired Git-archive install pins and old
  decorator/MCP keywords. Historical explicitly retired provider-engine design and
  merged evidence remain history; actual third-party api_key/domain options remain.
- Follow-up review: canonical ABX configuration is supported by all project
  entries, including standard sync/async/interpreter; it is not ProviderSandbox-only.
  Corrected this wording in the installation, beginner, migration and example guides.
  Standard public api_key parameters and real third-party E2B configuration remain valid.
  The import-migration example changes only its configuration docstring, not code.
- Documentation-only change: no product runtime or test implementation changed.
  Full package CI remains enforced by the PR; unrelated cloud matrix is not rerun
  merely for prose. CLI source preparation and new application images are being
  separately verified by their owning repositories; no new success claim is made here.
