"""Wheel/sdist layout of the client distribution (``easy-sandbox``).

The client and server SDKs share the ``easy_sandbox`` namespace but ship as two
distributions.  The client wheel owns ``easy_sandbox/__init__.py`` and every
sub-package *except* ``easy_sandbox/server``, which belongs to
``easy-sandbox-server``.  The CLI lives in a separate (Node.js) project and must
not reappear here.

The test builds with the project's real build backend (hatchling) in a temporary
copy of the project, so it checks the actual ``pyproject.toml`` configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

pytest.importorskip("hatchling", reason="build backend hatchling is not installed")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TOP_LEVEL_FILES = ("pyproject.toml", "README.md", "LICENSE", "NOTICE")


@pytest.fixture(scope="module")
def built_dists(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Path]]:
    project = tmp_path_factory.mktemp("client-packaging") / "project"
    project.mkdir()
    for name in _TOP_LEVEL_FILES:
        shutil.copy2(PROJECT_ROOT / name, project / name)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    shutil.copytree(PROJECT_ROOT / "src", project / "src", ignore=ignore)
    shutil.copytree(PROJECT_ROOT / "tests", project / "tests", ignore=ignore)
    result = subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "sdist", "-t", "wheel"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"hatchling build failed:\n{result.stdout}\n{result.stderr}"
    sdists = sorted((project / "dist").glob("*.tar.gz"))
    wheels = sorted((project / "dist").glob("*.whl"))
    assert len(sdists) == 1 and len(wheels) == 1
    yield {"sdist": sdists[0], "wheel": wheels[0]}


def _wheel_names(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as zf:
        return zf.namelist()


def test_wheel_owns_the_namespace_root_and_is_typed(built_dists: dict[str, Path]) -> None:
    names = _wheel_names(built_dists["wheel"])
    assert "easy_sandbox/__init__.py" in names
    assert "easy_sandbox/_version.py" in names
    assert "easy_sandbox/py.typed" in names
    for package in ("api", "models", "transport", "protocol", "declarative", "agent", "utils"):
        assert f"easy_sandbox/{package}/__init__.py" in names


def test_wheel_excludes_server_and_cli(built_dists: dict[str, Path]) -> None:
    names = _wheel_names(built_dists["wheel"])
    assert not [n for n in names if n.startswith("easy_sandbox/server")], (
        "easy_sandbox.server belongs to the easy-sandbox-server distribution"
    )
    assert not [n for n in names if n.startswith("easy_sandbox/cli")]
    assert not [n for n in names if n.endswith("entry_points.txt")], "no console scripts"


def test_wheel_metadata_has_no_cli_dependencies(built_dists: dict[str, Path]) -> None:
    with zipfile.ZipFile(built_dists["wheel"]) as zf:
        metadata = next(zf.read(n).decode() for n in zf.namelist() if n.endswith("/METADATA"))
    assert "Name: easy-sandbox\n" in metadata
    for dep in ("click", "rich", "questionary"):
        assert f"Requires-Dist: {dep}" not in metadata
    assert "Provides-Extra: cli" not in metadata
    assert "Provides-Extra: server" in metadata


def test_sdist_ships_license_notice_and_sources(built_dists: dict[str, Path]) -> None:
    with tarfile.open(built_dists["sdist"]) as tf:
        members = tf.getnames()
    root = members[0].split("/")[0]
    for name in (
        "LICENSE",
        "NOTICE",
        "README.md",
        "pyproject.toml",
        "src/easy_sandbox/__init__.py",
    ):
        assert f"{root}/{name}" in members
    assert not [m for m in members if "/src/easy_sandbox/server/" in m]
