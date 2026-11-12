# Decision: share YAML1.2 Core admission for public v1 files

Status: proposed

## Problem

The Node and Python v1 readers disagree before the shared object schema runs. Python's default
safe loader converts plain `on` to boolean and dates to non-JSON objects, while accepting
repeated keys, aliases and UTF16. Six public SDK behavior regressions reproduce these issues
in prepared launch, cached discovery and registry file loading.

## Decision

Copy the template owner's pure `parse_yaml_v1` and raw YAML text vectors exactly with the
immutable source lock. Use `yamlcore==0.1.1`, a small PyYAML-dependent Core1.2 loader, instead of
maintaining another resolver. Limit file reads to1MiB+1 bytes before parsing. Apply the same
strict UTF8, duplicate/alias/tag and finite JSON/string-key admission in every public v1 file
entry before validation, journaling or resource creation.

## API Design

An internal bounded I/O helper returns original bytes plus the shared parsed object. The launch
path preserves its existing original-byte identity; dict/resolved JSON input is unchanged.
Public template registry and cache discovery use the same helper. Native Devs expressions
remain literal strings here and require the real Devs parser for evaluation. Unrelated provider
configuration/catalog readers retain their existing contracts.

## Alternatives considered

- Ask users to quote scalars differently for Python: rejected because the same public YAML
  must retain the same meaning across consumers.
- Three custom handwritten resolver implementations: rejected as duplicate specification.
- A complete new YAML framework or installing the CLI: unnecessary for this bounded file
  admission; use the reviewed minimal Core loader and existing schema.
- Read the whole file before checking size: rejected because it does not bound input allocation.

## Dependencies

Base client dependency `yamlcore==0.1.1`, alongside existing PyYAML. Shared reader and raw
vectors are pinned to the template-owner commit recorded in `template_contract/source.json`.
Part of [delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309)
and the [canonical contract PR310](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/pull/310).
No package release or new runtime service is introduced. Managed Server consumes compiledJSON,
so this file-entry fix does not require another Guest/model/cloud matrix.

## Test Strategy

Run actual raw text vectors through the real installed Core loader. Assert all three public
paths preserve scalar values; invalid encoding, repeated keys, aliases and oversized input fail
before Sandbox/journal creation. Check error strings omit source values. Verify immutable owner
bytes, actual built wheel contents/dependency metadata and fresh environment installation with
pipcheck. Run relevant discovery/launch/schema tests and repository static/health gates.

## Acceptance criteria

- Owner lock and bundled reader/vector bytes match the immutable producer.
- Public file paths agree with Node's shared text cases and keep literal env values unchanged.
- Bounded strict parsing fails before resource or journal side effects without source leakage.
- A fresh installed client wheel includes the actual reader, vectors and Core dependency.
- Historical full-suite scope remains explicit; final-head remote CI/cloud gates are separate.

## Evidence

[Verification](../../../evidence/verify/2026-11-12-template-yaml-core-reader.md).
