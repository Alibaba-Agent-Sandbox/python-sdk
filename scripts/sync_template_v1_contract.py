"""Sync exact template-owner Git object bytes; never regenerate the contract locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_checkout", type=Path)
    parser.add_argument("--revision", help="Full immutable producer commit; defaults to source lock")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "client-sdk/src/agent_sandbox/template_contract"
    lock_path = destination / "source.json"
    lock = json.loads(lock_path.read_text())
    revision = args.revision or lock["revision"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        parser.error("Use a full immutable producer Git commit")
    for source, entry in lock["files"].items():
        data = subprocess.check_output(["git", "show", f"{revision}:{source}"], cwd=args.source_checkout)
        target = destination / entry["target"]
        digest = hashlib.sha256(data).hexdigest()
        if args.check:
            if revision != lock["revision"] or target.read_bytes() != data or entry["sha256"] != digest:
                raise SystemExit("Template owner source lock or copied bytes differ")
        else:
            target.write_bytes(data)
            entry["sha256"] = digest
    if not args.check:
        lock["revision"] = revision
        lock_path.write_text(json.dumps(lock, indent=2) + "\n")


if __name__ == "__main__":
    main()
