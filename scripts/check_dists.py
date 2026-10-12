#!/usr/bin/env python3
"""Verify the built ``client-sdk`` / ``server-sdk`` distributions.

Expects ``python -m build --outdir dist/client-sdk client-sdk`` and
``python -m build --outdir dist/server-sdk server-sdk`` to have been run from the
repository root (``make build``).

Checks:

* ``py-typed`` — each wheel ships its PEP 561 marker
  (``easy_sandbox/py.typed`` for the client, ``easy_sandbox/server/py.typed`` for the server).
* ``combined-install`` — both wheels install into one fresh virtualenv and the shared
  ``easy_sandbox`` namespace works (``import easy_sandbox`` and ``import easy_sandbox.server``).

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
    "client-sdk": "easy_sandbox/py.typed",
    "server-sdk": "easy_sandbox/server/py.typed",
}

IMPORT_CHECK = """
import easy_sandbox
import easy_sandbox.server
from easy_sandbox import Sandbox
from easy_sandbox.server import default_registry, start

print("easy_sandbox       :", easy_sandbox.__file__)
print("easy_sandbox.server:", easy_sandbox.server.__file__)
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
    with tempfile.TemporaryDirectory(prefix="easy-sandbox-combined-") as tmp:
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
