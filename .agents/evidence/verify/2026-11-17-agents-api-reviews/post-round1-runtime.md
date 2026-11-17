# Managed Agent API — independent post-implementation runtime review, round 1

Date: 2026-11-17. Result: PARTIAL / acceptance remains blocked.

## Reviewed scope

Read the candidate six template configurations, standalone bootstrap, release initialization and credential forwarding; SDK public Turn projection/Worker event changes; native Qoder, OpenCode and official DeepSeek Harness adapters; shared credential descriptors and ProcessDomain. Scope is the current task diff against the existing PR heads, not a released a8 artifact.

## Findings and disposition

1. **Actual consumer defect, unresolved:** SDK public `api.capability.parse_template_data` rejects the new `agents-api-codex/template.yaml` at schema root. Independently reproduced using the candidate installed SDK and actual YAML. The SDK packages the old ef695 contract and still consumes singular `sandbox.template/instance/start/ready`; current producer is named-resource `vars/sandbox/serving`. Managed backend and run.py explicit create/start paths do not parse this YAML, so this does not invalidate those paths. Replacing schema bytes alone would break the internal managed-instance compiler. Root/protocol reviewer were asked to preserve a precise open consumer gap and prevent a8 from claiming finished YAML migration.
2. **Adapter capability gap:** OpenCodeParser originally emitted tool_start plus tool_end for every tool_use record. Actual OpenCode v1 CLI emits completed-tool records, so the original guard cannot enforce maxToolSeconds from the actual native tool start. Root/Harness reviewer confirmed the source/probe boundary. They are correcting native outcome mapping/capability statements and adding user-facing limits to the template, both topics and guide. Overall Turn deadline/cancellation/process cleanup remain applicable. Do not fabricate real-time starts to imply full per-tool timing.
3. **Descriptor mismatch, non-blocking:** template diagnostic binary qodercli differed from adapter qoder. Independent Harness reviewer installed the exact npm package and confirmed both bin names; it is not a missing binary defect. Root accepted one canonical qoder spelling and corrected the official help URL.
4. **Publication/E2E blockers remain:** a8 is unpublished; both images now correctly require it instead of installing a7 without the new contract. Docker, final PostgreSQL-backed FC publication, stable alias/timer, retained old Session upgrade, six vendor/model native tasks and owned cloud cleanup have not been completed for this candidate. Source/config tests cannot close those gates.

## Independent checks

- `python -m unittest discover -s scripts -p test_agents_api_family.py -v`: PASS, 2 tests including six subcases. Each downloaded standalone project removes registry.yaml, compiles its bootstrap, creates a real local SQLite-backed ManagedService Session and passes that real frozen Session to ManagedExpressBackend.create up to the mocked native-infrastructure boundary. This tests the actual allowlist/settings chain, not a fabricated Session dict; it is not native cloud I/O.
- Project-independent stdlib raw HTTP control: raw GET501/header-only POST timeout, same listener http.client/urllib-no-proxy GET200. Actual source and typed results are retained in the SDK engineering record. This reproduces eight existing raw-test symptoms outside project code; the interception root cause is unproven and those tests remain failures.
- Read Turn projection and same-name events. Stable frozen Session agent identity, nullable historical start and reconstructed host in_progress.turn are reasonable. Saved Agent identity is never re-looked-up during projection; no subagent capability is introduced.

## Review decision

The minimal source approach is reasonable after the above corrections. Keep the shared receipt/epoch/process-domain and no-blind-replay design. Uniform public protocol does not imply identical native authentication, token streaming or tool-start observation. A second post-change review is required after these findings; no final completion or release approval is given in this round.
