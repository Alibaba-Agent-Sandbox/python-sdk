# Independent workflow second-round confirmation

Date: 2026-10-23
Result: PASS (reviewed local scope)

Scope: api/workflow.py cleanup journal failure handling and api/server_client.py fixed/added query key normalization, with the associated focused tests on the template workflow task branch. This is independent follow-up verification of the second-round findings; it does not replace real provider E2E, full repository CI or review requirements.
Environment: Python 3.11, editable task client/server distributions and httpx MockTransport for recording whether a request was sent.

Independent counterexamples were rerun outside the repository tests:

- PASS: a durable created resource ID was written before every subsequent journal append was forced to fail with OSError. Owned sandbox deletion was still attempted exactly once, both with a successful and failing application-client close. The original resource ID remained durable; close reported journal-write-failed and did not mark itself clean.
- PASS: duplicate base query keys, multiple nested percent-encoded aliases and case-equivalent aliases were rejected. Added parameters could not collide with a fixed key or another added key after normalization. No request reached the recording transport for any rejected case.
- PASS: the positive HTTP request retained the full sandbox prefix and exact opaque query values sig=100%25 and opaque=%2525.
- PASS: python -m pytest client-sdk/tests/test_api/test_application_binding.py client-sdk/tests/test_api/test_workflow_launch.py -q: 50 passed.
- No remaining P0/P1 was found in these two corrected areas. Prior first-round command-gate finding 7 was withdrawn: tuple rules use any(), so exec.run-only was already accepted; it was not a reproduced defect.

No live provider, cloud resource, credential, deployment or release was used. The independent request-recorder test validates rejection before I/O and signature byte preservation; it is not cloud acceptance. The broader first-round confirmations and product E2E belong in the implementation evidence.
