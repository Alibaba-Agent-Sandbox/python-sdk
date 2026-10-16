# Decision: Pin the Alibaba-supported E2B behavior contract

Status: proposed

## Problem

Existing E2B users on Alibaba Express should migrate by installing this project, configuring the same connection settings and replacing package imports or the CLI executable prefix. Similar method names alone did not preserve synchronous calls, pagination, result models, errors, interpreter state or interactive terminal behavior. The project is unreleased; no legacy mode is required. Node SDK work is outside scope.

## Decision

`agent_sandbox.Sandbox` is the synchronous standard client; `AsyncSandbox` is asynchronous. `agent_sandbox.code_interpreter` adds the real interpreter protocol. The owned source port lives in `_standard` and `code_interpreter`, preserves MIT notices and source hashes, and has no E2B runtime dependency. `ProviderSandbox` explicitly exposes project provider/server/declarative extensions. Connection settings converge on E2B_API_KEY/API_URL/DOMAIN. Alibaba snapshot name filtering, qualified-name URL encoding and documented snapshot states are supported additions beyond the pinned Python baseline. Explicit SDK arguments retain precedence. Standard pagination, return values, exceptions, streaming, class/instance method dispatch, templates, network and conditional snapshots follow the pinned contract.

The reference is e2b 2.31.0 and e2b-code-interpreter 2.8.1. A source port is chosen explicitly: the project maintains the code and protocol, rather than installing or invoking the upstream SDK at runtime. This changes the earlier handwritten-only interpretation while retaining the independent distribution requirement. Imported/generated sources have narrow lint/type exclusions; maintained adapters and behavioral tests remain checked. Do not describe this as a fully handwritten protocol implementation.

Backend capabilities follow [Alibaba's compatibility statement](https://help.aliyun.com/zh/agent-sandbox/e2b-compatibility-explanation). Implement supported and conditional APIs; preserve backend restrictions and errors. Snapshots require MicroVM/allowlist; pause depends on runtime/allowlist; network updates are supported. Volume, Team, access-token/API-key management and MCP gateway are outside the supported migration path. No client surface implies that an unavailable backend capability works. Third-party hardcoded imports remain the integrator's responsibility.

## API Design

Standard API shapes, errors, pagination and handles follow the fixed reference. Project extensions have explicit entry points. Connection settings are canonical E2B_* names; Python timeouts use seconds. CLI options after the sandbox ID in exec are forwarded to the command. No compatibility switch or Node SDK export is introduced. Public migration details are in `docs/en/guide/migrate-from-e2b.md` and its Chinese counterpart.

## Alternatives considered

- Keep partial lookalike methods: fails import-only migration for existing synchronous applications and terminal workflows.
- Runtime dependency/re-export or subprocess invocation of E2B: gives another project control of installation, endpoint defaults and executable availability.
- Reimplement every generated schema and wire detail by hand: needlessly increases drift risk. Pin, attribute and maintain the source port instead.
- Pretend missing cloud capabilities are available: rejected; document backend restrictions and conditional verification.

## Dependencies

Pinned MIT source provenance and licenses accompany the implementation. No upstream E2B runtime installation is required. Cross-repository contract: https://github.com/Alibaba-Agent-Sandbox/agent-sandbox/issues/33. Owner Issue: https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/36.

## Test Strategy

Observable contract tests cover configuration, lifecycle shape, pagination, process errors/handles, file and interpreter models, and command routing. Real cloud scenarios verify the deployed protocol and side effects. Build and install artifacts must retain the implementation and licenses. Historical Python-CLI oracle assertions must be reconciled with the newly selected E2B behavior rather than presented as the new standard. Preserve original evidence captures and add new runs.

## Acceptance criteria

- Existing supported E2B Python calls require only import replacement and configured credentials/endpoints.
- Standard CLI sandbox/template operations preserve the pinned parser, terminal, output and cleanup behavior.
- Network changes have a verified real effect; account-dependent snapshot/pause tests explicitly state their prerequisites.
- Unit, lint, type, package, hygiene and repository-health gates pass, with real-cloud evidence and cleanup recorded.
- Bilingual migration docs, contributor contract and changelog agree. No Node SDK changes.

## Evidence

- [First full review](../../../evidence/verify/2026-10-16-e2b-review-round-one.md).
