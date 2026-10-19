# Local changes to the pinned source port

`SOURCES.json` records original source hashes, not hashes after relocation. The fixed
sources are E2B 2.31.0, E2B Code Interpreter 2.8.1 and their bundled Connect runtime.
The adjacent MIT LICENSE files preserve upstream attribution. This is maintained
project source; changing an original source hash requires an intentional baseline update.

Local changes beyond namespace relocation:

- Import `agent_sandbox._standard.connect` instead of the bundled top-level e2b_connect.
- Use project package metadata and version; do not require installed E2B distributions.
- Read canonical E2B connection settings with project config-file fallback; default to
  Alibaba Express, derive explicit domains correctly, and accept Alibaba-issued API keys.
- Support Alibaba's documented optional snapshot `name` list filter in sync and async
  clients/paginators, which the fixed Python SDK does not expose. Preserve all existing
  positional arguments. Encode qualified snapshot names in the template deletion path.
- Accept Alibaba snapshotting/snapshot_failed states in lifecycle/list responses.
- Replace example workstation home paths in MCP documentation with generic paths.

Run `scripts/check_standard_contract.py` with a separately installed reference interpreter,
contract unit tests, real-cloud migration scenarios and package checks after changes.
The shape comparison allows only the documented additional snapshot-name keyword.
Runtime source imports never load an external E2B distribution.
