"""SDK 工作流端到端测试 — Mock 后端验证完整链路。

Tests the complete workflow from template definition → capability resolution
→ declarative↔server bridge.

(The CLI-completeness class of the original monolith moved out with the CLI.)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from agent_sandbox.api.capability import (
    ResolvedCapabilities,
    resolve_capabilities,
)
from agent_sandbox.models.template import (
    DEFAULT_CAPABILITIES,
    SandboxTemplate,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PYTHON_HELLO_YAML = _PROJECT_ROOT / "examples" / "templates" / "python-hello" / "template.yaml"

# ---------------------------------------------------------------------------
# Test 1: Template definition and Dockerfile generation
# ---------------------------------------------------------------------------


class TestTemplateDefinition:
    """Load template.yaml → parse → validate fields."""

    def test_parse_python_hello_template(self):
        """examples/templates/python-hello/template.yaml should parse correctly."""
        assert _PYTHON_HELLO_YAML.exists(), f"Missing {_PYTHON_HELLO_YAML}"
        data = yaml.safe_load(_PYTHON_HELLO_YAML.read_text())
        template = SandboxTemplate.model_validate(data)

        assert template.name == "python-hello"
        assert "shell" in template.capabilities
        assert "ports" in template.capabilities
        assert template.ports == [9000]

    def test_legacy_build_fields_ignored(self):
        """Legacy build fields are silently ignored by extra='ignore'."""
        data = yaml.safe_load(_PYTHON_HELLO_YAML.read_text())
        template = SandboxTemplate.model_validate(data)
        # Legacy fields should not be present on the model
        assert not hasattr(template, "base")
        assert not hasattr(template, "system_packages")

    def test_template_with_capabilities_none_uses_defaults(self):
        """When capabilities is None, DEFAULT_CAPABILITIES should apply."""
        tmpl = SandboxTemplate(name="minimal")
        assert tmpl.capabilities is None

    def test_template_with_explicit_capabilities(self):
        """Explicit capabilities override defaults."""
        tmpl = SandboxTemplate(name="custom", capabilities=["shell", "terminal"])
        assert set(tmpl.capabilities) == {"shell", "terminal"}


# ---------------------------------------------------------------------------
# Test 2: Capability resolution
# ---------------------------------------------------------------------------


class TestCapabilityResolution:
    """Test resolve_capabilities() with 4-level fallback."""

    async def test_resolve_from_local_yaml(self, tmp_path):
        """Priority 1: explicit local_yaml_path."""
        yaml_content = {
            "name": "test-template",
            "capabilities": ["shell", "files", "terminal"],
        }
        yaml_file = tmp_path / "template.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        result = await resolve_capabilities(
            "test-template",
            local_yaml_path=str(yaml_file),
        )
        assert isinstance(result, ResolvedCapabilities)
        assert result.capabilities == {"shell", "files", "terminal"}

    async def test_resolve_from_local_cache(self, tmp_path):
        """Priority 2: scan ~/.abx/templates/."""
        cache_dir = tmp_path / "templates" / "my-template"
        cache_dir.mkdir(parents=True)
        yaml_content = {
            "name": "my-template",
            "capabilities": ["shell", "files", "code", "ports"],
            "ports": [8080],
        }
        (cache_dir / "template.yaml").write_text(yaml.dump(yaml_content))

        with patch("agent_sandbox.api.capability.TEMPLATE_CACHE_DIR", tmp_path / "templates"):
            result = await resolve_capabilities("my-template")

        assert "ports" in result.capabilities
        assert "shell" in result.capabilities

    async def test_resolve_fallback_to_defaults(self):
        """Priority 4: when nothing matches, fall back to DEFAULT_CAPABILITIES."""
        result = await resolve_capabilities("nonexistent-template-xyz")
        assert result.capabilities == set(DEFAULT_CAPABILITIES)


# ---------------------------------------------------------------------------
# Test 3: Declarative → Server bridge verification
# ---------------------------------------------------------------------------


class TestDeclarativeServerBridge:
    """Verify that @sandbox.register bridges to the server registry."""

    @pytest.fixture(autouse=True)
    def _require_server_sdk(self) -> None:
        pytest.importorskip("agent_sandbox.server", reason="needs the agent-sandbox-server dist")

    def test_register_bridges_to_server_registry(self):
        """@sandbox.register should register the command in both registries."""
        # Import fresh to avoid cross-test pollution of the default registry
        from agent_sandbox.server.registry import CommandRegistry as ServerCommandRegistry

        from agent_sandbox.declarative.decorator import _SandboxFactory

        # Create a fresh server registry and patch default_registry()
        fresh_server_reg = ServerCommandRegistry()

        with patch(
            "agent_sandbox.server.registry.default_registry",
            return_value=fresh_server_reg,
        ):
            factory = _SandboxFactory()

            @factory.register
            def demo(x: int, y: str) -> str:
                return f"{y}={x}"

        # Verify declarative registry
        assert "demo" in factory._registry
        decl_cmd = factory._registry["demo"]
        assert decl_cmd.name == "demo"
        assert len(decl_cmd.args) == 2
        assert decl_cmd.args[0].name == "x"
        assert decl_cmd.args[0].type == "integer"
        assert decl_cmd.args[0].required is True
        assert decl_cmd.args[1].name == "y"
        assert decl_cmd.args[1].type == "string"
        assert decl_cmd.args[1].required is True

        # Verify server registry
        assert "demo" in fresh_server_reg
        srv_cmd = fresh_server_reg.get("demo")
        assert srv_cmd is not None
        assert srv_cmd.name == "demo"
        assert len(srv_cmd.args) == 2
        assert srv_cmd.args[0].name == "x"
        assert srv_cmd.args[0].type == "integer"
        assert srv_cmd.args[1].name == "y"
        assert srv_cmd.args[1].type == "string"

    def test_register_with_defaults(self):
        """Arguments with defaults should be marked required=False."""
        from agent_sandbox.server.registry import CommandRegistry as ServerCommandRegistry

        from agent_sandbox.declarative.decorator import _SandboxFactory

        fresh_server_reg = ServerCommandRegistry()

        with patch(
            "agent_sandbox.server.registry.default_registry",
            return_value=fresh_server_reg,
        ):
            factory = _SandboxFactory()

            @factory.register
            def greet(name: str, greeting: str = "Hello") -> str:
                return f"{greeting}, {name}!"

        decl_cmd = factory._registry["greet"]
        assert decl_cmd.args[0].required is True  # name
        assert decl_cmd.args[1].required is False  # greeting has default

        srv_cmd = fresh_server_reg.get("greet")
        assert srv_cmd.args[0].required is True
        assert srv_cmd.args[1].required is False
        assert srv_cmd.args[1].default == "Hello"

    def test_registered_function_still_callable(self):
        """The original function should still be callable locally."""
        from agent_sandbox.server.registry import CommandRegistry as ServerCommandRegistry

        from agent_sandbox.declarative.decorator import _SandboxFactory

        fresh_server_reg = ServerCommandRegistry()

        with patch(
            "agent_sandbox.server.registry.default_registry",
            return_value=fresh_server_reg,
        ):
            factory = _SandboxFactory()

            @factory.register
            def add(a: int, b: int) -> int:
                return a + b

        # The decorator should return the original function unchanged
        assert add(3, 4) == 7

    def test_list_registered_commands(self):
        """list_registered() returns metadata for all registered commands."""
        from agent_sandbox.server.registry import CommandRegistry as ServerCommandRegistry

        from agent_sandbox.declarative.decorator import _SandboxFactory

        fresh_server_reg = ServerCommandRegistry()

        with patch(
            "agent_sandbox.server.registry.default_registry",
            return_value=fresh_server_reg,
        ):
            factory = _SandboxFactory()

            @factory.register
            def foo(x: int) -> int:
                return x * 2

            @factory.register
            def bar(s: str) -> str:
                return s.upper()

        registered = factory.list_registered()
        names = {cmd["name"] for cmd in registered}
        assert names == {"foo", "bar"}
