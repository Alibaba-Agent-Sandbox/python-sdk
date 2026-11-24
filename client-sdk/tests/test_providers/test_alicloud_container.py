"""Public Client SDK paths against the Container Edition HTTP contract."""

from __future__ import annotations

import json
import struct
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from agent_sandbox import ProviderSandbox
from agent_sandbox._version import __version__
from agent_sandbox.models.errors import (
    InvalidAPIKeyError,
    InvalidCredentialsError,
    ProviderConfigError,
    ProviderFeatureNotSupportedError,
    ProviderInstallError,
    ProviderProtocolError,
    SandboxNotFoundError,
)
from agent_sandbox.models.sandbox import SandboxConfig, SandboxStatus
from agent_sandbox.providers import ProviderClient, ProviderLock, doctor, registry
from agent_sandbox.transport.config import TransportConfig

if TYPE_CHECKING:
    from collections.abc import Callable

_ID = "alicloud-container"
_LOCK = ProviderLock(provider=_ID, version=__version__)


def _frame(event: dict[str, Any]) -> bytes:
    payload = json.dumps({"event": event}).encode()
    return struct.pack(">BI", 0, len(payload)) + payload


def _mock(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    original = httpx.AsyncClient

    def use_mock(**kwargs: Any) -> httpx.AsyncClient:
        return original(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", use_mock)


def _config(**options: Any) -> TransportConfig:
    return TransportConfig(
        provider=_ID,
        sandbox_api_key="different-express-test-key",
        provider_options={
            "domain": "sandbox.example.test",
            "api_key": "manager-test-key",
            **options,
        },
    )


@pytest.mark.parametrize("private", [False, True])
async def test_builtin_lifecycle_execution_files_and_ports(monkeypatch, private):
    root = "https://private.example.test/proxy" if private else ""
    prefix = "/proxy/kruise" if private else ""
    api_path = f"{prefix}/api" if private else ""
    asset_path = f"{prefix}/sbx-one" if private else ""
    data_port = f"{asset_path}/49983" if private else ""
    interpreter_port = f"{asset_path}/49999" if private else ""
    requests = []
    state = "running"
    deleted = False
    missing_end = False
    end: dict[str, Any] = {"exited": True}
    token = "runtime-test-token"
    traffic = "traffic-test-token"
    info = {
        "sandboxID": "sbx-one",
        "templateID": "code-interpreter",
        "startedAt": "<unknown>",
        "envdVersion": "0.2.10",
        "envdUrl": "https://unexpected.example.test/steal",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal state, deleted, token, traffic
        requests.append(request)
        path = request.url.path
        control = path.startswith(f"{api_path}/sandboxes") or path.startswith(f"{api_path}/v2/")
        if control:
            assert request.headers["x-api-key"] == "manager-test-key"
            assert "authorization" not in request.headers
            assert "x-access-token" not in request.headers
            assert "e2b-traffic-access-token" not in request.headers
        else:
            assert "x-api-key" not in request.headers
            assert request.headers["x-access-token"] == token
            assert request.headers["e2b-traffic-access-token"] == traffic
            assert request.headers["e2b-sandbox-id"] == "sbx-one"
            assert request.url.host == (
                "private.example.test"
                if private
                else "49999-sbx-one.sandbox.example.test"
                if path.endswith("/execute")
                else "49983-sbx-one.sandbox.example.test"
            )
        if path == f"{api_path}/sandboxes" and request.method == "POST":
            assert json.loads(request.content) == {
                "templateID": "code-interpreter",
                "timeout": 300,
                "autoPause": True,
                "metadata": {"purpose": "test"},
                "envVars": {"WORKSPACE": "/tmp"},
            }
            return httpx.Response(
                201,
                json={
                    **info,
                    "envdAccessToken": token,
                    "trafficAccessToken": traffic,
                },
            )
        if path == f"{api_path}/v2/sandboxes":
            assert dict(request.url.params) == {"limit": "5", "state": "running"}
            return httpx.Response(200, json=[info])
        if path.endswith("/timeout"):
            assert json.loads(request.content) == {"timeout": 120}
            return httpx.Response(204)
        if path.endswith("/pause"):
            state = "paused"
            return httpx.Response(204)
        if path.endswith("/connect"):
            if private and path.startswith(f"{api_path}/v2"):
                return httpx.Response(404, text="404 page not found\n")
            assert json.loads(request.content) == ({"timeout": 300} if private else {})
            state = "running"
            token, traffic = "new-runtime-test-token", "new-traffic-test-token"
            return httpx.Response(
                200,
                json={
                    **info,
                    "state": state,
                    "envdAccessToken": token,
                    "trafficAccessToken": traffic,
                },
            )
        if path == f"{api_path}/sandboxes/sbx-one":
            if request.method == "DELETE":
                deleted = True
                return httpx.Response(204)
            if deleted:
                return httpx.Response(404, json={"message": "sandbox was not found"})
            return httpx.Response(200, json={**info, "state": state})
        if path == f"{data_port}/process.Process/Start":
            assert request.headers["content-type"] == "application/connect+json"
            (size,) = struct.unpack(">I", request.content[1:5])
            assert len(request.content[5:]) == size
            assert json.loads(request.content[5:])["stdin"] is False
            frames = _frame({"start": {"pid": 1}}) + _frame({"data": {"stdout": "aGk="}})
            if not missing_end:
                frames += _frame({"end": end})
            return httpx.Response(200, content=frames)
        if path == f"{data_port}/files":
            assert request.url.params["path"] == "/tmp/demo"
            if request.method == "POST":
                assert b"hello" in request.content
                return httpx.Response(201)
            return httpx.Response(200, content=b"hello")
        if path == f"{data_port}/filesystem.Filesystem/Remove":
            return httpx.Response(200, json={})
        if path == f"{interpreter_port}/execute":
            assert request.headers["e2b-sandbox-port"] == "49999"
            assert json.loads(request.content) == {"code": "2 + 2", "language": "python"}
            events = [{"type": "result", "text": "4", "is_main_result": True}]
            if missing_end:
                return httpx.Response(200, text='{"type":"result"')
            return httpx.Response(200, text="\n".join(map(json.dumps, events)))
        pytest.fail(f"Unexpected route: {request.method} {path}")

    _mock(monkeypatch, handler)
    opts = {"base_url": f"{root}/kruise/api", "protocol": "private"} if private else {}
    async with await ProviderClient.prepare(_LOCK, _config(**opts), download=True) as client:
        assert client.implementation == "python-native"
        assert client.features >= {"exec.stream", "files.rw"}
        sandbox = await client.create(
            SandboxConfig(
                template="code-interpreter",
                auto_pause=True,
                metadata={"purpose": "test"},
                env_vars={"WORKSPACE": "/tmp"},
            )
        )
        result = await sandbox.commands.run("printf hi")
        assert result.exit_code == 0 and result.stdout == "hi"
        chunks = [event async for event in sandbox.commands.stream("printf hi")]
        assert chunks[-1].exit_code == 0
        await sandbox.files.write("/tmp/demo", "hello")
        assert await sandbox.files.read("/tmp/demo") == "hello"
        await sandbox.files.remove("/tmp/demo")
        code = await sandbox.run_code("2 + 2", mode="default-context")
        assert code.exit_code == 0 and code.text == "4"
        end = {"exited": False, "exitCode": -1, "status": "signal: killed"}
        assert (await sandbox.commands.run("printf hi")).exit_code == -1
        end = {}
        with pytest.raises(ProviderProtocolError, match="invalid exit event"):
            await sandbox.commands.run("printf hi")
        missing_end = True
        with pytest.raises(ProviderProtocolError, match="without an exit event"):
            await sandbox.commands.run("printf hi")
        with pytest.raises(ProviderProtocolError, match="malformed interpreter output"):
            await sandbox.run_code("2 + 2", mode="default-context")

        listed = await client.list(status=SandboxStatus.RUNNING, limit=5)
        assert listed[0].started_at is None and listed[0].region == ""
        with pytest.raises(ProviderFeatureNotSupportedError, match="sandbox.list.offset"):
            await client.list(offset=1)
        await client.set_timeout(sandbox.id, 120)
        await sandbox.pause()
        assert not await sandbox.is_running()
        await sandbox.resume()
        info_after = await sandbox.refresh_info()
        assert info_after.status is SandboxStatus.RUNNING
        assert info_after.envd_access_token == token
        expected = (
            f"{root}/kruise/sbx-one/9000"
            if private
            else "https://9000-sbx-one.sandbox.example.test"
        )
        assert await sandbox.network.resolve(9000) == (
            expected,
            {"e2b-traffic-access-token": traffic},
        )
        async with await sandbox.application_client(9000) as application:
            assert application.base_url == expected
        with pytest.raises(ProviderFeatureNotSupportedError, match="code.execute"):
            await sandbox.run_code("2 + 2")
        with pytest.raises(ProviderFeatureNotSupportedError, match="pty"):
            await sandbox.get_terminal()
        await sandbox.close()
        assert not deleted
        async with await client.connect(f"{_ID}:sbx-one") as attached:
            assert attached.id == "sbx-one"
        await client.delete(sandbox.id)
        with pytest.raises(SandboxNotFoundError):
            await client.get(sandbox.id)
    assert requests and deleted


@pytest.mark.parametrize("status", [401, 403, 404, 500])
async def test_connect_does_not_retry_failed_operations(monkeypatch, status):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json={"message": "cloud API rejection"})

    _mock(monkeypatch, handler)
    async with await ProviderClient.prepare(_LOCK, _config()) as client:
        expected = {401: InvalidAPIKeyError, 404: SandboxNotFoundError}.get(
            status, httpx.HTTPStatusError
        )
        with pytest.raises(expected):
            await client.connect("sbx-one")
    assert [(r.method, r.url.path) for r in requests] == [("POST", "/v2/sandboxes/sbx-one/connect")]


async def test_public_provider_sandbox_selects_builtin_without_discovery(monkeypatch):
    def fail_discovery(*args, **kwargs):
        pytest.fail("The built-in implementation should skip plugin discovery.")

    monkeypatch.setattr(registry, "_load_entry_points", fail_discovery)
    monkeypatch.setattr(registry, "load_installed", fail_discovery)
    monkeypatch.setenv("ABX_ALICLOUD_CONTAINER_API_KEY", "manager-test-key")
    monkeypatch.setenv("ABX_ALICLOUD_CONTAINER_DOMAIN", "sandbox.example.test")
    monkeypatch.setenv("ABX_SANDBOX_API_KEY", "different-express-test-key")

    def handler(request):
        assert request.url.host == "api.sandbox.example.test"
        assert request.headers["x-api-key"] == "manager-test-key"
        if request.method == "POST":
            return httpx.Response(
                201, json={"sandboxID": "sbx-one", "envdAccessToken": "envd-token"}
            )
        return httpx.Response(204)

    _mock(monkeypatch, handler)
    assert registry.get_provider(_ID).kind == "builtin"
    sandbox = await ProviderSandbox.create(provider=_ID, template="code-interpreter")
    try:
        assert await sandbox.network.resolve(9000) == (
            "https://9000-sbx-one.sandbox.example.test",
            {"X-Access-Token": "envd-token"},
        )
    finally:
        await sandbox.kill()


async def test_container_credentials_and_unsupported_create_are_checked_before_io(monkeypatch):
    def no_request(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid or unsupported configuration must fail before network I/O.")

    _mock(monkeypatch, no_request)
    with pytest.raises(InvalidCredentialsError, match="ABX_ALICLOUD_CONTAINER_API_KEY"):
        await ProviderClient.prepare(
            _LOCK,
            TransportConfig(
                provider=_ID,
                sandbox_api_key="different-express-test-key",
                provider_options={"domain": "example.test"},
            ),
        )
    with pytest.raises(InvalidCredentialsError, match="ABX_ALICLOUD_CONTAINER_API_KEY"):
        await ProviderClient.prepare(_LOCK, _config(api_key=" "))
    with pytest.raises(ProviderConfigError, match="must end in /kruise/api"):
        await ProviderClient.prepare(
            _LOCK, _config(base_url="https://example.test", protocol="private")
        )
    async with await ProviderClient.prepare(_LOCK, _config()) as client:
        with pytest.raises(ProviderFeatureNotSupportedError, match="sandbox.create.cpu"):
            await client.create(SandboxConfig(template="code-interpreter", cpu=2))
        with pytest.raises(ProviderConfigError, match="DNS-label sandbox ID"):
            await client.get("invalid/id")


async def test_ambiguous_create_is_never_replayed(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502, json={"message": "lost upstream response"})

    _mock(monkeypatch, handler)
    async with await ProviderClient.prepare(_LOCK, _config()) as client:
        with pytest.raises(ProviderProtocolError) as captured:
            await client.create(SandboxConfig(template="code-interpreter"))
    assert captured.value.outcome == "unknown_outcome"
    assert len(calls) == 1


def test_install_verification_checks_the_installed_artifact(monkeypatch):
    def invalid_install(provider_id):
        assert provider_id == _ID
        raise SandboxNotFoundError("invalid installed artifact")

    monkeypatch.setattr(registry, "load_installed", invalid_install)
    assert registry.get_provider(_ID).kind == "builtin"
    with pytest.raises(ProviderInstallError, match="failed installed"):
        doctor.verify_handshake(_ID)
