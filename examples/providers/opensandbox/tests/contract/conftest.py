"""Fixtures for the pytest tier: install the plugin into a throwaway store, talk to a live server.

Opt in with ``OPENSANDBOX_LIVE=1`` plus ``EBX_OPENSANDBOX_BASE_URL`` and ``OPEN_SANDBOX_API_KEY``
(or ``EBX_OPENSANDBOX_API_KEY``). Everything is skipped otherwise.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("EBX_OPENSANDBOX_BASE_URL") or os.environ.get("OPEN_SANDBOX_DOMAIN")


def _live() -> bool:
    if os.environ.get("OPENSANDBOX_LIVE") != "1" or not BASE_URL:
        return False
    url = BASE_URL if BASE_URL.startswith("http") else f"http://{BASE_URL}"
    try:
        with urllib.request.urlopen(url.rstrip("/").removesuffix("/v1") + "/health", timeout=3):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    if _live():
        return
    skip = pytest.mark.skip(
        reason="set OPENSANDBOX_LIVE=1 and EBX_OPENSANDBOX_BASE_URL to a reachable server"
    )
    for item in items:
        if str(PLUGIN_DIR) in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def installed_plugin(tmp_path_factory):
    """Install the plugin by local path into an isolated ``~/.ebx`` (never touches the real one)."""
    if not _live():
        yield None
        return
    import easy_sandbox.transport.config as config_module
    from easy_sandbox.providers import installer, registry

    home = tmp_path_factory.mktemp("ebx-home")
    saved = config_module._CONFIG_FILE
    config_module._CONFIG_FILE = home / "config.toml"
    try:
        receipt = installer.install(str(PLUGIN_DIR), yes=True)
        yield receipt
    finally:
        registry.reset_registry()
        config_module._CONFIG_FILE = saved
