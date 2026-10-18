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
