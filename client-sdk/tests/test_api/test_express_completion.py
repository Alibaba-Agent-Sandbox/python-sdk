"""Regression coverage for Express session credentials and collision-free commands."""

from __future__ import annotations

import json
import traceback
from types import SimpleNamespace

# ruff: noqa: F811
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.errors import (
    QuotaExceededError,
    SandboxCreationError,
    TemplateNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo
from agent_sandbox.protocol.port_contract import PortContext
from agent_sandbox.providers import commands
from agent_sandbox.providers.alicloud_express.provider import AlicloudExpressProvider
from agent_sandbox.transport.config import explain_config, load_config
from agent_sandbox.utils.config_keys import get_key
from tests.iso import iso  # noqa: F401


def test_sts_token_resolves_as_secret(iso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIBABA_CLOUD_SECURITY_TOKEN", "placeholder-session-secret")
    config = load_config(provider="alicloud-express")
    assert config.security_token == "placeholder-session-secret"
    assert "placeholder-session-secret" not in repr(config)
    key = get_key("security_token", "alicloud-express")
    assert key is not None and key.secret and key.credential
    explanation = explain_config(provider="alicloud-express")["security_token"]
    assert explanation["secret"] is True
    assert explanation["value"] != "placeholder-session-secret"


def test_sts_does_not_restore_retired_environment_aliases(
    iso: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALICLOUD_SECURITY_TOKEN", "placeholder-not-configured")
    monkeypatch.setenv("ABX_ALICLOUD_EXPRESS_SECURITY_TOKEN", "placeholder-not-configured")
    assert load_config(provider="alicloud-express").security_token is None


def test_sts_token_reaches_command_engine(iso: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "EngineClient", lambda connection: connection)
    connection = commands._client(
        "alicloud-express",
        None,
        {
            "access_key_id": "placeholder-ak",
            "access_key_secret": "placeholder-sk",
            "security_token": "placeholder-sts",
        },
    )
    assert connection["security_token"] == "placeholder-sts"


async def test_explicit_command_arguments_keep_reserved_business_names() -> None:
    client = ServerClient("http://127.0.0.1:9000")
    request = AsyncMock(return_value={"result": "ok"})
    client._request = request
    arguments = {"timeout": 5, "request_timeout": 7, "arguments": [1], "name": "business"}
    try:
        assert await client.commands.invoke("probe", arguments, request_timeout=20) == "ok"
        assert request.call_args.kwargs == {"json_body": arguments, "timeout": 20}
    finally:
        await client.aclose()


async def test_legacy_command_keywords_keep_their_meaning() -> None:
    client = ServerClient("http://127.0.0.1:9000")
    request = AsyncMock(return_value={"result": "ok"})
    client._request = request
    try:
        assert (
            await client.commands.run("probe", timeout=20, arguments=1, request_timeout=2) == "ok"
        )
        assert request.call_args.kwargs == {
            "json_body": {"arguments": 1, "request_timeout": 2},
            "timeout": 20,
        }
    finally:
        await client.aclose()


@pytest.mark.parametrize("arguments", [None, [], "value", {1: "value"}])
async def test_invoke_requires_object_with_string_keys(arguments: Any) -> None:
    client = ServerClient("http://127.0.0.1:9000")
    request = AsyncMock()
    client._request = request
    try:
        with pytest.raises((TypeError, ValueError)):
            await client.commands.invoke("probe", arguments)
        request.assert_not_awaited()
    finally:
        await client.aclose()


def test_traffic_token_is_retained_but_never_default_serialized() -> None:
    info = SandboxInfo(sandboxID="example", trafficAccessToken="placeholder-traffic")
    assert info.traffic_access_token == "placeholder-traffic"
    assert "placeholder-traffic" not in repr(info)
    assert "placeholder-traffic" not in info.model_dump_json(by_alias=True)


async def test_express_application_uses_only_traffic_gateway_token() -> None:
    provider = AlicloudExpressProvider()
    context = PortContext(
        "example",
        "example.invalid",
        True,
        "placeholder-envd",
        traffic_access_token="placeholder-traffic",
    )
    descriptor = await provider.application_endpoint(context, 9000)
    assert descriptor["headers"] == {"e2b-traffic-access-token": "placeholder-traffic"}
    assert "placeholder-envd" not in str(descriptor)


def test_create_network_fields_survive_wire_conversion() -> None:
    config = SandboxConfig(
        network={"allow_out": [], "allow_public_traffic": False, "rules": {}},
        allow_internet_access=False,
    )
    payload = config.to_create_payload()
    assert payload["network"] == {"allowOut": [], "allowPublicTraffic": False, "rules": {}}
    assert payload["allowInternetAccess"] is False
    assert payload["secure"] is True


async def test_typed_express_pause_resume_uses_documented_routes() -> None:
    provider = AlicloudExpressProvider()
    infra = await provider.build_infra(load_config(sandbox_api_key="placeholder-key"))
    http = infra.http_client
    http.platform_request = AsyncMock(
        side_effect=[
            httpx.Response(204),
            httpx.Response(
                201,
                json={
                    "sandboxID": "example",
                    "envdAccessToken": "placeholder-new-envd",
                    "trafficAccessToken": "placeholder-new-traffic",
                },
            ),
        ]
    )
    try:
        await infra.sandbox_protocol.pause("example")
        info = await infra.sandbox_protocol.resume("example")
        assert http.platform_request.call_args_list[0].args == ("POST", "/sandboxes/example/pause")
        assert http.platform_request.call_args_list[0].kwargs["json"] == {"memory": True}
        assert http.platform_request.call_args_list[1].args == (
            "POST",
            "/sandboxes/example/connect",
        )
        assert info.envd_access_token == "placeholder-new-envd"
        assert info.traffic_access_token == "placeholder-new-traffic"
    finally:
        await infra.http_client.close()


async def test_resume_rebinds_existing_object_and_cached_modules(sandbox: Sandbox) -> None:
    previous_files, previous_commands, previous_network = (
        sandbox.files,
        sandbox.commands,
        sandbox.network,
    )
    sandbox._sandbox_protocol.resume.return_value = SandboxInfo(
        sandboxID=sandbox.id,
        envdUrl="https://new-envd.example.invalid",
        envdAccessToken="placeholder-new-envd",
        trafficAccessToken="placeholder-new-traffic",
    )
    original_template = sandbox._info.template
    await sandbox.resume()
    assert sandbox._info.template == original_template
    assert sandbox.url == "https://new-envd.example.invalid"
    assert sandbox._envd_token.token == "placeholder-new-envd"
    assert sandbox._info.traffic_access_token == "placeholder-new-traffic"
    assert sandbox.files is not previous_files
    assert sandbox.commands is not previous_commands
    assert sandbox.network is not previous_network
    assert sandbox.files._envd_url == sandbox.url
    assert sandbox.commands._envd_token.token == "placeholder-new-envd"


async def test_refresh_preserves_traffic_token_omitted_by_get(sandbox: Sandbox) -> None:
    sandbox._info.traffic_access_token = "placeholder-existing"
    previous_files = sandbox.files
    sandbox._sandbox_protocol.get_info.return_value = SandboxInfo(
        sandboxID=sandbox.id, envdUrl=sandbox.url
    )
    await sandbox.refresh_info()
    assert sandbox._info.traffic_access_token == "placeholder-existing"
    assert sandbox.files is previous_files


async def test_attach_and_application_client_never_post_to_connect(
    iso: Any, httpx_mock: Any
) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://api.cn-hangzhou.e2b.fc.aliyuncs.com/sandboxes/example",
        json={"sandboxID": "example", "envdAccessToken": "placeholder-envd"},
    )
    sandbox = await Sandbox.connect(
        "example", sandbox_api_key="placeholder-key", traffic_access_token="placeholder-explicit"
    )
    try:
        async with await sandbox.application_client(token="placeholder-app") as application:
            assert application.auth_headers()["e2b-traffic-access-token"] == "placeholder-explicit"
            assert application.auth_headers()["Authorization"] == "Bearer placeholder-app"
        assert [request.method for request in httpx_mock.get_requests()] == ["GET"]
    finally:
        await sandbox.close()


async def test_application_token_override_does_not_mutate_session(sandbox: Sandbox) -> None:
    sandbox._info.traffic_access_token = "placeholder-session"
    async with await sandbox.application_client(
        traffic_access_token="placeholder-override"
    ) as application:
        assert application.auth_headers()["e2b-traffic-access-token"] == "placeholder-override"
    assert sandbox._info.traffic_access_token == "placeholder-session"


async def test_provider_create_private_network_keeps_gateway_credentials(
    iso: Any, httpx_mock: Any
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://api.cn-hangzhou.e2b.fc.aliyuncs.com/sandboxes",
        status_code=201,
        json={
            "sandboxID": "example",
            "envdAccessToken": "placeholder-envd",
            "trafficAccessToken": "placeholder-created-traffic",
        },
    )
    sandbox = await Sandbox.create(
        sandbox_api_key="placeholder-key",
        network={"allow_public_traffic": False},
        allow_internet_access=False,
    )
    try:
        body = json.loads(httpx_mock.get_requests()[0].content)
        assert body["network"] == {"allowPublicTraffic": False}
        assert body["secure"] is True and body["allowInternetAccess"] is False
        async with await sandbox.application_client() as application:
            assert application.auth_headers()["e2b-traffic-access-token"] == (
                "placeholder-created-traffic"
            )
        assert len(httpx_mock.get_requests()) == 1
    finally:
        await sandbox.close()


async def test_provider_invoke_keeps_transport_names_in_business_arguments(
    sandbox: Sandbox,
) -> None:
    client = ServerClient("http://127.0.0.1:9000")
    request = AsyncMock(return_value={"result": 42})
    client._request = request
    sandbox.application_client = AsyncMock(return_value=client)
    arguments = {"server_port": 123, "timeout": 5, "request_timeout": 7}
    assert (
        await sandbox.invoke(
            "probe", arguments, application_token="placeholder-app", request_timeout=30
        )
        == 42
    )
    sandbox.application_client.assert_awaited_once_with(9000, token="placeholder-app")
    assert request.call_args.kwargs == {"json_body": arguments, "timeout": 30}


@pytest.mark.parametrize("operation", ["get_info_by_id", "set_timeout_by_id"])
async def test_sts_reaches_direct_control_plane_calls(
    operation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol = AsyncMock()
    protocol.get_info.return_value = SandboxInfo(sandboxID="example")
    build = AsyncMock(return_value=SimpleNamespace(sandbox_protocol=protocol, close=AsyncMock()))
    monkeypatch.setattr("agent_sandbox.api.sandbox._provider_infra", build)
    args = ("example", 600) if operation == "set_timeout_by_id" else ("example",)
    await getattr(Sandbox, operation)(*args, security_token="placeholder-sts")
    assert build.call_args.args[1]["security_token"] == "placeholder-sts"


async def test_fallback_session_uses_express_lifecycle_protocol() -> None:
    from agent_sandbox.providers.alicloud_express.sandbox import SandboxProtocol

    http = SimpleNamespace(
        platform_request=AsyncMock(return_value=httpx.Response(201, json={"sandboxID": "example"}))
    )
    protocol = AlicloudExpressProvider().session_protocols(http)["sandbox_protocol"]
    assert isinstance(protocol, SandboxProtocol)
    await protocol.resume("example")
    assert http.platform_request.call_args.args == ("POST", "/sandboxes/example/connect")


@pytest.mark.parametrize(
    "status, error_type",
    [(400, SandboxCreationError), (404, TemplateNotFoundError), (429, QuotaExceededError)],
)
async def test_network_create_errors_redact_reflection_and_detach_raw_exception(
    status: int, error_type: type[SandboxCreationError]
) -> None:
    from agent_sandbox.providers.alicloud_express.sandbox import SandboxProtocol

    replacement = json.dumps([{"key": "x-model-key", "value": "placeholder-replacement-secret"}])
    network = {
        "rules": {
            "example.invalid": [
                {
                    "transform": {
                        "headers": {
                            "Authorization": "Bearer placeholder-header-secret",
                            "fc.sandbox.network.header-value-replacements": replacement,
                        }
                    }
                }
            ]
        }
    }
    config = SandboxConfig(network=network)
    request = httpx.Request(
        "POST", "https://api.example.invalid/sandboxes", json=config.to_create_payload()
    )
    response = httpx.Response(
        status,
        request=request,
        json={
            "message": (
                "Invalid header: placeholder-header-secret; "
                "replacement placeholder-replacement-secret"
            )
        },
    )
    http = SimpleNamespace(
        platform_request=AsyncMock(
            side_effect=httpx.HTTPStatusError("Cloud rejection", request=request, response=response)
        )
    )
    with pytest.raises(error_type) as caught:
        await SandboxProtocol(http).create(config)
    error = caught.value
    assert "Invalid header" in error.message
    assert getattr(error, "status_code", None) == status
    assert error.__context__ is None and error.__cause__ is None
    rendered = "".join(traceback.format_exception(error)) + repr(error.to_dict())
    assert "placeholder-header-secret" not in rendered
    assert "placeholder-replacement-secret" not in rendered


async def test_network_create_keeps_nonsecret_error_detail() -> None:
    from agent_sandbox.providers.alicloud_express.sandbox import SandboxProtocol

    request = httpx.Request("POST", "https://api.example.invalid/sandboxes")
    response = httpx.Response(400, request=request, json={"message": "Unsupported instance size"})
    http = SimpleNamespace(
        platform_request=AsyncMock(
            side_effect=httpx.HTTPStatusError("Cloud rejection", request=request, response=response)
        )
    )
    with pytest.raises(SandboxCreationError, match="Unsupported instance size") as caught:
        await SandboxProtocol(http).create(SandboxConfig(network={"allow_out": []}))
    assert caught.value.__cause__ is not None
