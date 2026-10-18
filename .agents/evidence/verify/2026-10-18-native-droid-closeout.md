# Verification: native builtin delivery and Droid follow-up

- Date:2026-10-18
- Result:PASS for the documented native/source-runtime scope; hosted record gates pending.

Replay PR54 merged3d4ac95, API-key contract PR56 mergeda60e9ad and native builtin
PR57 mergede86cb0b after their exact reviewed heads passed all nine hosted
checks each. Their original evidence files remain immutable; accepted ADRs now
move to implemented with status and current indexes updated together.

Native source76268024fb6e046b78ebc0f797ebcaf162ef2a55 completed fresh cloud
116 PASS /4 SKIP /1 XFAIL /2 DESELECTED with zero resources in janitor readback.
The additional real Droid0.241.1 source-runtime installation/polling test now
passes all nine recorded checks, including SDK health, exact version/keyless
setup, external HTTP and owned cleanup. Independent readonly platform list:
zero source-runtime-droid resources remain. No model key/call or image/template
deployment was involved. The exact original historical root cause is not inferred.

Canonical template-owner proof: [https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/aaef5b63ee11b6b76b93b7ebbc8ad2530b21f576/.agents/evidence/verify/2026-10-18-droid-native-runtime.md](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/blob/aaef5b63ee11b6b76b93b7ebbc8ad2530b21f576/.agents/evidence/verify/2026-10-18-droid-native-runtime.md).
This satisfies the remaining reproduction/cleanup acceptance for
https://github.com/Alibaba-Agent-Sandbox/python-sdk/issues/35 once this record lands.
No native unconfigured vendor or canonical L2/L3 badge is claimed.

Repository health106 PASS /1 existing WARN /0 FAIL; hygiene and changed-local-link
checks PASS. Latest-head hosted record gates remain pending before merge.
