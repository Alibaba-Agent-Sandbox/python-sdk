"""Managed native credential mappings remain explicit across host and standalone server."""

from __future__ import annotations

import pytest

from agent_sandbox.models.managed_harness import (
    HARNESS_ENV,
    model_environment,
    validate_model_binding,
)


@pytest.mark.parametrize("adapter", sorted(HARNESS_ENV))
def test_native_environment_binding(adapter):
    binding = {"adapter": adapter, "model": "native-model", "apiKey": "placeholder-model-secret"}
    if adapter != "qoder":
        binding["baseUrl"] = "https://model.example/v1"
    environment = model_environment(binding)
    assert set(environment) == set(HARNESS_ENV[adapter])
    assert environment[HARNESS_ENV[adapter][0]] == "placeholder-model-secret"
    assert "ABX_SERVER_TOKEN" not in environment


def test_standalone_bridge_contract_parity():
    from agent_sandbox.server.managed import MANAGED_HARNESS_ENV

    assert MANAGED_HARNESS_ENV == HARNESS_ENV


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://model.example/v1",
        "https://user:password@model.example/v1",
        "https://model.example/v1?token=placeholder",
        "https://model.example/#secret",
    ],
)
def test_invalid_model_endpoints_reject(endpoint):
    with pytest.raises(ValueError):
        validate_model_binding(
            {
                "adapter": "claude-code",
                "model": "native-model",
                "apiKey": "placeholder",
                "baseUrl": endpoint,
            }
        )


def test_qoder_does_not_accept_fake_openai_endpoint():
    with pytest.raises(ValueError):
        validate_model_binding(
            {
                "adapter": "qoder",
                "model": "auto",
                "apiKey": "placeholder",
                "baseUrl": "https://model.example/v1",
            }
        )


def test_model_binding_rejects_arbitrary_secret_names():
    with pytest.raises(ValueError):
        validate_model_binding(
            {
                "adapter": "qoder",
                "model": "auto",
                "apiKey": "placeholder",
                "AWS_SECRET_ACCESS_KEY": "placeholder",
            }
        )
