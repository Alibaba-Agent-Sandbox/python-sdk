# Verification: E2B agent guidance review

- Date: 2026-10-16
- Change: https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
- Result: PASS (guidance correction); conditional backend success remains blocked as separately recorded
- Environment: current checkout; no credentials or cloud calls required for this review.

## What was verified

The distributed SDK/provider skills and llms.txt still taught the old root asynchronous Sandbox and retired credential names. They now distinguish synchronous standard Sandbox, AsyncSandbox/interpreter imports and explicit ProviderSandbox extensions. Standard signed URLs/handles/errors are no longer constrained by native-extension limitations. Template generation uses scaffold, and runtime/function prerequisites are explicit. Provider-specific keys remain isolated from the Express E2B_API_KEY.

## Commands run

- skill-creator `scripts/quick_validate.py agent-sandbox-sdk`: PASS.
- skill-creator `scripts/quick_validate.py agent-sandbox-provider`: PASS.
- Manual cross-check of public imports against the implemented/validated public contract and the passing 2035-client-test suite. No prose-matching tests added.
- Existing full Python 3.10/3.11/3.12 client/server/package/hygiene/Markdown matrix and isolated 354-shape contract passed on implementation head 3fa44beb. These guidance-only edits require their own latest remote documentation/gate result.

## Results

Skill names and invocation policies are preserved. The SDK skill starts with the standard migration example, then explicitly scopes existing provider/server material. Source/protocol details are kept in supporting references. Templates/engine notes link to maintained interfaces rather than hardcoding an obsolete socket.

## Cleanup

No resources created. Existing cloud-cleanup evidence and conditional backend restrictions remain unchanged.

## Problems found

This was a documentation omission in the migration change, corrected before acceptance. The current function still rejects pauseSession and lacks a snapshot-capable runtime; this record does not convert those failures into passes.

## Not verified

Successful enabled-function/MicroVM conditional scenarios and final acceptance/merge. Companion CLI: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40.
