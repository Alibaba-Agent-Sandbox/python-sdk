# Verification: SDK template consumer boundary

- Date: 2026-11-17
- Result: PARTIAL
- Change: AGENTS.md, eight English/Chinese documentation pairs and the contributor-boundary
  decision; no YAML runtime behavior changed.

## Evidence

Read the packaged source.json, schema and normalizer; the SDK still admits root
`sandbox/deployment/application` and consumes `sandbox.template/instance/start/ready`.
The current template owner instead admits `vars/sandbox/serving` with named resources.
`api/template.py` imports that older normalizer. `models/template.py` uses it for
discovery, and `models/managed_instance.py` constructs an older private snapshot.
Therefore synchronizing schema bytes alone would break additional consumers.

Current template run.py files use ProviderSandbox.create and start_server directly.
The managed Express backend creates instances from explicit frozen settings and does
not pass a template.yaml to launch_template. The CLI named-resource engine uses its
own JavaScript consumer, without calling this Python parser. The mismatch is a real
SDK YAML/discovery migration gap; it does not block those explicit managed paths.

## Commands and results

- `rg` traced launch_template/template_contract callers in SDK, templates and CLI.
- Python inspected both schema root/property sets directly; mismatch confirmed.
- `bash scripts/check-repo-health.sh --quiet`: 106 PASS, one existing recommended
  release-runbook warning, no failures. `make hygiene` and `git diff --check` passed.
- Updated workflow, field reference, architecture, build/deploy, authoring, SDK usage,
  API reference and managed instance descriptions in both languages.
- Owner Issue309 remains open: https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309.

## Not verified

No code migration, new public YAML support, cloud resource operation, model execution
or package publication was performed by this documentation-only correction. The
underlying consumer gap remains open and must not be described as completed.

## Scoped secret review

The coordinator compared exact configured secret/endpoint values against six repository
working trees and the added diff. No new matching value was introduced. Existing
configured-domain baseline matches in the two sdk-usage language files predate this
change and remain unchanged; no endpoint value is recorded here or replaced globally.
