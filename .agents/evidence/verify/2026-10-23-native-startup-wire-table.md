# Native startup identifier wire table

Result: PASS (fixture/documentation consistency); full native rerun remains required.

Follow-up to 899ca0de60326fed9774e399c95e61ca3f032abf. The CLI startup bridge now accepts backend-issued nonempty strings or positive safe integers, matching the project's ProcessChunk identifier union. The Python conformance fixture and both languages of provider authoring/design guidance now describe `exec.start` result `{process_id: string|integer}`. A startup acknowledgment is an empty chunk carrying the actual identifier; missing IDs and stdout cannot stand in for an acknowledgment. The fixture generator and existing consistency assertion receive the same single-field change. No transport implementation or maintained standard SDK source changes in this follow-up.

Validation: configured host-adapter/conformance tests PASS (103 passed, 5 unavailable live-provider prerequisites skipped); JSON parsing and `git diff --check` PASS. The prior scoped implementation passed 56 regressions and all 98 configured source files under mypy. Documentation relative links are checked by repository CI; no source/runtime/cloud pass is inferred from fixture consistency.

The first consistency run exposed the generator and old string-only assertion (2 failures, 101 passes); those sources were synchronized before the passing rerun.
