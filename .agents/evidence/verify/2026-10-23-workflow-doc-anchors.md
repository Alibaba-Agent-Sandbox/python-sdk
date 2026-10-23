# Verification: aggregated workflow reference anchors

Date: 2026-10-23. Result: PASS for the corrected source anchor; final aggregation readback is a separate consumer check.

Readback of the 24 updated current design/reference document routes found the existing E9 error-code link depended on differing GitHub and registry heading slug rules. Add an explicit canonical E9 anchor to both English and Chinese error-code references. This keeps the same document link target under both renderers and changes no runtime API or compatibility path. Both explicit IDs match the existing api-reference links; git diff --check passed. Registry will regenerate from this real source revision and verify the emitted route/fragment again.
