# Retained official SDK interoperability probe

The accompanying directory retains the original probe execution semantics, actual distribution identity and before/after
typed results. It was not rerun during record placement. sources.json identifies every retained
byte sequence. No wheel, model request/response, credential or raw stderr is committed.

The [recorded alignment table](2026-11-12-agents-api-interoperability/alignment.md) keeps the prior capability and topology decisions
with the SDK owner instead of requiring a workspace-only report.

Use a separate local test environment with the matching reviewed client source and its
managed-agents dependencies, plus the actual official openai3.49.0 distribution identified in
distribution.json. Run `python .agents/evidence/verify/2026-11-12-agents-api-interoperability/probe.py` from the repository root and save any new typed result in a
new dated evidence file. OpenAI is not a product dependency. The probe binds only loopback,
uses temporary SQLite and a synthetic local token, starts no Worker and calls no model/cloud.
Review the source before execution; its create/retrieve/list result is not full API coverage.

The after-projection result records default decoding success and remaining strict
Agent/harness/environment validation differences. A permissive default decoder is not a full
compatibility contract. The [SDK owner operations](../../notes/proposed/process/2026-11-12-agents-api-delivery-operations.md)
describe actual product gates and limits. Existing source versions/test results remain scoped
to their own captures, not an unexecuted current-head full run.

The retained model-protocol-preflight.json is a separate configured-endpoint synthetic check: Chat tool-result200 and Responses tool-result400 for the selected model. It is not a general claim about all providers/models, an actual Codex task, or a new probe during record placement. The template owner separately holds the real local Qwen task results.

The initial normal commit hook rejected the historical constant loopback token as a hardcoded assignment. The retained probe adds only an explicit synthetic test-fixture comment; its Python AST is identical to the original. sources.json preserves both byte hashes and that adaptation. No scanner rule was changed, no real credential was involved, and the recorded SDK result was not rerun or relabeled.
