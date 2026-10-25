#!/usr/bin/env python3
"""Verify the built ``client-sdk`` / ``server-sdk`` distributions.

Expects ``python -m build --outdir dist/client-sdk client-sdk`` and
``python -m build --outdir dist/server-sdk server-sdk`` to have been run from the
repository root (``make build``).

Checks:

* ``py-typed`` — each wheel ships its PEP 561 marker
  (``agent_sandbox/py.typed`` for the client, ``agent_sandbox/server/py.typed`` for the server).
* ``combined-install`` — both wheels install into one fresh virtualenv and the shared
  ``agent_sandbox`` namespace works (``import agent_sandbox`` and ``import agent_sandbox.server``).

Usage: ``python scripts/check_dists.py [py-typed|combined-install|all]``
"""

from __future__ import annotations

import glob
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PY_TYPED_MARKERS = {
    "client-sdk": "agent_sandbox/py.typed",
    "server-sdk": "agent_sandbox/server/py.typed",
}

IMPORT_CHECK = """
import agent_sandbox
import agent_sandbox.server
import yaml
from agent_sandbox.api import launch_template
from agent_sandbox import Sandbox, AsyncSandbox, ProviderSandbox
from agent_sandbox.server import default_registry, start

assert all(callable(cls.create) for cls in (Sandbox, AsyncSandbox, ProviderSandbox))
assert callable(launch_template)
assert yaml.safe_load("spec_version: 4") == {"spec_version": 4}
print("template YAML parser: available in the base install")
print("agent_sandbox       :", agent_sandbox.__file__)
print("agent_sandbox.server:", agent_sandbox.server.__file__)
"""


def _wheel(package: str) -> Path:
    wheels = sorted(glob.glob(str(DIST / package / "*.whl")))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one wheel in dist/{package}, found {wheels}")
    return Path(wheels[0])


def check_py_typed() -> None:
    failed = False
    for package, marker in PY_TYPED_MARKERS.items():
        wheel = _wheel(package)
        with zipfile.ZipFile(wheel) as zf:
            names = zf.namelist()
        if marker in names:
            print(f"py.typed found in {wheel.name}: OK ({marker})")
        else:
            print(f"{marker} NOT found in {wheel}", file=sys.stderr)
            failed = True
    if failed:
        raise SystemExit(1)


def check_combined_install() -> None:
    server, client = _wheel("server-sdk"), _wheel("client-sdk")
    with tempfile.TemporaryDirectory(prefix="agent-sandbox-combined-") as tmp:
        venv = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        bindir = "Scripts" if sys.platform == "win32" else "bin"
        python = venv / bindir / ("python.exe" if sys.platform == "win32" else "python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(server), str(client)],
            check=True,
        )
        # Run outside the repo so the installed wheels, not the source trees, are imported.
        subprocess.run([str(python), "-c", IMPORT_CHECK], check=True, cwd=tmp)
    print("client + server wheels install into one venv and import: OK")


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else "all"
    if what not in {"py-typed", "combined-install", "all"}:
        print(__doc__, file=sys.stderr)
        return 2
    if what in {"py-typed", "all"}:
        check_py_typed()
    if what in {"combined-install", "all"}:
        check_combined_install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
