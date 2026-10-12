"""Global pytest fixtures for Easy Sandbox tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

# A developer machine may export GITHUB_TOKEN or LLM credentials; the SDK
# resolves them and would otherwise leak into tests that expect no
# credentials to be configured.
_CREDENTIAL_ENV_VARS: tuple[str, ...] = (
    "GITHUB_TOKEN",
    "EBX_LLM_API_KEY",
    "EBX_QWEN_CODE_API_KEY",
    "EBX_LLM_BASE_URL",
    "EBX_LLM_MODEL",
    "BAILIAN_CODING_PLAN_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
)


@pytest.fixture(autouse=True)
def _isolate_credential_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Iterator[None]:
    """Remove credential env vars so tests stay deterministic.

    Also point the project ``.env`` reader at a missing file. The SDK
    consults ``./.env`` before ``~/.ebx``, and this repository's ``.env``
    must not leak into that layer.
    """
    for var in _CREDENTIAL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        "easy_sandbox.transport.config._PROJECT_ENV_FILE",
        tmp_path / "no-project.env",
    )
    yield


@pytest.fixture
def sandbox_api_key() -> str:
    """Provide a test API key."""
    return "test-api-key-for-unit-tests"


@pytest.fixture
def sandbox_envd_token() -> str:
    """Provide a test envd access token."""
    return "test-envd-access-token"


@pytest.fixture
def sandbox_id() -> str:
    """Provide a test sandbox ID."""
    return "sbx-test-1234567890"


@pytest.fixture
def sandbox_api_url() -> str:
    """Provide a test sandbox API URL."""
    return "https://api.cn-hangzhou.e2b.fc.aliyuncs.com"
