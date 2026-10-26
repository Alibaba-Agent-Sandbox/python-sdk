"""Application authentication vectors shared with the CLI and Node HTTP client."""

import json
from pathlib import Path

import pytest

from agent_sandbox.api.server_client import ServerClient

VECTORS = json.loads(
    (
        Path(__file__).resolve().parents[3] / "contracts/testing/application-auth-vectors.json"
    ).read_text()
)["cases"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda case: case["id"])
def test_application_auth_vectors(case):
    client = ServerClient(
        "https://example.invalid/owned", token=case.get("token"), headers=case["headers"]
    )
    assert {key.lower(): value for key, value in client.auth_headers().items()} == case["expected"]
