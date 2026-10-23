"""Shared contract parity, fail-closed inputs and content identity regressions."""

import json
from pathlib import Path

import pytest

from agent_sandbox.workflows import plan_workflow
from agent_sandbox.workflows.identity import binding_digest, bytes_digest, snapshot_digest
from agent_sandbox.workflows.planner import CONTRACT

CONTRACTS = Path(__file__).parents[3] / "contracts"
VECTORS = json.loads((CONTRACTS / "vectors.json").read_text())["cases"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["id"])
def test_canonical_vectors(case):
    data = case["input"]
    if "error" in case:
        with pytest.raises(ValueError):
            plan_workflow(**data)
    else:
        assert plan_workflow(**data) == case["expected"]


def test_package_contract_copies_are_exact():
    import agent_sandbox.workflows as workflows

    for path in CONTRACTS.glob("*.json"):
        assert Path(workflows.__file__).with_name(path.name).read_bytes() == path.read_bytes()


def test_all_of_truth_table():
    for states, result in CONTRACT["truth_table"].items():
        expected = "F" if "F" in states else "U" if "U" in states else "T"
        assert result == expected


def test_snapshot_identity_tracks_paths_and_untracked_content():
    assert snapshot_digest({"a": b"1", "b": b"2"}) == snapshot_digest({"b": b"2", "a": b"1"})
    assert snapshot_digest({"a": b"1"}) != snapshot_digest({"a": b"1", "untracked": b"new"})
    assert snapshot_digest({"a": b"1"}) != snapshot_digest({"other": b"1"})
    with pytest.raises(ValueError):
        snapshot_digest({"../outside": b"secret"})
    with pytest.raises(ValueError):
        snapshot_digest({"/absolute": b"secret"})


def test_manifest_is_exact_bytes_binding_is_canonical():
    assert bytes_digest(b"name: app\n") != bytes_digest(b"name: app\n# change\n")
    assert binding_digest({"a": "1", "b": "2"}) == binding_digest({"b": "2", "a": "1"})
    assert binding_digest({"a": "1"}) != binding_digest({"a": "2"})
