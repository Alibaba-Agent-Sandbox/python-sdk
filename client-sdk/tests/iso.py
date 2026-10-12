"""Shared isolation fixture for configuration/provider tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

import easy_sandbox.transport.config as config_module
from easy_sandbox.providers import registry
from easy_sandbox.utils import config_keys as ck

if TYPE_CHECKING:
    from pathlib import Path

_PREFIXES = ("EBX_", "SANDBOX_", "E2B_", "ALICLOUD_", "ALIBABA_CLOUD_", "OPENAI_")


def _all_env_names() -> set[str]:
    names = set()
    for key in (*ck.CORE_KEYS, *ck.ALICLOUD_EXPRESS_KEYS):
        names.update(ck.env_names(key))
    names.update({"GITHUB_TOKEN", "AccessKey", "AccessKeySecret"})
    return names


@dataclass
class Iso:
    home: Path

    @property
    def toml(self) -> Path:
        return self.home / "config.toml"

    @property
    def env(self) -> Path:
        return self.home / ".env"

    def write_toml(self, text: str) -> None:
        self.toml.write_text(text, encoding="utf-8")
        config_module.reset_config()

    def write_env(self, text: str) -> None:
        self.env.write_text(text, encoding="utf-8")
        config_module.reset_config()


@pytest.fixture
def iso(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    for name in list(os.environ):
        if name.startswith(_PREFIXES) or name in _all_env_names():
            monkeypatch.delenv(name, raising=False)
    home = tmp_path / ".ebx"
    home.mkdir()
    monkeypatch.setattr(config_module, "_CONFIG_FILE", home / "config.toml")
    monkeypatch.setattr(config_module, "_ENV_FILE_CANDIDATES", [home / ".env"])
    monkeypatch.setattr(config_module, "_PROJECT_ENV_FILE", tmp_path / "no-project.env")
    config_module.reset_config()
    registry.reset_registry()
    yield Iso(home)
    config_module.reset_config()
    registry.reset_registry()
