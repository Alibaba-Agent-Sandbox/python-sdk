"""KI-006: a Platform API 401 surfaces as ``AuthenticationError`` (CLI exit code 3)."""

from __future__ import annotations

import httpx
import pytest

from agent_sandbox.models.errors import (
    AuthenticationError,
    InvalidAPIKeyError,
    InvalidCredentialsError,
    SandboxCreationError,
    SandboxError,
)
from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient
from tests.test_known_issues.helpers import API, make_http

SECRET = "e2e-invalid-key-0000000000000000"


async def test_list_with_a_rejected_key_raises_authentication_error(httpx_mock) -> None:
    httpx_mock.add_response(method="GET", status_code=401, json={"message": "invalid api key"})
    with pytest.raises(AuthenticationError) as err:
        await SandboxProtocol(make_http(SECRET)).list()
    assert isinstance(err.value, InvalidAPIKeyError)
    assert not isinstance(err.value, httpx.HTTPError)
    assert err.value.code == "E1001"
    assert SECRET not in str(err.value)
    assert API not in str(err.value)


async def test_create_with_a_rejected_key_is_an_authentication_error(httpx_mock) -> None:
    from agent_sandbox.models.sandbox import SandboxConfig

    httpx_mock.add_response(method="POST", status_code=401, json={"message": "invalid api key"})
    with pytest.raises(AuthenticationError) as err:
        await SandboxProtocol(make_http(SECRET)).create(SandboxConfig(template="base"))
    assert not isinstance(err.value, SandboxCreationError)


async def test_sandbox_list_api_with_wrong_key(httpx_mock) -> None:
    from agent_sandbox.api.sandbox import Sandbox

    httpx_mock.add_response(method="GET", status_code=401, content=b"")
    with pytest.raises(AuthenticationError):
        await Sandbox.list(sandbox_api_key=SECRET, sandbox_base_url=API)


async def test_aksk_auth_maps_to_invalid_credentials(httpx_mock) -> None:
    class _Aksk:
        def __init__(self) -> None:  # no network / signing in this test
            pass

        async def get_headers(self) -> dict[str, str]:
            return {}

        async def refresh(self) -> None:
            pass

        def authentication_error(self, path: str) -> InvalidCredentialsError:
            return InvalidCredentialsError("Custom credentials were rejected")

    httpx_mock.add_response(method="GET", status_code=401, content=b"")
    client = HttpClient(TransportConfig(sandbox_base_url=API, http2=False), _Aksk())
    with pytest.raises(InvalidCredentialsError):
        await client.platform_request("GET", "/sandboxes")


@pytest.mark.parametrize("status", [403, 404, 429, 500])
async def test_other_statuses_are_left_to_the_callers(httpx_mock, status: int) -> None:
    httpx_mock.add_response(method="GET", status_code=status, json={})
    with pytest.raises(httpx.HTTPStatusError):
        await make_http().platform_request("GET", "/sandboxes")


async def test_authentication_error_is_a_sandbox_error(httpx_mock) -> None:
    httpx_mock.add_response(method="GET", status_code=401, json={})
    with pytest.raises(SandboxError):
        await make_http().platform_request("GET", "/sandboxes/x")
