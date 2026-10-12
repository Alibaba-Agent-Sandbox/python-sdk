import sys, os
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
RES = []
def check(name, cond, extra=""):
    RES.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if (extra and not cond) else ""))
def done(scn):
    ok = sum(1 for _, c in RES if c)
    print(f"== {scn}: {ok}/{len(RES)}")
    return ok == len(RES)
