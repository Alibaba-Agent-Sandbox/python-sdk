"""Compare public callable shapes against separately installed, pinned E2B clients.

Usage: python scripts/check_standard_contract.py --reference-python /path/to/python
The reference interpreter is a development oracle, never a runtime dependency.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import re
import subprocess
import sys


def contract(base: str, interpreter: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for module_name, reference_name in [(base, "base"), (interpreter, "interpreter")]:
        module = importlib.import_module(module_name)
        names = getattr(module, "__all__", None)
        if names is None:
            names = [name for name in vars(module) if not name.startswith("_")]
        for name in names:
            value = getattr(module, name)
            candidates = [(f"{reference_name}.{name}", value)]
            if inspect.isclass(value) and name in {
                "Sandbox", "AsyncSandbox", "Template", "AsyncTemplate", "CommandHandle",
                "AsyncCommandHandle", "WatchHandle", "AsyncWatchHandle", "Context", "Execution",
                "Result", "SandboxPaginator", "AsyncSandboxPaginator", "SnapshotPaginator",
                "AsyncSnapshotPaginator",
            }:
                candidates += [(f"{reference_name}.{name}.{member}", obj)
                               for member, obj in inspect.getmembers(value)
                               if not member.startswith("_") and callable(obj)]
            for key, obj in candidates:
                if not callable(obj):
                    continue
                try:
                    signature = str(inspect.signature(obj))
                except (TypeError, ValueError):
                    continue
                signature = signature.replace("agent_sandbox._standard", "e2b")
                signature = signature.replace("agent_sandbox.code_interpreter", "e2b_code_interpreter")
                signature = re.sub(r"0x[0-9a-fA-F]+", "0xADDRESS", signature)
                result[key] = [inspect.iscoroutinefunction(obj), signature]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-python")
    parser.add_argument("--reference-dump", action="store_true")
    args = parser.parse_args()
    if args.reference_dump:
        print(json.dumps(contract("e2b", "e2b_code_interpreter"), sort_keys=True))
        return
    if not args.reference_python:
        parser.error("--reference-python is required")
    reference = json.loads(subprocess.check_output(
        [args.reference_python, __file__, "--reference-dump"], text=True
    ))
    actual = contract("agent_sandbox", "agent_sandbox.code_interpreter")
    # Alibaba documents a name filter not present in the pinned Python reference.
    # Removing only this additional optional keyword verifies all existing call shapes.
    for key, value in actual.items():
        if key.endswith((".list_snapshots", ".SnapshotPaginator", ".AsyncSnapshotPaginator")):
            value[1] = value[1].replace("name: Optional[str] = None, ", "")
    differences = {key: {"expected": value, "actual": actual.get(key)}
                   for key, value in reference.items() if actual.get(key) != value}
    if differences:
        print(json.dumps(differences, indent=2))
        sys.exit(1)
    print(f"PASS: {len(reference)} public callable signatures and sync/async shapes match the pinned reference")


if __name__ == "__main__":
    main()
