"""Strict workflow discovery, separate from provider operation authorization."""

import pytest
import yaml
from pydantic import ValidationError

from agent_sandbox.api.capability import (
    parse_template_data,
    resolve_capabilities,
    resolve_capabilities_for,
)
from agent_sandbox.models.errors import TemplateParseError
from agent_sandbox.models.template import DEFAULT_CAPABILITIES
from tests.template_fixtures import template_manifest


def test_no_default_interpreter_claim():
    assert frozenset() == DEFAULT_CAPABILITIES


def test_application_service_does_not_imply_code_interpreter():
    template = parse_template_data(template_manifest())
    assert template.discovery_capabilities() == {"ports"}


@pytest.mark.parametrize(
    "retired",
    [
        "capabilities",
        "tested_on",
        "providers",
        "custom_commands",
        "system_packages",
        "python_packages",
    ],
)
def test_retired_inputs_rejected(retired):
    with pytest.raises(ValidationError):
        parse_template_data(template_manifest(**{retired: []}))


async def test_unknown_remote_reference_is_unknown_not_default():
    result = await resolve_capabilities("no-local-metadata")
    assert not result.matched and result.capabilities == set()


async def test_explicit_manifest_is_strict_and_resources_do_not_mutate_input(tmp_path):
    path = tmp_path / "template.yaml"
    data = template_manifest(resources={"cpu": 2, "memory": 512})
    path.write_text(yaml.safe_dump(data))
    result = await resolve_capabilities("fixture", local_yaml_path=str(path))
    assert result.matched and result.capabilities == {"ports"}
    parsed = parse_template_data(data)
    assert parsed.cpu_count == 2 and parsed.memory_mb == 512
    assert "cpu_count" not in data


@pytest.mark.parametrize("content", ["name: old", "[]", "bad: [", ""])
async def test_explicit_invalid_manifest_never_falls_back(tmp_path, content):
    path = tmp_path / "template.yaml"
    path.write_text(content)
    with pytest.raises(TemplateParseError):
        await resolve_capabilities("fixture", local_yaml_path=str(path))


async def test_missing_explicit_manifest_raises(tmp_path):
    with pytest.raises(TemplateParseError):
        await resolve_capabilities(local_yaml_path=str(tmp_path / "missing.yaml"))


async def test_cached_alias_matches_only_valid_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_sandbox.api.capability.TEMPLATE_CACHE_DIR", tmp_path)
    path = tmp_path / "cache" / "template.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(template_manifest(aliases=["alias"])))
    result = await resolve_capabilities_for("not-matching", "alias")
    assert result.matched and "code" not in result.capabilities
    path.write_text("name: old\nalias: alias\ncapabilities: [code]")
    with pytest.raises(TemplateParseError):
        await resolve_capabilities("alias")


def test_application_resources_are_preserved_as_topology_metadata(tmp_path):
    from agent_sandbox.utils.registry import load_template_from_yaml

    data = template_manifest(
        application={"name": "service"}, resources={"cpu": 0.5, "memory": "1Gi"}
    )
    path = tmp_path / "template.yaml"
    path.write_text(yaml.safe_dump(data))
    for parsed in (parse_template_data(data), load_template_from_yaml(path)):
        assert parsed.model_extra["resources"] == data["resources"]
        assert parsed.cpu_count is None and parsed.memory_mb is None
    assert "cpu_count" not in data
