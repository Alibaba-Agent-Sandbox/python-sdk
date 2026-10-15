"""Tests for capability model, gating, custom commands, and resolver."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

import agent_sandbox.api.capability as capability_mod
from agent_sandbox.api.capability import (
    ResolvedCapabilities,
    resolve_capabilities,
)
from agent_sandbox.api.code import CodeContextModule
from agent_sandbox.api.commands import CommandsModule
from agent_sandbox.api.files import FilesModule
from agent_sandbox.api.network import NetworkModule
from agent_sandbox.api.sandbox import Sandbox
from agent_sandbox.models.errors import (
    CapabilityNotSupportedError,
    TemplateParseError,
)
from agent_sandbox.models.process import (
    ProcessChunk,
    ProcessChunkType,
    ProcessResult,
)
from agent_sandbox.models.template import (
    DEFAULT_CAPABILITIES,
    STANDARD_CAPABILITIES,
    SandboxTemplate,
)
from agent_sandbox.transport.auth import EnvdTokenManager
from tests.test_api.conftest import (
    TEST_ENVD_TOKEN,
    TEST_ENVD_URL,
    _MockStreamReader,
    make_sandbox_info,
)

if TYPE_CHECKING:
    from pathlib import Path


# =====================================================================
# 1. Template / Capability Model tests
# =====================================================================


class TestStandardCapabilities:
    """Verify the vocabulary and default baseline constants."""

    def test_standard_vocab(self) -> None:
        assert {"shell", "files", "code", "terminal", "ports"} == STANDARD_CAPABILITIES

    def test_default_baseline(self) -> None:
        assert {"shell", "files", "code"} == DEFAULT_CAPABILITIES
        assert "terminal" not in DEFAULT_CAPABILITIES
        assert "ports" not in DEFAULT_CAPABILITIES


class TestSandboxTemplateCapabilities:
    """Test SandboxTemplate capability field validation."""

    def test_none_capabilities_is_valid(self) -> None:
        t = SandboxTemplate(name="test")
        assert t.capabilities is None

    def test_valid_capabilities(self) -> None:
        t = SandboxTemplate(name="test", capabilities=["shell", "files", "ports"])
        assert t.capabilities == ["shell", "files", "ports"]

    def test_invalid_capability_raises(self) -> None:
        with pytest.raises(ValidationError, match="Unknown capability"):
            SandboxTemplate(name="test", capabilities=["shell", "invalid_cap"])

    def test_empty_capabilities_is_valid(self) -> None:
        t = SandboxTemplate(name="test", capabilities=[])
        assert t.capabilities == []

    def test_removed_custom_commands_key_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="custom_commands"):
            SandboxTemplate.model_validate({"name": "test", "custom_commands": {"a": {"cmd": "x"}}})


# =====================================================================
# 2. CapabilityNotSupportedError
# =====================================================================


class TestCapabilityNotSupportedError:
    def test_error_code_and_message(self) -> None:
        err = CapabilityNotSupportedError("terminal")
        assert err.code == "E3004"
        assert "terminal" in err.message
        assert "terminal" in err.suggestion
        assert err.capability == "terminal"

    def test_custom_message(self) -> None:
        err = CapabilityNotSupportedError(
            "ports",
            message="Custom message",
            suggestion="Custom suggestion",
        )
        assert err.message == "Custom message"
        assert err.suggestion == "Custom suggestion"


# =====================================================================
# 3. Allowed-path smoke tests (gating removed; verify modules work)
# =====================================================================


class TestCommandsAllowedPath:
    """Verify commands.run works (no gating)."""

    @pytest.mark.asyncio
    async def test_run_allowed_with_shell(self) -> None:
        proto = AsyncMock()
        proto.start.return_value = _MockStreamReader(
            [
                ProcessChunk(type=ProcessChunkType.EXIT, exit_code=0),
            ]
        )
        mod = CommandsModule(
            envd_url=TEST_ENVD_URL,
            envd_token=EnvdTokenManager(TEST_ENVD_TOKEN),
            process_protocol=proto,
            capabilities={"shell"},
        )
        result = await mod.run("echo ok")
        assert isinstance(result, ProcessResult)


class TestNetworkAllowedPath:
    """Verify network.get_host works (no gating)."""

    def test_allowed_with_ports(self) -> None:
        mod = NetworkModule(
            sandbox_id="sbx-1",
            domain="example.com",
            capabilities={"ports"},
        )
        host = mod.get_host(8080)
        assert "8080" in host


# =====================================================================
# 4. Sandbox.capabilities / list_commands / run
# =====================================================================


class TestSandboxCapabilitiesProperty:
    """Test Sandbox.capabilities property."""

    def test_returns_effective_set(self) -> None:
        info = make_sandbox_info()
        resolved = ResolvedCapabilities(capabilities={"shell", "files"})
        sb = Sandbox(
            info=info,
            config=MagicMock(),
            http_client=AsyncMock(),
            auth=AsyncMock(),
            envd_token=EnvdTokenManager(TEST_ENVD_TOKEN),
            resolved_capabilities=resolved,
        )
        assert sb.capabilities == {"shell", "files"}
        # Contract: capabilities property returns a frozenset.
        assert isinstance(sb.capabilities, frozenset)

    def test_default_when_no_resolved(self) -> None:
        info = make_sandbox_info()
        sb = Sandbox(
            info=info,
            config=MagicMock(),
            http_client=AsyncMock(),
            auth=AsyncMock(),
            envd_token=EnvdTokenManager(TEST_ENVD_TOKEN),
        )
        assert sb.capabilities == set(DEFAULT_CAPABILITIES)


# =====================================================================
# 5. Resolver tests
# =====================================================================


class TestResolveCapabilities:
    """Test resolve_capabilities from local YAML."""

    @pytest.mark.asyncio
    async def test_resolve_from_local_yaml(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            name: test-template
            capabilities:
              - shell
              - files
              - terminal
        """)
        yaml_file = tmp_path / "template.yaml"
        yaml_file.write_text(yaml_content)

        result = await resolve_capabilities(
            "test-template",
            local_yaml_path=str(yaml_file),
        )
        assert result.capabilities == {"shell", "files", "terminal"}

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_defaults(self) -> None:
        """When template is not found, use DEFAULT_CAPABILITIES."""
        result = await resolve_capabilities("nonexistent-template-xyz")
        assert result.capabilities == set(DEFAULT_CAPABILITIES)

    @pytest.mark.asyncio
    async def test_remote_template_id_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """A cloud template id has no local YAML. That is not a warning."""
        with caplog.at_level("WARNING", logger="agent_sandbox.api.capability"):
            result = await resolve_capabilities("bwhjalty8fei0y5c63un")
        assert result.capabilities == set(DEFAULT_CAPABILITIES)
        assert "Could not resolve capabilities" not in caplog.text

    @pytest.mark.asyncio
    async def test_resolve_none_capabilities_uses_defaults(
        self,
        tmp_path: Path,
    ) -> None:
        """A template with no capabilities field uses DEFAULT_CAPABILITIES."""
        yaml_content = textwrap.dedent("""\
            name: minimal
        """)
        yaml_file = tmp_path / "template.yaml"
        yaml_file.write_text(yaml_content)

        result = await resolve_capabilities(
            "minimal",
            local_yaml_path=str(yaml_file),
        )
        assert result.capabilities == set(DEFAULT_CAPABILITIES)

    @pytest.mark.asyncio
    async def test_malformed_local_yaml_fails_closed(
        self,
        tmp_path: Path,
    ) -> None:
        """A matched template whose capabilities fail validation must NOT
        silently fall back to DEFAULT_CAPABILITIES (permission widening)."""
        yaml_content = textwrap.dedent("""\
            name: broken
            capabilities:
              - shell
              - not_a_real_capability
        """)
        yaml_file = tmp_path / "template.yaml"
        yaml_file.write_text(yaml_content)

        with pytest.raises(TemplateParseError):
            await resolve_capabilities(
                "broken",
                local_yaml_path=str(yaml_file),
            )

    @pytest.mark.asyncio
    async def test_malformed_scanned_template_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scanning ~/.abx/templates: a matched-but-malformed template
        raises instead of falling back to defaults."""
        cache = tmp_path / "templates"
        (cache / "broken-tmpl").mkdir(parents=True)
        (cache / "broken-tmpl" / "template.yaml").write_text(
            textwrap.dedent("""\
                name: broken-tmpl
                capabilities:
                  - bogus_capability
            """)
        )
        monkeypatch.setattr(capability_mod, "TEMPLATE_CACHE_DIR", cache)

        with pytest.raises(TemplateParseError):
            await resolve_capabilities("broken-tmpl")

    @pytest.mark.asyncio
    async def test_unreadable_scanned_template_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-dict / unreadable document cannot match, so it is skipped
        and resolution falls back to defaults (no fail-closed)."""
        cache = tmp_path / "templates"
        (cache / "junk").mkdir(parents=True)
        (cache / "junk" / "template.yaml").write_text("just a string\n")
        monkeypatch.setattr(capability_mod, "TEMPLATE_CACHE_DIR", cache)

        result = await resolve_capabilities("anything")
        assert result.capabilities == set(DEFAULT_CAPABILITIES)

    @pytest.mark.asyncio
    async def test_match_by_alias_field(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A template referenced by its ``alias`` field must be matched
        (previously only ``name`` was compared → wrongful DEFAULT fallback)."""
        cache = tmp_path / "templates"
        (cache / "some-dir").mkdir(parents=True)
        (cache / "some-dir" / "template.yaml").write_text(
            textwrap.dedent("""\
                name: real-name
                alias: my-alias
                capabilities:
                  - shell
                  - terminal
            """)
        )
        monkeypatch.setattr(capability_mod, "TEMPLATE_CACHE_DIR", cache)

        result = await resolve_capabilities("my-alias")
        assert result.capabilities == {"shell", "terminal"}

    @pytest.mark.asyncio
    async def test_match_by_aliases_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        cache = tmp_path / "templates"
        (cache / "dir").mkdir(parents=True)
        (cache / "dir" / "template.yaml").write_text(
            textwrap.dedent("""\
                name: real-name
                aliases:
                  - first-alias
                  - second-alias
                capabilities:
                  - ports
            """)
        )
        monkeypatch.setattr(capability_mod, "TEMPLATE_CACHE_DIR", cache)

        result = await resolve_capabilities("second-alias")
        assert result.capabilities == {"ports"}

    @pytest.mark.asyncio
    async def test_match_by_directory_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A template referenced by its containing directory name matches."""
        cache = tmp_path / "templates"
        (cache / "dir-name-ref").mkdir(parents=True)
        (cache / "dir-name-ref" / "template.yaml").write_text(
            textwrap.dedent("""\
                name: something-else
                capabilities:
                  - shell
                  - ports
            """)
        )
        monkeypatch.setattr(capability_mod, "TEMPLATE_CACHE_DIR", cache)

        result = await resolve_capabilities("dir-name-ref")
        assert result.capabilities == {"shell", "ports"}


# =====================================================================
# 6. Default capabilities in default-constructed modules
# =====================================================================


class TestDefaultCapabilities:
    """Modules get DEFAULT_CAPABILITIES when none are passed."""

    def test_commands_default(self) -> None:
        mod = CommandsModule(
            envd_url="http://x",
            envd_token=EnvdTokenManager("tok"),
            process_protocol=AsyncMock(),
        )
        assert mod._capabilities == set(DEFAULT_CAPABILITIES)

    def test_files_default(self) -> None:
        mod = FilesModule(
            envd_url="http://x",
            envd_token=EnvdTokenManager("tok"),
            filesystem_protocol=AsyncMock(),
        )
        assert mod._capabilities == set(DEFAULT_CAPABILITIES)

    def test_code_default(self) -> None:
        mod = CodeContextModule(
            sandbox_id="sbx-1",
            envd_url="http://x",
            envd_token=EnvdTokenManager("tok"),
            code_interpreter_protocol=AsyncMock(),
        )
        assert mod._capabilities == set(DEFAULT_CAPABILITIES)

    def test_network_default(self) -> None:
        mod = NetworkModule(
            sandbox_id="sbx-1",
            domain="example.com",
        )
        assert mod._capabilities == set(DEFAULT_CAPABILITIES)
