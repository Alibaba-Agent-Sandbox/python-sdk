"""Run every independent-security PoC and report VULNERABLE / HELD.

    python3 run_all.py            # v2.1: same as --strict (every PoC is HELD against the fixed spike)
    python3 run_all.py --strict   # exit 1 if ANY check is VULNERABLE (the release gate)
    python3 run_all.py IS-P2      # only checks whose id starts with the given prefix

A PoC asserts the SECURE behaviour, so VULNERABLE == the assertion failed == the finding reproduces.
"""
from __future__ import annotations

import importlib
import sys
import traceback

MODULES = ["poc_policy", "poc_paths", "poc_commands", "poc_transport", "poc_misc", "poc_held"]

# Everything listed here reproduces today (finding open).  Ids prefixed HELD- must keep passing.
HELD_PREFIX = "HELD-"


def main(argv: list[str]) -> int:
    strict = True  # v2.1: all PoCs hold; --strict is kept as an explicit spelling of the default
    prefixes = [a for a in argv if not a.startswith("--")]
    results = []
    for name in MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name == name:
                continue
            raise
        for cid, fn in mod.CHECKS:
            if prefixes and not any(cid.startswith(p) for p in prefixes):
                continue
            try:
                fn()
                status, note = "HELD", ""
            except AssertionError as exc:
                status, note = "VULNERABLE", str(exc)
            except Exception as exc:  # a crash is itself a finding (undefined behaviour) but is reported apart
                status, note = "ERROR", f"{type(exc).__name__}: {exc}"
                traceback.print_exc(limit=2)
            results.append((cid, status, note))
            print(f"{status:10s} {cid:9s} {note}")
    vuln = [r for r in results if r[1] == "VULNERABLE"]
    held = [r for r in results if r[1] == "HELD"]
    err = [r for r in results if r[1] == "ERROR"]
    print(f"\n{len(vuln)} vulnerable, {len(held)} held, {len(err)} error, {len(results)} total")
    bad_held = [r for r in results if r[0].startswith(HELD_PREFIX) and r[1] != "HELD"]
    if bad_held:
        print("REGRESSION: a HELD- check no longer holds:", [r[0] for r in bad_held])
        return 1
    if strict and (vuln or err):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
