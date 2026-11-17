# Decision: Native harness adapters behind one managed protocol

Status: proposed

## Problem

Managed Agents accepts only Codex and Qwen Code. Renamed templates cannot use Claude,
Qoder, OpenCode or official DeepSeek Harness, and the universal OPENAI credential mapping
would misrepresent their native authentication and model protocols.

## Decision

Add Qoder 1.1.90, OpenCode 1.19.5 and official DeepSeek Harness 0.2.2-rc.1 invocation/parser
adapters. Make existing Claude Code available through the managed bridge. Keep the six
canonical adapter IDs behind one durable Session/submission contract. Each Worker binds
one model and harness and injects exactly its known native environment names. Qoder uses
a native PAT and no fake model endpoint. DSH uses its official Messages route and native
headless session restoration, rather than the older project-owned DeepSeek tool loop.

The client maps credentials using a dependency-free model helper. The standalone server
retains its own fixed descriptors because it must remain installable without the client;
a parity test checks the two descriptors. Native parser terminal checks supplement actual
process exit and existing process-domain/reconciliation rules. New adapters remain
experimental pending real account/model and hosting acceptance.

OpenCode's native JSON emits tools only at completion. Record completed items atomically,
declare completion-only tool events and no live per-tool timeout, and preserve the overall
run deadline. Reject its unsupported workspace_write mode instead of widening permissions.

## API Design

Internal Worker model binding remains `{adapter, model, apiKey, baseUrl}`. `baseUrl` is
required for model APIs and omitted/empty for Qoder's native service. The existing public
managed API envelopes do not change. Canonical adapter IDs are `codex`, `qwen-code`,
`claude-code`, `qoder`, `opencode` and `deepseek-harness`.

## Alternatives considered

- Copy six complete Gateway implementations: duplicates state/lifecycle behavior.
- Wrap all CLIs as generic text commands: loses native session/error/tool semantics.
- Treat all credentials as OPENAI keys: breaks native Qoder/Claude/DeepSeek authentication.
- Import client configuration from the standalone server: breaks package independence.

## Dependencies

Existing stdlib-only AgentRuntime adapter boundary and managed bridge; official native CLI
packages installed by each template. Client/server source metadata moves together to a8;
this is a candidate, not proof that a8 exists on PyPI. Existing release artifacts remain unchanged.

## Test Strategy

Invocation/parser/error/resume/credential/parity unit tests; installed real CLI version/help
and unauthenticated rejection; native subprocesses against bounded loopback model fixtures
where feasible, clearly separated from real-model acceptance. Required owner suite, lint,
typecheck, build/packaging and real cloud/model checks remain necessary.

## Acceptance criteria

Six bindings preserve one protocol and exact native identity. Credentials remain out of argv,
generated files and Gateway public responses. Native nonzero, missing terminal, malformed
configuration and unconfirmed stop never become success. Each real-model path demonstrates
two turns, independent generated artifact execution, cancellation and owned cleanup. Revised
FC/PostgreSQL deployment and old-session upgrade pass before full delivery is claimed.

## Evidence

- [Verification](../../../evidence/verify/2026-11-17-managed-harness-adapters.md).
- [Installed native components and real-model preflight](../../../evidence/verify/2026-11-17-native-harness-components.md).
