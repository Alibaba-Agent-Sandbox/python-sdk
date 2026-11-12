# Verification: standalone policy documentation

Date: 2026-11-12. Scope: documentation only, extending
`b988d2a76057b6202d836ec329cc0bd90a572b26`. Part of
[SDK PR164](https://github.com/Alibaba-Agent-Sandbox/python-sdk/pull/164) and
[delivery309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

The actual failed [Markdown job](https://github.com/Alibaba-Agent-Sandbox/python-sdk/actions/runs/43283073913/job/131409205320)
reports exactly two missing fragments in bilingual file-and-command-controls links to
`template-yaml-spec.md`. Their surrounding instructions also teach the removed root server
block. Independent adversarial review approved correcting all seven active bilingual topics.

Changes preserve standalone JSON policy, YAML policy with PyYAML, Python policy APIs and actual
server loading/validation commands. Advanced policy is optional; normal resources retain one
manifest. The image example explicitly copies its guest policy file. Managed bridge route
configuration is not represented as SandboxServer policy. Existing archive/design/history is
unchanged. The related active ports prerequisite now refers to real Provider endpoint operations.

Local verification:

- Actual lychee0.24.2, same offline/include-fragments/exclude-agents arguments as remote CI:
  1502 links total,458 unique,1190 OK,312 excluded,0 errors; exit0.
- Real ServerPolicy:12 complete JSON/YAML examples plus2 Python policy objects validate/bind.
  Actual `check-config --policy` runs for both languages; a separate real YAML policy file loads.
- All14 active pages checked:zero root server examples and removed reference fragments.
- Repository health/hygiene and staged secret/diff checks are recorded before scoped commit.

The platform artifact mount refused an executable chmod for the downloaded checker; an identical
binary was executed from temporary tool storage. No product permission or global setting was
changed. No runtime tests or cloud/model matrix are repeated merely for prose.

The final b988 Server image has separately passed actual image/local HTTP/SQLite/Core probes and
pipcheck; this documentation increment changes no image runtime bytes and needs no new recipe
pin/build. The older c550 image evidence remains historical. Final-head remote CI and the
required cloud acceptance gate are not claimed by these documentation checks.
