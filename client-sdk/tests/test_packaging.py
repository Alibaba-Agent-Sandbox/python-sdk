"""Wheel/sdist layout of the client distribution (``agent-sandbox``).

The client and server SDKs share the ``agent_sandbox`` namespace but ship as two
distributions.  The client wheel owns ``agent_sandbox/__init__.py`` and every
sub-package *except* ``agent_sandbox/server``, which belongs to
``agent-sandbox-server``.  The CLI lives in a separate (Node.js) project and must
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
    assert "agent_sandbox/__init__.py" in names
    assert "agent_sandbox/_version.py" in names
    assert "agent_sandbox/py.typed" in names
    for package in ("api", "models", "transport", "protocol", "declarative", "agent", "utils"):
        assert f"agent_sandbox/{package}/__init__.py" in names


def test_wheel_excludes_server_and_cli(built_dists: dict[str, Path]) -> None:
    names = _wheel_names(built_dists["wheel"])
    assert not [n for n in names if n.startswith("agent_sandbox/server")], (
        "agent_sandbox.server belongs to the agent-sandbox-server distribution"
    )
    assert not [n for n in names if n.startswith("agent_sandbox/cli")]
    assert not [n for n in names if n.endswith("entry_points.txt")], "no console scripts"


def test_wheel_metadata_has_no_cli_dependencies(built_dists: dict[str, Path]) -> None:
    with zipfile.ZipFile(built_dists["wheel"]) as zf:
        metadata = next(zf.read(n).decode() for n in zf.namelist() if n.endswith("/METADATA"))
    assert "Name: agent-sandbox-client\n" in metadata
    for dep in ("click", "questionary", "e2b", "e2b-code-interpreter"):
        assert f"Requires-Dist: {dep}" not in metadata
    assert "Provides-Extra: cli" not in metadata
    assert "Provides-Extra: server" not in metadata


def test_wheel_hard_depends_on_matching_server_and_keeps_functional_extras(
    built_dists: dict[str, Path],
) -> None:
    import agent_sandbox

    with zipfile.ZipFile(built_dists["wheel"]) as zf:
        metadata = next(zf.read(n).decode() for n in zf.namelist() if n.endswith("/METADATA"))
    requires = [line for line in metadata.splitlines() if line.startswith("Requires-Dist: ")]
    unconditional = [r for r in requires if "extra ==" not in r]
    assert f"Requires-Dist: agent-sandbox-server=={agent_sandbox.__version__}" in unconditional
    assert "Provides-Extra: server" not in metadata
    mcp_deps = [r for r in requires if "extra == 'mcp'" in r]
    assert any(r.startswith("Requires-Dist: mcp>=1.0.0") for r in mcp_deps)


def test_sdist_ships_license_notice_and_sources(built_dists: dict[str, Path]) -> None:
    with tarfile.open(built_dists["sdist"]) as tf:
        members = tf.getnames()
    root = members[0].split("/")[0]
    for name in (
        "LICENSE",
        "NOTICE",
        "README.md",
        "pyproject.toml",
        "src/agent_sandbox/__init__.py",
    ):
        assert f"{root}/{name}" in members
    assert not [m for m in members if "/src/agent_sandbox/server/" in m]


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


def test_uv_can_resolve_both_workspace_editables_offline() -> None:
    """Exercise uv's workspace metadata parser without installing or contacting PyPI."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    workspace = PROJECT_ROOT.parent
    if not (workspace / "server-sdk" / "pyproject.toml").is_file():
        pytest.skip("requires the repository workspace, not a standalone client sdist")
    result = subprocess.run(
        [
            uv,
            "pip",
            "install",
            "--dry-run",
            "--no-deps",
            "--offline",
            "--no-build-isolation",
            "--python",
            sys.executable,
            "-e",
            "./server-sdk",
            "-e",
            "./client-sdk[dev]",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"uv workspace resolution failed:\n{result.stderr}"
