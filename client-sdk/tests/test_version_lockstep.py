"""The client and server distributions are released in lockstep.

The client depends on ``agent-sandbox-server==<its own version>``, so the two
``_version.py`` files must never drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import agent_sandbox

_SERVER_VERSION_FILE = (
    Path(__file__).resolve().parents[2]
    / "server-sdk"
    / "src"
    / "agent_sandbox"
    / "server"
    / "_version.py"
)


def test_client_and_server_versions_match() -> None:
    if not _SERVER_VERSION_FILE.is_file():
        pytest.skip("server-sdk source tree not present (building from an sdist)")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', _SERVER_VERSION_FILE.read_text("utf-8"))
    assert match is not None
    assert match.group(1) == agent_sandbox.__version__


def test_client_pins_the_matching_server_version() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("pyproject.toml not present")
    text = pyproject.read_text("utf-8")
    assert f'"agent-sandbox-server=={agent_sandbox.__version__}"' in text


def test_mcp_server_advertises_the_package_version() -> None:
    from agent_sandbox.agent.mcp import SERVER_VERSION

    assert agent_sandbox.__version__ == SERVER_VERSION
