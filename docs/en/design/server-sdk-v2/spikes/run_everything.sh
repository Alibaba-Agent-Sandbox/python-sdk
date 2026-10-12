#!/usr/bin/env bash
# Full self-regression of the design spikes. PoCs and unit suites use the system python (stdlib only);
# agents_sdk_check.py needs a venv with `openai` (python3 -m virtualenv -q "$OAI_VENV" && "$OAI_VENV/bin/pip" install openai).
cd "$(dirname "$0")"; fail=0
run() { echo "== $*"; "$@" > /tmp/ebx-spike.out 2>&1; rc=$?; tail -n 2 /tmp/ebx-spike.out; [ $rc -ne 0 ] && { fail=1; grep -a "^FAIL\|Error" /tmp/ebx-spike.out | head; }; return 0; }
run python3 independent-security/run_all.py --strict
for t in tests_proto tests_catalog tests_round4 attack1 attack2 attack3 tests_v21 tests_install tests_parity tests_disposition; do run python3 $t.py; done
for s in ai_consumer/s[1-8]_*.py; do run python3 $s; done
run python3 templates/run_all.py
PY=${OAI_PY:-${OAI_VENV:-${TMPDIR:-/tmp}/oai-venv}/bin/python}
[ -x "$PY" ] && run "$PY" agents_sdk_check.py || echo "SKIP agents_sdk_check.py (no $PY)"
exit $fail
