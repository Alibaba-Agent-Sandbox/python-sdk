"""Installed provider requirements still apply after the SDK changes."""

from __future__ import annotations

import pytest

from agent_sandbox.models.errors import ProviderVersionError
from agent_sandbox.providers import installer, registry
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import write_plugin


def test_runtime_checks_sdk_after_install(iso, tmp_path, monkeypatch):  # noqa: F811
    import agent_sandbox._version as version

    source = write_plugin(tmp_path / "plugin")
    installer.install(str(source), yes=True)
    monkeypatch.setattr(version, "__version__", "0.1.0")
    with pytest.raises(ProviderVersionError, match="requires sdk"):
        registry.load_installed("demo-prov")
