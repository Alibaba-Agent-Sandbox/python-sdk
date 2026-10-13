"""The client and server distributions are released in lockstep.

``DockerBuilder`` pins the server wheel it downloads from PyPI to the *client*
version, so the two ``_version.py`` files must never drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import easy_sandbox

_SERVER_VERSION_FILE = (
    Path(__file__).resolve().parents[2]
    / "server-sdk"
    / "src"
    / "easy_sandbox"
    / "server"
    / "_version.py"
)


def test_client_and_server_versions_match() -> None:
    if not _SERVER_VERSION_FILE.is_file():
        pytest.skip("server-sdk source tree not present (building from an sdist)")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', _SERVER_VERSION_FILE.read_text("utf-8"))
    assert match is not None
    assert match.group(1) == easy_sandbox.__version__
