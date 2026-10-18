# Verification: provider schema composition

- Date:2026-10-18
- Result:PARTIAL; local/package/configured cloud PASS, hosted gates pending.
- Base:e86cb0b, accepted native/auth/replay source.

Fresh process:bare package import loads neither Pydantic nor registry; builtin
schema resolves without registry:PASS. Config focused repeat43 PASS.
Initial extraction missed a builtin constant in the moved class property;
existing config/provider tests exposed it, corrected by a lazy lower-level
constant import before the final full/cloud repeats. No initial failure is
called a pass. Final client/server lint/format/mypy PASS,81 client/56 server files.
Full client2083 PASS /21 SKIP /10 DESELECTED,two existing subprocess/event-loop
warnings. Both distributions/twine/py.typed/combined wheel imports PASS.
Fresh configured full cloud116 PASS /4 SKIP /1 XFAIL /2 DESELECTED,exit0 in337.05s;
janitor zero candidates/zero total resources. Unconfigured native vendors are
skips. Health106 PASS /1 existing WARN /0 FAIL; hygiene PASS. Latest-head hosted
three-interpreter client/server, package/links/hygiene and review remain required.
No config key, source vector, dependency or provider receipt format is changed.

Hosted a852139 Python3.11 initially failed the unrelated HTTP/PTY fixture port
reuse race. The deterministic fix landed independently in PR64 after9/9 checks,
merge5d700d6eaa1fd75f62297b3f289be2a45be772b4. Ordinary merge of current main
retains that regression and accepted PR62 retry docs (merge3c27c67568e7c53165ea60b32b109f208cca22ad), resolving only adjacent index/architecture paragraphs by preserving both. Move those already merged owner notes to implemented; original evidence remains unchanged. This composition source and the previously successful real-cloud run are unchanged by the fixture/docs merge. Fresh focused/health/latest hosted matrix remain required before acceptance; no failed job was simply rerun without its cause being fixed.
