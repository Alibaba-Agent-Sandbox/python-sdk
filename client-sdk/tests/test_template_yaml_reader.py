"""Public v1 file consumers agree on actual YAML Core scalar/admission behavior."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent_sandbox import template_contract
from agent_sandbox.api.capability import resolve_capabilities
from agent_sandbox.api.template import launch_template
from agent_sandbox.template_contract.normalize import parse_yaml_v1
from agent_sandbox.utils.registry import load_template_from_yaml

LITERAL = b"""specVersion: 1
name: yaml-values
sandbox:
  provider: alicloud-express
  template:
    reference: base
    aliases: [yaml-alias]
  instance:
    envs:
      FLAG: on
      WHEN: 2026-11-12
"""


def test_registry_file_loader_preserves_core_strings(tmp_path):
    path = tmp_path / "template.yaml"
    path.write_bytes(LITERAL)
    template = load_template_from_yaml(path)
    assert template.env == {"FLAG": "on", "WHEN": "2026-11-12"}


async def test_cached_discovery_uses_the_same_core_reader(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_sandbox.api.capability.TEMPLATE_CACHE_DIR", tmp_path)
    directory = tmp_path / "cached"
    directory.mkdir()
    (directory / "template.yaml").write_bytes(LITERAL)
    result = await resolve_capabilities("yaml-alias")
    assert result.matched


async def test_prepared_file_launch_forwards_core_strings_without_cli(tmp_path, monkeypatch):
    path, journal = tmp_path / "template.yaml", tmp_path / "run"
    path.write_bytes(LITERAL)
    sandbox = SimpleNamespace(id="local-fixture", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    async with await launch_template(path, provider="alicloud-express", journal_path=journal):
        assert create.call_args.kwargs["envs"] == {"FLAG": "on", "WHEN": "2026-11-12"}
    sandbox.kill.assert_awaited_once()
    assert "WHEN" not in journal.read_text()


SAFE_LITERAL = LITERAL.replace(b"FLAG: on", b"FLAG: safe").replace(
    b"WHEN: 2026-11-12", b'WHEN: "2026-11-12"'
)


@pytest.mark.parametrize(
    "content",
    [
        SAFE_LITERAL.replace(
            b"FLAG: safe", b"FLAG: first-private-value\n      FLAG: second-private-value"
        ),
        SAFE_LITERAL.replace(b"FLAG: safe", b"FLAG: &sample literal\n      COPY: *sample"),
        SAFE_LITERAL + b"\n#" + b"x" * 1048576,
        b"""specVersion: 1
name: yaml-values
sandbox:
  provider: alicloud-express
  template: {reference: base}
""".decode().encode("utf-16"),
    ],
)
async def test_invalid_yaml_is_rejected_before_resource_or_journal(tmp_path, monkeypatch, content):
    path, journal = tmp_path / "template.yaml", tmp_path / "run"
    path.write_bytes(content)
    sandbox = SimpleNamespace(id="local-fixture", provider="alicloud-express", kill=AsyncMock())
    create = AsyncMock(return_value=sandbox)
    monkeypatch.setattr("agent_sandbox.api.template.Sandbox.create", create)
    session = None
    try:
        with pytest.raises(ValueError) as caught:
            session = await launch_template(path, provider="alicloud-express", journal_path=journal)
    finally:
        if session is not None:
            await session.close()
    assert "first-private-value" not in str(caught.value)
    assert "second-private-value" not in str(caught.value)
    create.assert_not_awaited()
    assert not journal.exists()


_VECTORS = json.loads(Path(template_contract.__file__).with_name("yaml-fixtures.json").read_text())


@pytest.mark.parametrize("case", _VECTORS["valid"], ids=lambda case: case["id"])
def test_shared_valid_yaml_text_vectors_use_actual_core_loader(case):
    assert parse_yaml_v1(case["text"]) == case["expected"]
    assert parse_yaml_v1(case["text"].encode("utf-8")) == case["expected"]


@pytest.mark.parametrize("case", _VECTORS["invalid"], ids=lambda case: case["id"])
def test_shared_invalid_yaml_vectors_reject_without_source_values(case):
    source = (
        bytes.fromhex(case["hex"])
        if "hex" in case
        else case["repeat"] * case["count"]
        if "repeat" in case
        else case["text"]
    )
    with pytest.raises(ValueError) as caught:
        parse_yaml_v1(source)
    assert "private-source-canary" not in str(caught.value)


def test_core_reader_does_not_mutate_other_pyyaml_consumers():
    import yaml

    assert yaml.safe_load("flag: on")["flag"] is True
    assert parse_yaml_v1("flag: on")["flag"] == "on"
    assert yaml.safe_load("flag: on")["flag"] is True
