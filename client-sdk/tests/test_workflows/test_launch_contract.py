"""Shared whole-template plans stay identical across consumers."""

import json
from pathlib import Path

import pytest

from agent_sandbox.workflows.launch import plan_template_launch

CONTRACTS = Path(__file__).parents[3] / "contracts"
CASES = json.loads((CONTRACTS / "launch-vectors.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_launch_vectors(case):
    if case.get("error"):
        with pytest.raises(ValueError):
            plan_template_launch(**case["input"])
    else:
        assert plan_template_launch(**case["input"]) == case["expected"]
