# Workflow contract foundation verification

Scope: canonical contract 1, template specification 4, pure Python planner and identity helpers.

- Python 3.11: `pytest client-sdk/tests/test_workflows -q` — 33 passed.
- Canonical input set: 29 vectors. CLI implementer independently reported exact normalized JSON parity for all 29; final integrated checks are recorded in a later evidence file.
- Runtime, cloud, packaging and full repository CI are not established by this foundation run. This is an intermediate record, not execution certification.
