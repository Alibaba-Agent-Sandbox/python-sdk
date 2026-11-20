"""Fixed managed-harness credential names; no environment discovery or plugin loading."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

__all__ = ["HARNESS_ENV", "HARNESS_CAPABILITIES", "model_environment", "validate_model_binding"]

# The standalone server has its own runtime descriptors, checked for parity in tests.
HARNESS_ENV: dict[str, tuple[str, ...]] = {
    "codex": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    "qwen-code": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    "claude-code": ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL"),
    "qoder": ("QODER_PERSONAL_ACCESS_TOKEN",),
    "opencode": ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"),
    "deepseek-harness": ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"),
}

# These describe event observation, not cloud/model qualification.
HARNESS_CAPABILITIES: dict[str, dict[str, Any]] = {
    adapter: {
        "streaming": "native_partial"
        if adapter in {"claude-code", "qwen-code"}
        else "committed_steps"
        if adapter == "deepseek-harness"
        else "complete_messages",
        "tool_events": "completed_only" if adapter == "opencode" else "live",
        "per_tool_timeout": adapter != "opencode",
    }
    for adapter in HARNESS_ENV
}


def validate_model_binding(model: dict[str, Any]) -> None:
    """Validate native authentication without requiring a fake endpoint for Qoder."""
    if (
        not isinstance(model, dict)
        or not isinstance(model.get("adapter"), str)
        or model["adapter"] not in HARNESS_ENV
    ):
        raise ValueError("An explicit supported harness adapter is required")
    required = {"adapter", "model", "apiKey"}
    if model["adapter"] != "qoder":
        required.add("baseUrl")
    if not required <= set(model) or set(model) - (required | {"baseUrl"}):
        raise ValueError("Explicit harness credentials, model and applicable endpoint are required")
    if any(not isinstance(model.get(k), str) or not model[k].strip() for k in required):
        raise ValueError("Harness credentials, model and adapter cannot be empty")
    endpoint = model.get("baseUrl", "")
    if model["adapter"] == "qoder":
        if endpoint not in (None, ""):
            raise ValueError("Qoder native authentication does not accept a model endpoint")
        return
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Model endpoints must be explicit HTTPS URLs without credentials or query")


def model_environment(model: dict[str, Any]) -> dict[str, str]:
    """Return only the selected harness's known credential/configuration variables."""
    validate_model_binding(model)
    names = HARNESS_ENV[model["adapter"]]
    values = (model["apiKey"], model.get("baseUrl", ""), model["model"])
    return dict(zip(names, values[: len(names)], strict=True))
