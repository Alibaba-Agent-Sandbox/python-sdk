# Verification: installed native Harness components

- Date: 2026-11-17
- Result: PARTIAL
- Source: client/server a8 candidate; official OpenCode 1.19.5 and DeepSeek Harness
  0.2.2-rc.1 packages; Qoder CLI 1.1.90.
- Environment: Linux, Python 3.12.13; official Node 24.16.0 archive verified independently
  against the checksum used by the template image.

## Native CLI and continuation

Installed the actual npm packages in an isolated local prefix. Exact version probes passed
for `qoder`, `opencode` and `dsh`; the installed package's headless help was inspected.
The actual Qoder version lacks a max-turns flag and plan permission mode, so the adapter
uses supported arguments rather than copying an incompatible documentation example.
Qoder without credentials rejected with exit 1 and a native authentication error. No PAT
was supplied or native Qoder model task claimed.

Executed both OpenCode and official DSH through their new SDK adapters against one bounded
loopback HTTP server with deterministic model responses. Each CLI completed two invocations
using the exact same native session ID. The second actual model HTTP request contained
the first turn's marker and the follow-up prompt. Both processes exited zero, and parsers
observed successful native terminal results. The DSH test used its Messages transport and
explicit DEEPSEEK_BASE_URL; it did not substitute the older repository-owned DeepSeek loop.

Reproduction, using caller-supplied installed binary directories:

```bash
python .agents/evidence/verify/2026-11-17-native-harness-components/loopback.py \
  --native-bin "$NATIVE_BIN" --node-bin "$NODE_BIN"
```

- [Sanitized result](2026-11-17-native-harness-components/loopback-result.jsonl)
- [Reproduction](2026-11-17-native-harness-components/loopback.py)
- Native event envelope fixtures under `server-sdk/tests/fixtures/native-harnesses/`
  normalize IDs, paths and timestamps and are covered by parser regression tests.

This proves native command construction, protocol transport and persisted continuation
against a controlled model fixture. It does not prove model quality, provider account
permissions, generated business artifacts, cloud Sandbox execution or FC hosting.

## Attempted real-model acceptance

The owner authorized one existing-endpoint discovery followed by one two-turn OpenCode
file task, without creating cloud resources or trying a model matrix. The credentials
were loaded only in the child process from the existing gitignored configuration, with
neither credential nor base URL printed or saved. The single `GET /models` attempt failed
with `ConnectError`. No model was selected and no task was submitted. Generated-file and
independent-computation checks therefore remain unrun. No process belonging to the attempt
remained after cleanup.

[Sanitized failed preflight](2026-11-17-native-harness-components/real-model-result.json)
retains the failure and its unrun downstream checks.

## Review findings addressed

OpenCode's actual JSON interface reports tool use at completion. Its parser now emits an
atomic completion record; the runtime publishes terminal item status immediately and
does not fabricate a live tool start or a per-tool timer. Native duration is retained
when present. Public adapter capabilities report completion-only tool events and no live
per-tool timeout for this interface. Overall run deadlines and owned-process cleanup remain.

Independent review also found that mapping `workspace_write` to a blanket OpenCode allow
policy would widen explicit permission intent. The adapter now rejects that unsupported
mode rather than treating it as full access; read-only and full-access are distinct.

## Cleanup and limits

Only local CLI processes and temporary workspaces were used. The reproduction closes its
loopback listener and removes its owned temporary homes after normal completion. No cloud
resources were created. Six native real-account/model paths, generated artifacts, active
tool cancellation, current FC/PostgreSQL deployment/upgrade and published image/package
verification remain separate required acceptance work.
