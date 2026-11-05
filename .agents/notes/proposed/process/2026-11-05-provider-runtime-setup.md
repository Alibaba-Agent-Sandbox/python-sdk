# Decision: Explain provider runtime setup and performance boundaries

Status: proposed

## Problem

Python users can manage Node providers from a Python module, but that entry does not install the local Node engine. The provider guide did not give a complete client setup route and could imply that Python-only management meant a Python-only runtime. It also omitted the user-visible latency and memory tradeoffs of the bridge.

## Decision

Document the existing standalone abx installer as the recommended way to supply an embedded Node runtime, with npm as an alternative for machines already running Node. State Python, platform, PATH and installation-tool requirements, distinguish registry archives from Git sources, and keep server deployment separate from client preparation. Explain engine discovery/reuse and performance measurement boundaries without presenting a synthetic probe as a product benchmark. Provide a complete OpenSandbox create/command/file/cleanup example and identify service credentials.

The current SDK has no published opensandbox extra or automatic engine download. Do not advertise either. Changing package delivery or runtime behavior requires a separate implementation and its own verification.

## API Design

N/A — this decision does not involve API changes. Existing ProviderSandbox and Python provider-management commands remain unchanged.

## Alternatives considered

- Require every Python user to install Node and npm separately: unnecessary when the standalone executable embeds the runtime.
- Publish a one-command pip-extra recipe before runtime/provider packages exist: rejected because dependency declarations alone do not provide those artifacts.
- Treat a loopback forwarding delta as the SDK's fixed overhead: rejected because it omits real engine/provider work and workload variation.
- Retain a CLI-launched sandbox as the only OpenSandbox example: unnecessarily hides the direct lifecycle API and its cleanup obligations.

## Dependencies

The existing CLI release installers and standalone artifacts are owned by https://github.com/Alibaba-Agent-Sandbox/agent-sandbox . OpenSandbox source and credential configuration are owned by https://github.com/Alibaba-Agent-Sandbox/awesome-providers . No Python runtime dependencies, package versions or production source files change.

## Test Strategy

Check bilingual parity, Python-example syntax, shell-installer command syntax, local document targets, repository health and hygiene. Validate the documented public binary route and a real plugin handshake separately from server/cloud operations. Retain available original synthetic probe sources/results only as engineering evidence. Required current-head CI and review remain gates.

## Acceptance criteria

- Both provider guides explain why Node providers still use a Node engine from Python and distinguish that from a separate Node installation.
- Existing standalone and npm setup routes, Python version, supported platforms, PATH/ABX_BIN and registry-versus-Git requirements are explicit.
- OpenSandbox defaults, service/key prerequisites and resource cleanup are unambiguous.
- Performance text separates cold/warm behavior and workload effects without a universal millisecond or percentage promise.
- Proposed installation extras are not described as available; existing public contracts and unrelated files remain unchanged.
- Document checks and actual verification outcomes are recorded; remote gates pass before merge.

## Evidence

[Verification](../../../evidence/verify/2026-11-05-provider-runtime-setup.md).
