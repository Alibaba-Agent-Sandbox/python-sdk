# Decision: Provision conditional Express acceptance fixtures

Status: proposed

## Problem
Conditional acceptance previously stopped after failures on a generation1 template;
consumer documentation also depends on the old asynchronous root import/CLI flags.
A valid local runtime key alone cannot select the generation or enable an allowlist.

## Decision
Add independently selectable E2E_PAUSE_TEMPLATE and E2E_SNAPSHOT_TEMPLATE real tests.
Assert running→paused→connected-running and in-memory nonce/file preservation;
assert snapshot creation/list/restore/clone isolation/deletion with owned cleanup.
Missing prerequisites skip only their own scenario and remain acceptance gaps.
Provision only a uniquely named task fixture; inspect build state and preserve
server admission errors. Do not modify existing templates, account policy or feature
flags. Use local ignored credentials; keep resource identifiers out of evidence.
Consumers use the stable native api.sandbox import for provider/server examples
and choose CLI syntax from installed help, preserving working main installations.

## API Design
No public client API changes. Existing OpenAPI CreateTemplate uses sandboxConfig
generation2, official same-region runtime-v2/base image, explicit15360MB disk.
Keep native ABX settings and standard-entry E2B mapping separate.

## Alternatives considered
Repeating generation1 probes cannot test MicroVM behavior. Silently skipping all
conditional tests or changing a gate to pass would hide missing acceptance.
Changing existing cloud templates risks other sessions; use an isolated fixture.

## Dependencies
https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/47
https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/pull/40
Official contracts: https://help.aliyun.com/zh/agent-sandbox/build-and-manage-custom-templates-with-code
and https://www.alibabacloud.com/help/en/agent-sandbox/e2b-compatibility-explanation

## Test Strategy
Run required owner checks; actual local provisioning and cloud probes with exact
source/artifact receipts; inspect owned resources after cleanup. Record failures,
skips and platform allowlist restrictions separately from passes. Check consumer
imports against both accepted-main and standard-candidate installations.

## Acceptance criteria
Runnable bilingual guide and scoped consumer migration records; required current
head CI passes. Successful conditional paths require actual enabled fixtures; if
admission is rejected, record the exact sanitized failure and retained test design.

## Evidence
[Verification](../../../evidence/verify/2026-10-19-conditional-acceptance.md).
