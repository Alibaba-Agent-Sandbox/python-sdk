# Decision: Prepare the matching 0.5.0a0 Python preview

Status: proposed

## Problem

Current main and the immutable public 0.4.0a7 pair report the same version despite
different dependency and API behavior. Main makes the local server runtime
optional and removes module-level `sandbox.run` / `sandbox.run_async`. Consumers
need an explicit version boundary and matching installation instructions.

## Decision

Set both distributions and the optional server pin to 0.5.0a0. Update the current
bilingual installation, Client SDK, Server SDK and SDK usage guides plus embedded
package READMEs for that preview. Document the local `[server]` requirement and
explicit application calls. Do not claim candidate artifacts are already public
or change historical release evidence and version-specific examples.
The new 0.5 changelog describes final preview compatibility and community contact,
without carrying an expired release forecast into the new release's behavior.

Base this preparation on the actual merge of
[PR #172](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/172),
`d333d9d51387c89027987d4cfda4f6d2a9ce0daa`. Its final reviewed head
`b516356405054775f3e386c41308867dbdbfa13e` passed all 13 remote checks. Move the
delivered upload decision to `implemented`; update only its link targets in prior
evidence, preserving the recorded verification facts, commands and failures.

## API Design

No runtime API implementation changes. The new version identifies the already
merged boundary: base clients do not install the local server; `[server]`, `[all]`
and `[dev]` provide the exact matching runtime. Use `ServerClient.commands.run`
for an explicitly selected deployed application. `ProviderSandbox.run` and the
remote decorator remain available.

## Alternatives considered

- Reuse 0.4.0a7: rejected because immutable public artifacts and changed source
  would remain indistinguishable.
- Increment only the alpha counter: a new minor preview expresses the dependency
  and removed API boundary more clearly.
- Combine pending feature branches or another cloud matrix: rejected as unrelated
  to version metadata. Keep actual artifact and downstream-consumer verification.

## Dependencies

- [Release Issue #173](https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/173)
  remains open through real publication and downstream acceptance.
- [CLI Issue #270](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/270)
  and [CLI PR #271](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/271)
  own matching Python pins and real image/HTTP MCP consumption. That gate depends
  on the public Python pair and is not replaced by source installation.
- Existing tag-bound publisher, four preserved artifacts, digest preflight and
  fresh official-index installation checks. No new release workflow or credential.

## Test Strategy

Build both wheels and sdists; inspect versions, unconditional/extra dependency
metadata and actual embedded READMEs. Exercise clean candidate client-only
installation followed by matching `[server]` resolution and `pip check`. Run owner
checks and full local tests while the independent Draft PR runs the complete
remote Python matrix. Preserve original failures and optional skips.

Reuse PR #172's real cloud transfer and cleanup evidence only after independently
confirming that the server code differs solely in `_version.py`. Run no new cloud
instance for version strings. The tag publisher and CLI real image/MCP acceptance
remain distinct required release gates.

## Acceptance criteria

- Both packages, imports and all matching server extras use 0.5.0a0.
- Four valid artifacts, accurate READMEs and clean sequential installations pass.
- Bilingual guides, CHANGELOG, owner note/evidence and required latest-head checks
  are complete before merging the preparation PR.
- The existing publisher binds the matching tag, preserves artifacts and verifies
  their public digests and fresh installs; no existing artifact is overwritten.
- CLI real image and HTTP MCP consumption of the public pair is recorded before
  Issue #173 is closed. Preparation, merge, publication and consumer gates remain
  separate claims.

## Evidence

- [Preparation verification](../../../evidence/verify/2026-11-25-python-050a0-preview.md).
- [Changelog review and local server follow-up](../../../evidence/verify/2026-11-25-python-050a0-changelog.md).
- [Merged upload acceptance](../../../evidence/verify/2026-11-25-bounded-file-uploads-cloud.md).
