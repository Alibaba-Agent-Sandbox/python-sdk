# Decision: Retain python-sdk Agents API delivery operations

Status: proposed

## Problem

Runtime evidence exists in this owner, while the capability/alignment matrix and the exact official-SDK interoperability probe were retained only outside the repository. Maintainers need both the operations and the precise limits in a standalone clone.

## Decision

Keep SDK/runtime verification and OpenAI compatibility observations in this .agents directory. Preserve exact test revisions and earlier failures. Retain the original small offline interoperability source and typed outcomes, without adding OpenAI as a product dependency or copying its distribution binary.

## API Design

No SDK or server API change. The candidate public contract is v1; the Managed profile and the broad local server retain distinct contracts.

### Owner verification operations

```sh
make dev
make test
make ci
bash scripts/check-repo-health.sh --quiet
make hygiene
```

On a shared same-UID host, the recorded full validation used a real PID/proc namespace via `unshare -Upf --map-current-user --mount-proc` while retaining a non-root UID. Preserve the process-safety scanner and assertions. A same-UID process outside the owned execution scope is not proof of safe reuse. Root PostgreSQL restrictions, missing namespace support and old CLI prerequisites must be reported, not hidden as passes.

Synchronize the canonical files with scripts/sync_template_v1_contract.py using the exact producer revision and check the source lock. Its source_checkout argument names a reviewed producer checkout; --revision selects its full immutable commit, and --check verifies without rewriting. Build both wheels and verify fresh client-only and server-extra installations; match source bytes, not the unchanged a7 metadata label. Custom instance values reach the owning Worker, while Session/state/receipts keep only permitted safe values and environment names.

### Capability and compatibility review

Managed supports the admitted Codex/Qwen text, Session/Turn, durable submissions/events, fixed file/artifact and close/delete subset. Busy input that cannot steer is rejected; the explicit submission queue is an extension. Unsupported external tools/MCP/subagents/automations are not silently advertised. The official hosted harness/self-hosted exec-server topology is not the same as a full CLI/model/tool loop in Sandbox.

Saved Agent plus inline Session overrides are officially valid; do not reintroduce a one-of guard into Managed. The broad local server still has a separate saved-Agent/override difference and different persistence/input behavior. Adapter classes are not evidence that HTTP admits Claude/Cursor.

The [retained SDK probe](../../../evidence/verify/2026-11-12-agents-api-interoperability.md) uses official openai3.49.0 against real loopback Managed HTTP/SQLite, with no Worker/model/cloud. Default create/retrieve/list decoding passed. Strict validation still fails on real Agent/harness/environment differences. The public integer timestamp/empty-action/Vault projection fixes only its verified fields; never fabricate a remote_url, inline saved-Agent identity or effective model settings to satisfy a decoder.

### Existing evidence

- [Full local gates and exact source scope](../../../evidence/verify/2026-11-12-template-v1-runtime-final-local.md).
- [Projection](../../../evidence/verify/2026-11-12-managed-session-projection.md), [Core reader and installed wheel](../../../evidence/verify/2026-11-12-template-yaml-core-reader.md), [standalone policy documentation](../../../evidence/verify/2026-11-12-standalone-policy-docs.md).

The final Server image uses SDK source b988d2a76057b6202d836ec329cc0bd90a572b26; c4d43a2 only changes later documentation. Image/model evidence belongs to the template owner and does not establish FC ingress, old Worker routing or cloud cleanup.

## Alternatives considered

A root-only compatibility report can be lost between sessions and makes default SDK decoding look stronger than it is. Adding OpenAI to the product dependencies or implementing a second hosted harness is unnecessary. Keep the narrow probe and truthful matrix in engineering records instead.

## Dependencies

Tracking: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309. Cross-repository links refer to owner branches
and do not assert that pending work is merged or published.

- [awesome-templates owner operations](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/feat/template-v1-migration-20261112/.agents/notes/proposed/process/2026-11-12-agents-api-delivery-operations.md).
- [agent-sandbox owner operations](https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/blob/feat/template-v1-parser-20261112/.agents/notes/proposed/process/2026-11-12-agents-api-delivery-operations.md).
- [registry owner operations](https://github.com/Alibaba-Agent-Sandbox/registry/blob/feat/template-v1-registry-20261112/.agents/notes/proposed/process/2026-11-12-agents-api-delivery-operations.md).
- [blogs owner operations](https://github.com/Alibaba-Agent-Sandbox/blogs/blob/docs/agents-api-owner-records-20261112/.agents/notes/proposed/process/2026-11-12-agents-api-delivery-operations.md).

## Test Strategy

Validate links, note shape, retained source/result hashes, probe Python syntax and record hygiene. Historical full-suite counts, final deltas and remote matrix are separate facts. Copying the probe does not rerun it; a future probe run needs its own dated result.

## Acceptance criteria

A standalone SDK checkout explains what was tested, how to repeat local gates, what remains unaligned, and which cloud/model operations are still required. No record implies strict official SDK compatibility or a new package publication.

## Evidence

- [Record-placement verification](../../../evidence/verify/2026-11-12-agents-api-delivery-operations.md).
