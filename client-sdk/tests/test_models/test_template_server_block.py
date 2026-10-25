"""``SandboxTemplate.server`` (declarative SandboxServer policy)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_sandbox.models.template import (
    SERVER_GROUP_NAMES,
    SERVER_PATH_KEYS,
    SERVER_POLICY_PRESETS,
    SERVER_POLICY_TOP_KEYS,
    SERVER_RULE_KEYS,
    SandboxTemplate,
    validate_server_block,
)
from tests.template_fixtures import template_manifest

VALID = {
    "preset": "transfer-only",
    "endpoints": {
        "files_download_stream": {
            "paths": {"allow": ["/home/user/out"]},
            "limits": {"max_bytes": "5MB"},
        },
        "files_upload": {"enabled": True, "scopes": ["files:write"]},
    },
}


def make(server: object) -> SandboxTemplate:
    return SandboxTemplate.model_validate(template_manifest(server=server))


def test_default_is_none() -> None:
    assert SandboxTemplate.model_validate(template_manifest()).server is None


def test_valid_block_round_trips() -> None:
    assert make(VALID).server == VALID


def test_existing_templates_without_server_are_unaffected() -> None:
    t = SandboxTemplate.model_validate(template_manifest(unknown_future_key=1))
    assert t.server is None


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ({"presets": "x"}, "server.presets"),
        ({"preset": "nope"}, "server.preset"),
        ({"endpoints": []}, "server.endpoints"),
        ({"endpoints": {"a": {"enable": True}}}, "server.endpoints.a.enable"),
        ({"endpoints": {"a": {"enabled": "yes"}}}, "enabled"),
        ({"endpoints": {"a": {"scopes": "files:read"}}}, "scopes"),
        ({"endpoints": {"a": {"paths": {"allowed": []}}}}, "paths.allowed"),
        ({"endpoints": {"a": {"limits": []}}}, "limits"),
        ({"endpoints": {"a": "on"}}, "expected a mapping"),
        ({"defaults": {"bogus": 1}}, "server.defaults.bogus"),
        ({"groups": ["file_ops", "nope"]}, "unknown group 'nope'"),
        ({"groups": [1]}, "list of group names"),
        ({"groups": "file_ops"}, "server.groups: expected a mapping"),
        ({"groups": {"nope": True}}, "server.groups.nope"),
        ({"groups": {"process": "off"}}, "server.groups.process: expected a boolean"),
        ({"groups": {"core": False}}, "core group cannot be disabled"),
    ],
)
def test_malformed_blocks_are_rejected(block: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace(".", r"\.")):
        make(block)


@pytest.mark.parametrize(
    "groups", [["file_ops", "dev_tools"], {"process": False, "browser": True}, []]
)
def test_groups_accept_a_list_or_a_map_and_keep_their_shape(groups: object) -> None:
    template = make({"groups": groups})
    assert template.server == {"groups": groups}
    dumped = template.model_dump(mode="json")["server"]
    assert dumped == {"groups": groups}


def test_non_mapping_server_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make("transfer-only")


def test_validator_is_usable_directly() -> None:
    assert validate_server_block({"preset": "locked"}) == {"preset": "locked"}
    with pytest.raises(ValueError, match="unknown key"):
        validate_server_block({"x": 1})


def test_vocabulary_matches_the_server() -> None:
    policy = pytest.importorskip("agent_sandbox.server.policy")
    assert SERVER_POLICY_TOP_KEYS == policy._TOP_KEYS
    assert SERVER_RULE_KEYS == policy._RULE_KEYS
    assert SERVER_PATH_KEYS == policy._PATH_KEYS
    assert frozenset(policy.PRESETS) == SERVER_POLICY_PRESETS
    assert frozenset(policy._GROUP_NAMES) == SERVER_GROUP_NAMES


def test_a_valid_block_is_accepted_by_the_real_server_loader() -> None:
    policy = pytest.importorskip("agent_sandbox.server.policy")
    block = make(VALID).server
    assert block is not None
    policy.ServerPolicy.from_dict(block)


@pytest.mark.parametrize("groups", [["file_ops"], {"process": False}])
def test_group_forms_are_accepted_by_the_real_server_loader(groups: object) -> None:
    policy = pytest.importorskip("agent_sandbox.server.policy")
    block = make({"groups": groups}).server
    assert block is not None
    assert policy.ServerPolicy.from_dict(block).groups == (
        {"file_ops": True} if isinstance(groups, list) else groups
    )
