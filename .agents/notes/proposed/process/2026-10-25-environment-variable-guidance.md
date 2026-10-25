# Decision: Explain environment injection with current public interfaces

Status: proposed

## Problem

The bilingual environment guide promises universal creation-time inheritance,
assumes two independent process trees and describes Express terminal `--env` as
sandbox-lifetime injection. Its application HTTP examples omit the application
credential and its snippets do not identify the asynchronous ProviderSandbox.

## Decision

Correct only the bilingual environment guides. Describe creation inputs,
per-process overrides and an already running application's environment using
ordinary process inheritance. Show explicit ProviderSandbox ownership/cleanup
and authenticated application binding with existing typed environment methods.
Keep real interpreter and network APIs, with their provider-specific scope, and
keep the exec plugin's actual initialize/allowlist contract. Historical command
maps retain their explicit historical scope and current-guide links.

## API Design

N/A — no runtime, docstring, API, dependency or package-version change.

## Alternatives considered

- Change the runtime or add a global environment API: unnecessary for correcting
  misleading documentation and outside this change.
- Replace every interpreter/network/plugin reference as obsolete: those public
  interfaces are real; their scope and credentials need accurate explanation.
- Update external-product historical comparison tables: outside this guide fix.

## Dependencies

- https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/135
- https://github.com/Alibaba-Agent-Sandbox/python-sdk/releases/tag/v0.4.0a6
- https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/releases/tag/v0.5.6

## Test Strategy

Use official SDK6 imports/signatures and the official CLI6 help/parser without
cloud creation. Compile both guides' Python fragments, exercise typed environment
methods against a real local server, verify document links/health/hygiene and run
normal full SDK PR gates. Record a startup-probe failure separately from any
subsequent local HTTP result. No new cloud run or package publication is requested.

## Acceptance criteria

- The two translations describe the same current behavior and owned cleanup.
- No terminal flag is presented as lifetime creation injection.
- Application examples supply explicit credentials through the existing binding.
- Provider interpreter support and exec initialization remain accurately scoped.
- Owner record, scoped real-component evidence, latest full CI and review pass.

## Evidence

- [Verification](../../../evidence/verify/2026-10-25-environment-variable-guidance.md)
