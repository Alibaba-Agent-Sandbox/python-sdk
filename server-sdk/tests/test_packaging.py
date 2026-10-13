"""Wheel/sdist layout of the server distribution (``agent-sandbox-server``).

``agent_sandbox`` is a shared namespace.  This distribution must ship only
``agent_sandbox/server/**`` and must NOT ship ``agent_sandbox/__init__.py``
(otherwise it would collide with the client distribution's file and a plain
``pip install agent-sandbox-server`` would fight ``pip install agent-sandbox``).

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
    project = tmp_path_factory.mktemp("server-packaging") / "project"
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


def test_wheel_is_a_pure_namespace_portion(built_dists: dict[str, Path]) -> None:
    names = [n for n in _wheel_names(built_dists["wheel"]) if ".dist-info/" not in n]
    assert "agent_sandbox/__init__.py" not in names, "namespace root belongs to the client dist"
    assert names, "wheel is empty"
    assert all(n.startswith("agent_sandbox/server/") for n in names), [
        n for n in names if not n.startswith("agent_sandbox/server/")
    ]


def test_wheel_ships_server_package_version_coerce_and_py_typed(
    built_dists: dict[str, Path],
) -> None:
    names = _wheel_names(built_dists["wheel"])
    for expected in (
        "agent_sandbox/server/__init__.py",
        "agent_sandbox/server/_version.py",
        "agent_sandbox/server/_coerce.py",
        "agent_sandbox/server/py.typed",
        "agent_sandbox/server/app.py",
    ):
        assert expected in names


def test_wheel_metadata_is_stdlib_plus_websockets_only(built_dists: dict[str, Path]) -> None:
    with zipfile.ZipFile(built_dists["wheel"]) as zf:
        metadata = next(zf.read(n).decode() for n in zf.namelist() if n.endswith("/METADATA"))
    assert "Name: agent-sandbox-server\n" in metadata
    requires = [
        line
        for line in metadata.splitlines()
        if line.startswith("Requires-Dist:") and "extra ==" not in line
    ]
    assert requires == ["Requires-Dist: websockets>=12.0"]


def test_sdist_ships_license_notice_and_sources(built_dists: dict[str, Path]) -> None:
    with tarfile.open(built_dists["sdist"]) as tf:
        members = tf.getnames()
    root = members[0].split("/")[0]
    for name in ("LICENSE", "NOTICE", "README.md", "pyproject.toml"):
        assert f"{root}/{name}" in members
    assert f"{root}/src/agent_sandbox/__init__.py" not in members


def test_sdist_include_list_is_the_documented_one() -> None:
    """The sdist include list is exactly the documented one.

    Repo-only documents (``llms.txt``, ``CHANGELOG.md``, ``SKILL.md``) are intentionally NOT
    in it; update this test if shipping one in the distribution becomes an explicit decision.
    """
    try:
        import tomllib  # type: ignore[import-not-found,unused-ignore]
    except ImportError:  # pragma: no cover - Python 3.10 fallback
        import tomli as tomllib

    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include: list[str] = data["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert sorted(include) == sorted(
        ["src/agent_sandbox/", "tests/", "README.md", "LICENSE", "NOTICE", "pyproject.toml"]
    )
    for repo_doc in ("llms.txt", "CHANGELOG.md", "SKILL.md"):
        assert repo_doc not in include
