# Decision: document standalone SandboxServer policy loading

Status: proposed

## Problem

Actual PR164 Markdown links CI on b988 failed on two removed server-policy anchors. Reviewing
the source context found fourteen active bilingual pages that still described a root `server`
resource block or automatic template-to-policy compilation, neither admitted by template v1.

## Decision

Correct seven active topics in both languages, retaining ordinary `template.yaml` as the single
resource entry. Present optional advanced SandboxServer restrictions as a standalone policy
with real loading commands. Preserve existing JSON/YAML policy support and Python APIs.

## API Design

No runtime API changes. JSON policy examples contain their actual policy keys without the
removed wrapper. `ABX_SERVER_POLICY`, `ABX_SERVER_POLICY_FILE`, `serve --policy`, `check-config`
and `ServerPolicy` retain their existing meanings. An authored image explicitly copies the
file into the guest path. Managed Agents API bridge/bootstrap controls are separate.

## Alternatives considered

Only fixing the two fragments leaves executable instructions that v1 rejects. Reintroducing
a root resource block or automatic compiler adds an unnecessary configuration contract.
Removing standalone YAML policy support contradicts the actual runtime and is not justified.
Historical/archive/design documents remain unchanged.

## Dependencies

[SDK PR164](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/164) and
[delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).
Actual existing `ServerPolicy.from_file` supports JSON always and YAML when PyYAML is installed.
No dependency, package release, runtime, Server recipe or Guest image change is required.

## Test Strategy

Run the same actual lychee0.24.2 offline/fragments command as the failed remote job. Validate
complete documented policy examples with real ServerPolicy, actual check-config in both
languages and a real standalone YAML file. Check active-page obsolete claims, relative links,
repository health/hygiene, scoped secret/diff checks and exact runtime-source immutability.

## Acceptance criteria

The fourteen pages agree on supported loading and fields. The existing explicit v1 anchor
resolves in both languages. Examples are actual standalone policies and correctly loaded guest
files. JSON/YAML/runtime API support remains accurate. Only documentation/records are changed;
new remote CI remains bound to its actual head, not inferred from the local result.

## Evidence

[Verification](../../../evidence/verify/2026-11-12-standalone-policy-docs.md).
