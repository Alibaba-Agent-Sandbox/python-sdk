"""Tests for transport.auth module."""

from __future__ import annotations

import pytest

from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
    TokenExpiredError,
)
from agent_sandbox.providers.alicloud_express.auth import (
    ENVD_AUTH_HEADER,
    ENVD_SANDBOX_ID_HEADER,
    ENVD_SANDBOX_PORT_HEADER,
    PLATFORM_AUTH_HEADER,
    ApiKeyAuth,
    EnvdTokenManager,
    build_envd_headers,
    create_auth_provider,
)


class TestApiKeyAuth:
    """Test API Key authentication."""

    async def test_get_headers(self):
        auth = ApiKeyAuth("my-api-key")
        headers = await auth.get_headers()
        assert headers == {PLATFORM_AUTH_HEADER: "Bearer my-api-key"}

    async def test_get_headers_strips_whitespace(self):
        auth = ApiKeyAuth("  my-api-key  ")
        headers = await auth.get_headers()
        assert headers == {PLATFORM_AUTH_HEADER: "Bearer my-api-key"}

    def test_empty_key_raises(self):
        with pytest.raises(InvalidAPIKeyError):
            ApiKeyAuth("")

    def test_whitespace_only_key_raises(self):
        with pytest.raises(InvalidAPIKeyError):
            ApiKeyAuth("   ")

    async def test_refresh_is_noop(self):
        auth = ApiKeyAuth("key")
        await auth.refresh()  # Should not raise


class TestEnvdTokenManager:
    """Test envd access token manager."""

    def test_initial_token_none(self):
        mgr = EnvdTokenManager()
        assert mgr.token is None

    def test_initial_token_set(self):
        mgr = EnvdTokenManager("my-token")
        assert mgr.token == "my-token"

    def test_set_token(self):
        mgr = EnvdTokenManager()
        mgr.set_token("new-token")
        assert mgr.token == "new-token"

    def test_get_headers(self):
        mgr = EnvdTokenManager("my-token", sandbox_id="sbx-123")
        headers = mgr.get_headers()
        assert ENVD_AUTH_HEADER in headers
        assert headers[ENVD_AUTH_HEADER] == "my-token"
        assert ENVD_SANDBOX_ID_HEADER in headers
        assert headers[ENVD_SANDBOX_ID_HEADER] == "sbx-123"
        assert ENVD_SANDBOX_PORT_HEADER in headers
        assert headers[ENVD_SANDBOX_PORT_HEADER] == "49983"
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")

    def test_get_headers_without_sandbox_id(self):
        mgr = EnvdTokenManager("my-token")
        headers = mgr.get_headers()
        assert ENVD_AUTH_HEADER in headers
        assert ENVD_SANDBOX_ID_HEADER not in headers
        assert ENVD_SANDBOX_PORT_HEADER in headers
        assert "Authorization" in headers

    def test_get_headers_no_token_raises(self):
        mgr = EnvdTokenManager()
        with pytest.raises(TokenExpiredError):
            mgr.get_headers()

    def test_clear(self):
        mgr = EnvdTokenManager("my-token")
        mgr.clear()
        assert mgr.token is None


class TestCreateAuthProvider:
    """Test create_auth_provider factory."""

    def test_api_key_priority(self):
        auth = create_auth_provider(api_key="my-key")
        assert isinstance(auth, ApiKeyAuth)

    def test_removed_control_plane_arguments_are_rejected(self):
        with pytest.raises(TypeError):
            create_auth_provider(access_key_id="ak", access_key_secret="sk")

    def test_no_credentials_raises(self):
        with pytest.raises(InvalidAPIKeyError, match="No authentication credentials"):
            create_auth_provider()

    def test_api_key_used(self):
        auth = create_auth_provider(api_key="key-123")
        assert isinstance(auth, ApiKeyAuth)

    def test_env_sandbox_api_key_is_used(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "env-key-123")
        auth = create_auth_provider()
        assert isinstance(auth, ApiKeyAuth)
        assert auth._api_key == "env-key-123"

    async def test_env_sandbox_api_key_header(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "env-key-123")
        auth = create_auth_provider()
        assert await auth.get_headers() == {PLATFORM_AUTH_HEADER: "Bearer env-key-123"}

    def test_retired_api_key_names_are_not_read(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("E2B_API_KEY", "retired-e2b")
        monkeypatch.setenv("SANDBOX_API_KEY", "retired-sandbox")
        with pytest.raises(InvalidAPIKeyError, match="No authentication credentials") as exc_info:
            create_auth_provider()
        suggestion = exc_info.value.suggestion
        assert "ABX_SANDBOX_API_KEY" in suggestion
        assert "E2B_API_KEY" not in suggestion


class TestBuildEnvdHeaders:
    """Test build_envd_headers convenience function."""

    def test_returns_all_four_headers(self):
        headers = build_envd_headers("sbx-abc", "tok-xyz")
        assert headers[ENVD_AUTH_HEADER] == "tok-xyz"
        assert headers[ENVD_SANDBOX_ID_HEADER] == "sbx-abc"
        assert headers[ENVD_SANDBOX_PORT_HEADER] == "49983"
        assert headers["Authorization"].startswith("Basic ")
        assert len(headers) == 4
