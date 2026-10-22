"""Tests for the Sandbox core API class."""

from __future__ import annotations

import inspect
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_sandbox.api.capability import ResolvedCapabilities
from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.errors import CommandNotFoundError, ServerAPIError
from agent_sandbox.models.process import CodeResult
from agent_sandbox.models.sandbox import SandboxConfig, SandboxInfo, SandboxStatus
from agent_sandbox.providers.alicloud_express.auth import EnvdTokenManager
from agent_sandbox.transport.config import TransportConfig
from agent_sandbox.transport.http import HttpClient
from tests.test_api.conftest import (
    TEST_API_KEY,
    TEST_ENVD_TOKEN,
    TEST_ENVD_URL,
    TEST_SANDBOX_ID,
    make_sandbox_info,
)


class TestSandboxProperties:
    """Test Sandbox instance properties."""

    def test_id(self, sandbox: Sandbox) -> None:
        assert sandbox.id == TEST_SANDBOX_ID

    def test_status(self, sandbox: Sandbox) -> None:
        assert sandbox.status == SandboxStatus.RUNNING

    def test_url(self, sandbox: Sandbox) -> None:
        assert sandbox.url == TEST_ENVD_URL

    def test_info(self, sandbox: Sandbox) -> None:
        assert sandbox.info.sandbox_id == TEST_SANDBOX_ID
        assert sandbox.info.template == "python-base"

    def test_repr(self, sandbox: Sandbox) -> None:
        r = repr(sandbox)
        assert TEST_SANDBOX_ID in r
        assert "running" in r


class TestSandboxCreate:
    """Test Sandbox.create() classmethod."""

    @pytest.mark.asyncio
    async def test_create_returns_sandbox(self) -> None:
        info = make_sandbox_info()

        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        mock_http = AsyncMock(spec=HttpClient)
        mock_auth = AsyncMock()
        mock_auth.get_headers.return_value = {"X-API-KEY": TEST_API_KEY}

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_load_config,
            patch(
                "agent_sandbox.providers.alicloud_express.auth.create_auth_provider"
            ) as mock_create_auth,
            patch("agent_sandbox.transport.http.HttpClient") as mock_http_cls,
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_proto_cls,
        ):
            mock_load_config.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_create_auth.return_value = mock_auth
            mock_http_cls.return_value = mock_http
            mock_proto_cls.return_value = mock_sandbox_proto

            sb = await Sandbox.create(template="python-base", sandbox_api_key=TEST_API_KEY)

            assert sb.id == TEST_SANDBOX_ID
            assert sb.status == SandboxStatus.RUNNING
            assert sb.url == TEST_ENVD_URL
            mock_sandbox_proto.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_passes_config(self) -> None:
        info = make_sandbox_info()

        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_load_config,
            patch(
                "agent_sandbox.providers.alicloud_express.auth.create_auth_provider"
            ) as mock_create_auth,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_proto_cls,
        ):
            mock_load_config.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_create_auth.return_value = AsyncMock()
            mock_proto_cls.return_value = mock_sandbox_proto

            await Sandbox.create(
                template="node-base",
                timeout=600,
                envs={"FOO": "bar"},
                sandbox_api_key=TEST_API_KEY,
            )

            call_args = mock_sandbox_proto.create.call_args
            config: SandboxConfig = call_args[0][0]
            assert config.template == "node-base"
            assert config.timeout == 600
            assert config.env_vars == {"FOO": "bar"}

    @pytest.mark.asyncio
    async def test_create_default_request_timeout_is_none(self) -> None:
        """Without an explicit request_timeout, None is forwarded (default behaviour)."""
        info = make_sandbox_info()
        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_load_config,
            patch(
                "agent_sandbox.providers.alicloud_express.auth.create_auth_provider"
            ) as mock_create_auth,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_proto_cls,
        ):
            mock_load_config.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_create_auth.return_value = AsyncMock()
            mock_proto_cls.return_value = mock_sandbox_proto

            await Sandbox.create(template="base", sandbox_api_key=TEST_API_KEY)

            assert mock_sandbox_proto.create.call_args.kwargs["request_timeout"] is None

    @pytest.mark.asyncio
    async def test_create_explicit_request_timeout_forwarded(self) -> None:
        """An explicit request_timeout reaches SandboxProtocol.create() as a kwarg."""
        info = make_sandbox_info()
        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_load_config,
            patch(
                "agent_sandbox.providers.alicloud_express.auth.create_auth_provider"
            ) as mock_create_auth,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_proto_cls,
        ):
            mock_load_config.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_create_auth.return_value = AsyncMock()
            mock_proto_cls.return_value = mock_sandbox_proto

            await Sandbox.create(
                template="python-hello",
                request_timeout=120.0,
                sandbox_api_key=TEST_API_KEY,
            )

            assert mock_sandbox_proto.create.call_args.kwargs["request_timeout"] == 120.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_value", [0, -1, -0.5])
    async def test_create_rejects_non_positive_request_timeout(self, bad_value: float) -> None:
        """request_timeout must be positive when provided; else ValueError."""
        with pytest.raises(ValueError, match="request_timeout must be a positive number"):
            await Sandbox.create(
                template="base",
                request_timeout=bad_value,
                sandbox_api_key=TEST_API_KEY,
            )


class TestSandboxConnect:
    """Test Sandbox.connect() classmethod."""

    @pytest.mark.asyncio
    async def test_connect_returns_sandbox(self) -> None:
        info = make_sandbox_info()

        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.connect.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_load_config,
            patch(
                "agent_sandbox.providers.alicloud_express.auth.create_auth_provider"
            ) as mock_create_auth,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_proto_cls,
        ):
            mock_load_config.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_create_auth.return_value = AsyncMock()
            mock_proto_cls.return_value = mock_sandbox_proto

            sb = await Sandbox.connect(TEST_SANDBOX_ID, sandbox_api_key=TEST_API_KEY)

            assert sb.id == TEST_SANDBOX_ID
            mock_sandbox_proto.connect.assert_called_once_with(TEST_SANDBOX_ID)


class TestSandboxLifecycle:
    """Test kill, set_timeout, is_running, pause."""

    @pytest.mark.asyncio
    async def test_kill_calls_protocol_and_closes_http(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
        mock_http_client: AsyncMock,
    ) -> None:
        await sandbox.kill()
        mock_sandbox_protocol.kill.assert_called_once_with(TEST_SANDBOX_ID)
        mock_http_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_second_kill_is_a_noop(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
        mock_http_client: AsyncMock,
    ) -> None:
        await sandbox.kill()
        await sandbox.kill()
        mock_sandbox_protocol.kill.assert_called_once_with(TEST_SANDBOX_ID)
        mock_http_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_closes_http_even_on_protocol_error(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
        mock_http_client: AsyncMock,
    ) -> None:
        mock_sandbox_protocol.kill.side_effect = Exception("kill failed")
        with pytest.raises(Exception, match="kill failed"):
            await sandbox.kill()
        # HTTP client should still be closed
        mock_http_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_timeout(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        await sandbox.set_timeout(600)
        mock_sandbox_protocol.set_timeout.assert_called_once_with(TEST_SANDBOX_ID, 600)

    @pytest.mark.asyncio
    async def test_is_running(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        result = await sandbox.is_running()
        assert result is True
        mock_sandbox_protocol.is_running.assert_called_once_with(TEST_SANDBOX_ID)

    @pytest.mark.asyncio
    async def test_pause(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        await sandbox.pause()
        mock_sandbox_protocol.pause.assert_called_once_with(TEST_SANDBOX_ID)


class TestSandboxContextManager:
    """Test async context manager behavior."""

    @pytest.mark.asyncio
    async def test_context_manager_calls_kill_on_exit(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
        mock_http_client: AsyncMock,
    ) -> None:
        async with sandbox:
            pass
        mock_sandbox_protocol.kill.assert_called_once_with(TEST_SANDBOX_ID)
        mock_http_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_suppresses_kill_error(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        mock_sandbox_protocol.kill.side_effect = Exception("kill failed")
        # Should NOT raise
        async with sandbox:
            pass

    @pytest.mark.asyncio
    async def test_context_manager_enters_returns_sandbox(
        self,
        sandbox: Sandbox,
    ) -> None:
        async with sandbox as sb:
            assert sb is sandbox


class TestSandboxSubmodules:
    """Test lazy cached property sub-modules."""

    def test_commands_property(self, sandbox: Sandbox) -> None:
        from agent_sandbox.api.commands import CommandsModule

        cmds = sandbox.commands
        assert isinstance(cmds, CommandsModule)
        # Cached - same object
        assert sandbox.commands is cmds

    def test_files_property(self, sandbox: Sandbox) -> None:
        from agent_sandbox.api.files import FilesModule

        files = sandbox.files
        assert isinstance(files, FilesModule)
        assert sandbox.files is files

    def test_network_property(self, sandbox: Sandbox) -> None:
        from agent_sandbox.api.network import NetworkModule

        net = sandbox.network
        assert isinstance(net, NetworkModule)
        assert sandbox.network is net

    def test_code_property(self, sandbox: Sandbox) -> None:
        from agent_sandbox.api.code import CodeContextModule

        code = sandbox.code
        assert isinstance(code, CodeContextModule)
        assert sandbox.code is code


class TestSandboxRunCode:
    """Test the run_code convenience method."""

    @pytest.mark.asyncio
    async def test_run_code_delegates_to_code_module(
        self,
        sandbox: Sandbox,
        mock_code_interpreter_protocol: AsyncMock,
    ) -> None:
        result = await sandbox.run_code("print(42)")
        assert isinstance(result, CodeResult)
        # Should have called run_code on the code interpreter protocol
        mock_code_interpreter_protocol.run_code.assert_called()


class TestSandboxSyncVariants:
    """Test sync method wrappers exist and are callable."""

    def test_create_sync_exists(self) -> None:
        assert hasattr(Sandbox, "create_sync")
        assert callable(Sandbox.create_sync)

    def test_kill_sync_exists(self) -> None:
        assert hasattr(Sandbox, "kill_sync")
        assert callable(Sandbox.kill_sync)

    def test_run_code_sync_exists(self) -> None:
        assert hasattr(Sandbox, "run_code_sync")
        assert callable(Sandbox.run_code_sync)

    def test_resume_sync_exists(self) -> None:
        assert hasattr(Sandbox, "resume_sync")
        assert callable(Sandbox.resume_sync)

    def test_get_terminal_sync_exists(self) -> None:
        assert hasattr(Sandbox, "get_terminal_sync")
        assert callable(Sandbox.get_terminal_sync)

    def test_sync_factories_pass_subclass(self) -> None:
        """create_sync/connect_sync must inject cls. A staticmethod drops it."""
        seen: dict[str, Any] = {}

        class TypedSandbox(Sandbox):
            @classmethod
            async def create(cls, template: str = "base", **kwargs: Any) -> str:
                seen["create_cls"] = cls
                seen["template"] = template
                return "created"

            @classmethod
            async def connect(cls, sandbox_id: str, **kwargs: Any) -> str:
                seen["connect_cls"] = cls
                seen["sandbox_id"] = sandbox_id
                return "connected"

            @classmethod
            async def list(cls, **kwargs: Any) -> str:
                seen["list_cls"] = cls
                return "listed"

            @classmethod
            async def kill_by_id(cls, sandbox_id: str, **kwargs: Any) -> str:
                seen["kill_cls"] = cls
                seen["killed"] = sandbox_id
                return "killed"

        assert TypedSandbox.create_sync(template="my-alias") == "created"
        assert seen["create_cls"] is TypedSandbox
        assert seen["template"] == "my-alias"

        assert TypedSandbox.connect_sync("sbx-123") == "connected"
        assert seen["connect_cls"] is TypedSandbox
        assert seen["sandbox_id"] == "sbx-123"

        assert TypedSandbox.list_sync() == "listed"
        assert seen["list_cls"] is TypedSandbox

        assert TypedSandbox.kill_by_id_sync("sbx-123") == "killed"
        assert seen["kill_cls"] is TypedSandbox
        assert seen["killed"] == "sbx-123"

        signature = inspect.signature(Sandbox.connect_sync)
        assert "cls" not in signature.parameters
        assert "sandbox_id" in signature.parameters

    @pytest.mark.asyncio
    async def test_create_tries_alias_then_platform_id(self) -> None:
        info = make_sandbox_info(template="plat-id")
        info.alias_name = "cached-alias"
        seen: dict[str, Any] = {}

        protocol = AsyncMock()

        async def _create(config: SandboxConfig, **kwargs: Any) -> SandboxInfo:
            seen["template"] = config.template
            return info

        protocol.create.side_effect = _create

        from agent_sandbox.providers.base import ProviderInfra
        from agent_sandbox.providers.registry import get_provider
        from agent_sandbox.transport.config import TransportConfig

        provider = get_provider("alicloud-express")

        def _select(*_args: Any, **_kwargs: Any) -> tuple[Any, None]:
            return provider, None

        config = MagicMock()
        config.sandbox_domain = "example.com"
        http = MagicMock()

        async def _infra(*_args: Any, **_kwargs: Any) -> ProviderInfra:
            config = TransportConfig(sandbox_api_key="k")
            return ProviderInfra(config, MagicMock(), http, protocol)

        async def _resolve(*ids: str | None, **_kwargs: Any) -> ResolvedCapabilities:
            seen["ids"] = ids
            return ResolvedCapabilities(capabilities={"shell", "ports"}, matched=True)

        with (
            patch("agent_sandbox.api.sandbox._select_provider", _select),
            patch.object(provider, "build_infra", _infra),
            patch("agent_sandbox.api.capability.resolve_capabilities_for", _resolve),
        ):
            sb = await Sandbox.create(template="unique-alias", sandbox_api_key="k")

        assert seen["template"] == "unique-alias"
        assert seen["ids"] == ("unique-alias", "plat-id", "cached-alias")
        assert sb.capabilities == frozenset({"shell", "ports"})
        assert type(sb) is Sandbox

    @pytest.mark.asyncio
    async def test_connect_tries_template_then_alias(self) -> None:
        info = make_sandbox_info(template="plat-id")
        info.alias_name = "cached-alias"
        seen: dict[str, Any] = {}

        from agent_sandbox.providers.base import ProviderInfra
        from agent_sandbox.providers.registry import get_provider
        from agent_sandbox.transport.config import TransportConfig

        provider = get_provider("alicloud-express")

        def _select(*_args: Any, **_kwargs: Any) -> tuple[Any, None]:
            return provider, None

        protocol = AsyncMock()
        protocol.connect.return_value = info
        http = MagicMock()

        async def _infra(*_args: Any, **_kwargs: Any) -> ProviderInfra:
            return ProviderInfra(TransportConfig(sandbox_api_key="k"), MagicMock(), http, protocol)

        async def _resolve(*ids: str | None, **_kwargs: Any) -> ResolvedCapabilities:
            seen["ids"] = ids
            return ResolvedCapabilities(capabilities={"files"}, matched=True)

        with (
            patch("agent_sandbox.api.sandbox._select_provider", _select),
            patch.object(provider, "build_infra", _infra),
            patch("agent_sandbox.api.capability.resolve_capabilities_for", _resolve),
        ):
            sb = await Sandbox.connect("sbx-123", sandbox_api_key="k")

        assert seen["ids"] == ("plat-id", "cached-alias")
        assert sb.capabilities == frozenset({"files"})


class TestSandboxResourceParams:
    """Test cpu/memory/disk/gpu payload mapping through create()."""

    @pytest.mark.asyncio
    async def test_create_with_cpu_memory(self) -> None:
        info = make_sandbox_info()
        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_lc,
            patch("agent_sandbox.providers.alicloud_express.auth.create_auth_provider") as mock_ca,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_pc,
        ):
            mock_lc.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_ca.return_value = AsyncMock()
            mock_pc.return_value = mock_sandbox_proto

            await Sandbox.create(
                template="python-base",
                cpu=4,
                memory=8192,
                sandbox_api_key=TEST_API_KEY,
            )

            config: SandboxConfig = mock_sandbox_proto.create.call_args[0][0]
            assert config.cpu == 4
            assert config.memory == 8192
            payload = config.to_create_payload()
            assert payload["cpuCount"] == 4
            assert payload["memoryMB"] == 8192
            assert "diskSizeMB" not in payload
            assert "gpu" not in payload

    @pytest.mark.asyncio
    async def test_create_with_disk_gpu(self) -> None:
        info = make_sandbox_info()
        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_lc,
            patch("agent_sandbox.providers.alicloud_express.auth.create_auth_provider") as mock_ca,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_pc,
        ):
            mock_lc.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_ca.return_value = AsyncMock()
            mock_pc.return_value = mock_sandbox_proto

            await Sandbox.create(
                template="python-base",
                disk=10240,
                gpu="A10",
                sandbox_api_key=TEST_API_KEY,
            )

            config: SandboxConfig = mock_sandbox_proto.create.call_args[0][0]
            assert config.disk == 10240
            assert config.gpu == "A10"
            payload = config.to_create_payload()
            assert payload["diskSizeMB"] == 10240
            assert payload["gpu"] == "A10"
            assert "cpuCount" not in payload
            assert "memoryMB" not in payload

    @pytest.mark.asyncio
    async def test_create_without_resources_omits_keys(self) -> None:
        info = make_sandbox_info()
        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_lc,
            patch("agent_sandbox.providers.alicloud_express.auth.create_auth_provider") as mock_ca,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_pc,
        ):
            mock_lc.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_ca.return_value = AsyncMock()
            mock_pc.return_value = mock_sandbox_proto

            await Sandbox.create(template="base", sandbox_api_key=TEST_API_KEY)

            config: SandboxConfig = mock_sandbox_proto.create.call_args[0][0]
            payload = config.to_create_payload()
            assert "cpuCount" not in payload
            assert "memoryMB" not in payload
            assert "diskSizeMB" not in payload
            assert "gpu" not in payload


class TestSandboxResume:
    """Test resume() method."""

    @pytest.mark.asyncio
    async def test_resume(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        await sandbox.resume()
        mock_sandbox_protocol.resume.assert_called_once_with(TEST_SANDBOX_ID)


class TestSandboxRunCodeEnvs:
    """Test run_code envs pass-through."""

    @pytest.mark.asyncio
    async def test_run_code_passes_envs(
        self,
        sandbox: Sandbox,
        mock_code_interpreter_protocol: AsyncMock,
    ) -> None:
        await sandbox.run_code("print(1)", envs={"MY_VAR": "123"})
        call_kwargs = mock_code_interpreter_protocol.run_code.call_args.kwargs
        assert call_kwargs["envs"] == {"MY_VAR": "123"}

    @pytest.mark.asyncio
    async def test_run_code_without_envs(
        self,
        sandbox: Sandbox,
        mock_code_interpreter_protocol: AsyncMock,
    ) -> None:
        await sandbox.run_code("print(1)")
        call_kwargs = mock_code_interpreter_protocol.run_code.call_args.kwargs
        assert call_kwargs["envs"] is None


class TestSandboxRunCodeCallbacks:
    """Test run_code streaming callback pass-through."""

    @pytest.mark.asyncio
    async def test_run_code_forwards_callbacks(
        self,
        sandbox: Sandbox,
        mock_code_interpreter_protocol: AsyncMock,
    ) -> None:
        """run_code() forwards on_stdout/on_stderr/on_result to the protocol."""
        cb = MagicMock()
        await sandbox.run_code(
            "print(1)",
            on_stdout=cb,
            on_stderr=cb,
            on_result=cb,
        )
        call_kwargs = mock_code_interpreter_protocol.run_code.call_args.kwargs
        assert call_kwargs["on_stdout"] is cb
        assert call_kwargs["on_stderr"] is cb
        assert call_kwargs["on_result"] is cb

    @pytest.mark.asyncio
    async def test_run_code_without_callbacks_still_works(
        self,
        sandbox: Sandbox,
        mock_code_interpreter_protocol: AsyncMock,
    ) -> None:
        """run_code() without callbacks preserves existing behavior."""
        result = await sandbox.run_code("print(42)")
        assert isinstance(result, CodeResult)
        call_kwargs = mock_code_interpreter_protocol.run_code.call_args.kwargs
        assert call_kwargs["on_stdout"] is None
        assert call_kwargs["on_stderr"] is None
        assert call_kwargs["on_result"] is None


class TestSandboxSignedFileUrls:
    """Signature-only file URLs are refused by the live data plane."""

    @pytest.mark.asyncio
    async def test_get_upload_url_refuses_signature_only_url(
        self,
        sandbox: Sandbox,
    ) -> None:
        from agent_sandbox.models.errors import FileOperationError

        with pytest.raises(FileOperationError, match="X-Access-Token"):
            await sandbox.get_upload_url("/app/data.csv")

    @pytest.mark.asyncio
    async def test_get_download_url_refuses_signature_only_url(
        self,
        sandbox: Sandbox,
    ) -> None:
        from agent_sandbox.models.errors import FileOperationError

        with pytest.raises(FileOperationError, match="X-Access-Token"):
            await sandbox.get_download_url("/app/data.csv")

    @pytest.mark.asyncio
    async def test_e2b_upload_url_name_refuses_signature_only_url(
        self,
        sandbox: Sandbox,
    ) -> None:
        from agent_sandbox.models.errors import FileOperationError

        with pytest.raises(FileOperationError, match="upload_url"):
            await sandbox.upload_url("/app/data.csv")

    @pytest.mark.asyncio
    async def test_e2b_download_url_name_refuses_signature_only_url(
        self,
        sandbox: Sandbox,
    ) -> None:
        from agent_sandbox.models.errors import FileOperationError

        with pytest.raises(FileOperationError, match="download_url"):
            await sandbox.download_url("/app/data.csv")


class TestSandboxTerminal:
    """Test terminal wiring."""

    @pytest.mark.asyncio
    async def test_get_terminal_calls_terminal_session_create(
        self,
        sandbox: Sandbox,
    ) -> None:
        mock_session = AsyncMock()
        with patch(
            "agent_sandbox.providers.shared.e2b.terminal.TerminalSession.create",
            new_callable=AsyncMock,
            return_value=mock_session,
        ) as mock_create:
            terminal = await sandbox.get_terminal(cols=120, rows=40)
            assert terminal is mock_session
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["cols"] == 120
            assert call_kwargs["rows"] == 40


class TestSandboxEnvdUrlDerivation:
    """Test envd URL derivation when platform response omits envdUrl (Bug 1)."""

    @pytest.mark.asyncio
    async def test_create_derives_envd_url_when_missing(self) -> None:
        """create() should derive envd_url via build_envd_url when API omits it."""
        # Simulate real FC response: no envdUrl field
        info = SandboxInfo.model_validate(
            {
                "sandboxID": TEST_SANDBOX_ID,
                "templateID": "base",
                "envdAccessToken": TEST_ENVD_TOKEN,
                "envdVersion": "0.5.2",
            }
        )
        assert info.envd_url is None  # precondition

        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.create.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_lc,
            patch("agent_sandbox.providers.alicloud_express.auth.create_auth_provider") as mock_ca,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_pc,
        ):
            mock_lc.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_ca.return_value = AsyncMock()
            mock_pc.return_value = mock_sandbox_proto

            sb = await Sandbox.create(template="base", sandbox_api_key=TEST_API_KEY)

            expected_url = f"https://49983-{TEST_SANDBOX_ID}.cn-hangzhou.e2b.fc.aliyuncs.com"
            assert sb.url == expected_url
            assert sb.url != ""

    @pytest.mark.asyncio
    async def test_connect_derives_envd_url_when_missing(self) -> None:
        """connect() should derive envd_url via build_envd_url when API omits it."""
        info = SandboxInfo.model_validate(
            {
                "sandboxID": TEST_SANDBOX_ID,
                "templateID": "base",
                "envdAccessToken": TEST_ENVD_TOKEN,
                "envdVersion": "0.5.2",
            }
        )

        mock_sandbox_proto = AsyncMock()
        mock_sandbox_proto.connect.return_value = info

        with (
            patch("agent_sandbox.api.sandbox.load_config") as mock_lc,
            patch("agent_sandbox.providers.alicloud_express.auth.create_auth_provider") as mock_ca,
            patch("agent_sandbox.transport.http.HttpClient"),
            patch("agent_sandbox.providers.shared.e2b.sandbox.SandboxProtocol") as mock_pc,
        ):
            mock_lc.return_value = TransportConfig(sandbox_api_key=TEST_API_KEY)
            mock_ca.return_value = AsyncMock()
            mock_pc.return_value = mock_sandbox_proto

            sb = await Sandbox.connect(TEST_SANDBOX_ID, sandbox_api_key=TEST_API_KEY)

            expected_url = f"https://49983-{TEST_SANDBOX_ID}.cn-hangzhou.e2b.fc.aliyuncs.com"
            assert sb.url == expected_url

    @pytest.mark.asyncio
    async def test_refresh_info_derives_envd_url_when_missing(
        self,
        sandbox: Sandbox,
        mock_sandbox_protocol: AsyncMock,
    ) -> None:
        """refresh_info() should re-derive envd_url if platform still omits it."""
        refreshed_info = SandboxInfo.model_validate(
            {
                "sandboxID": TEST_SANDBOX_ID,
                "templateID": "python-base",
                "envdAccessToken": TEST_ENVD_TOKEN,
            }
        )
        mock_sandbox_protocol.get_info.return_value = refreshed_info

        result = await sandbox.refresh_info()

        expected_url = f"https://49983-{TEST_SANDBOX_ID}.cn-hangzhou.e2b.fc.aliyuncs.com"
        assert result.envd_url == expected_url
        assert sandbox.url == expected_url

    def test_existing_envd_url_not_overwritten(self) -> None:
        """If platform provides envdUrl, it should NOT be overwritten."""
        info = make_sandbox_info()  # includes envd_url
        original_url = info.envd_url
        assert original_url  # precondition

        sb = Sandbox(
            info=info,
            config=TransportConfig(sandbox_api_key=TEST_API_KEY),
            http_client=AsyncMock(spec=HttpClient),
            auth=AsyncMock(),
            envd_token=EnvdTokenManager(TEST_ENVD_TOKEN),
        )

        assert sb.url == original_url


def _server_client(handler: Any) -> ServerClient:
    return ServerClient(
        "http://sandbox.test:9000",
        http_client=httpx.AsyncClient(
            base_url="http://sandbox.test:9000", transport=httpx.MockTransport(handler)
        ),
    )


class TestSandboxRunNamedCommand:
    """``Sandbox.run(name, **kwargs)`` is ``POST /commands/{name}`` on the SandboxServer."""

    @pytest.mark.asyncio
    async def test_run_posts_kwargs_and_returns_value(self, sandbox: Sandbox) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"result": 42})

        sandbox.__dict__["server"] = _server_client(handler)

        assert await sandbox.run("add", x=1, y=2) == 42
        assert seen[0].method == "POST"
        assert seen[0].url.path == "/commands/add"
        assert json.loads(seen[0].content) == {"x": 1, "y": 2}

    @pytest.mark.asyncio
    async def test_name_is_a_valid_command_argument(self, sandbox: Sandbox) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"result": "Hello World"})

        sandbox.__dict__["server"] = _server_client(handler)

        assert await sandbox.run("hello", name="World") == "Hello World"
        assert seen[0].url.path == "/commands/hello"
        assert json.loads(seen[0].content) == {"name": "World"}

    @pytest.mark.asyncio
    async def test_unknown_command_raises_command_not_found(self, sandbox: Sandbox) -> None:
        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(404, json={"error": "not found", "type": "ValueError"})
        )
        with pytest.raises(CommandNotFoundError, match="not found"):
            await sandbox.run("nonexistent")

    @pytest.mark.asyncio
    async def test_unknown_command_includes_the_server_list(self, sandbox: Sandbox) -> None:
        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(
                404,
                json={
                    "error": "Unknown command 'nope'; available: hello",
                    "type": "ValueError",
                },
            )
        )
        with pytest.raises(CommandNotFoundError, match="available: hello"):
            await sandbox.run("nope")

    @pytest.mark.asyncio
    async def test_bad_arguments_are_a_command_argument_error(self, sandbox: Sandbox) -> None:
        from agent_sandbox.models.errors import CommandArgumentError

        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(
                400,
                json={
                    "error": "Unexpected argument(s): ['nope']; declared: ['name']",
                    "type": "ValueError",
                },
            )
        )
        with pytest.raises(CommandArgumentError, match="Unexpected argument") as caught:
            await sandbox.run("hello", nope=1)
        assert caught.value.status_code == 400
        assert caught.value.error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_command_exception_is_a_command_execution_error(self, sandbox: Sandbox) -> None:
        from agent_sandbox.models.errors import CommandExecutionError, ServerAPIError

        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(500, json={"error": "disk full", "type": "OSError"})
        )
        with pytest.raises(CommandExecutionError, match="OSError: disk full") as caught:
            await sandbox.run("hello")
        assert isinstance(caught.value, ServerAPIError)
        assert caught.value.error_type == "OSError"

    @pytest.mark.asyncio
    async def test_gateway_502_stays_a_server_api_error(self, sandbox: Sandbox) -> None:
        from agent_sandbox.models.errors import ServerAPIError

        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(502, json={"error": "bad gateway"})
        )
        with pytest.raises(ServerAPIError, match="bad gateway") as caught:
            await sandbox.run("hello")
        assert type(caught.value) is ServerAPIError

    @pytest.mark.asyncio
    async def test_run_timeout_is_not_a_command_argument(self, sandbox: Sandbox) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"result": "ok"})

        sandbox.__dict__["server"] = _server_client(handler)
        assert await sandbox.run("hello", name="Bob", timeout=5) == "ok"
        assert json.loads(seen[0].content) == {"name": "Bob"}

    @pytest.mark.asyncio
    async def test_command_failure_raises_server_api_error(self, sandbox: Sandbox) -> None:
        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(500, json={"error": "boom", "type": "RuntimeError"})
        )
        with pytest.raises(ServerAPIError, match="boom"):
            await sandbox.run("bad")

    @pytest.mark.asyncio
    async def test_server_port_selects_the_server_and_is_not_forwarded(
        self, sandbox: Sandbox
    ) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"result": "ok"})

        with patch.object(Sandbox, "server_at", return_value=_server_client(handler)) as server_at:
            assert await sandbox.run("ping", server_port=9100, a=1) == "ok"

        server_at.assert_called_once_with(9100)
        assert json.loads(seen[0].content) == {"a": 1}

    @pytest.mark.asyncio
    async def test_list_commands_returns_server_commands(self, sandbox: Sandbox) -> None:
        sandbox.__dict__["server"] = _server_client(
            lambda request: httpx.Response(
                200,
                json={
                    "commands": [
                        {
                            "name": "add",
                            "description": "Add",
                            "args": [{"name": "x", "type": "integer", "required": True}],
                        }
                    ]
                },
            )
        )
        commands = await sandbox.list_commands()
        assert [c.name for c in commands] == ["add"]
        assert commands[0].args[0].type == "integer"

    def test_client_side_command_mechanism_is_gone(self, sandbox: Sandbox) -> None:
        for removed in ("custom", "run_command", "reset_server_probe", "custom_sync"):
            assert not hasattr(sandbox, removed)
