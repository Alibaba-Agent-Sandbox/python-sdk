"""Tests for SandboxTemplate and TemplateRef models."""

from __future__ import annotations

from agent_sandbox.models.template import SandboxTemplate, TemplateRef


class TestSandboxTemplate:
    """Current schema preserves application metadata and rejects old contracts."""

    def test_workflow_template(self) -> None:
        from tests.workflow_fixtures import workflow_manifest

        tmpl = SandboxTemplate.model_validate(workflow_manifest())
        assert tmpl.spec_version == 4
        assert tmpl.default_workflow == "application"
        assert tmpl.env == {} and tmpl.ports == []
        assert "code" not in tmpl.discovery_capabilities()

    def test_application_topology_round_trips(self) -> None:
        from tests.workflow_fixtures import workflow_manifest

        topology = {"workers": {"limits": {"cpu": 0.5}}}
        tmpl = SandboxTemplate.model_validate(workflow_manifest(deployment=topology))
        assert tmpl.model_dump()["deployment"] == topology

    def test_old_missing_version_is_rejected(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SandboxTemplate(name="old")


class TestTemplateRef:
    """Tests for TemplateRef model."""

    def test_default(self) -> None:
        ref = TemplateRef()
        assert ref.owner is None
        assert ref.repo is None
        assert ref.tag is None
        assert ref.path is None
        assert ref.is_builtin is False
        assert ref.registry_url == "https://github.com"
        assert ref.registry_type == "github"
        assert ref.local_path is None

    def test_builtin(self) -> None:
        ref = TemplateRef(is_builtin=True, tag="base")
        assert ref.is_builtin is True
        assert ref.tag == "base"
        assert ref.path is None

    def test_github_ref(self) -> None:
        ref = TemplateRef(
            owner="org",
            repo="sandbox-templates",
            tag="v1.0",
            registry_url="https://github.com",
        )
        assert ref.owner == "org"
        assert ref.repo == "sandbox-templates"
        assert ref.tag == "v1.0"
        assert ref.path is None
        assert ref.is_builtin is False

    def test_path_field(self) -> None:
        """path 字段应正确存储子目录信息。"""
        ref = TemplateRef(
            owner="demo",
            repo="demo",
            tag="v1.0",
            path="templates/python-data",
        )
        assert ref.owner == "demo"
        assert ref.repo == "demo"
        assert ref.tag == "v1.0"
        assert ref.path == "templates/python-data"
        assert ref.is_builtin is False

    def test_path_field_default_none(self) -> None:
        """path 字段默认为 None。"""
        ref = TemplateRef(owner="a", repo="b")
        assert ref.path is None

    def test_path_with_nested_dirs(self) -> None:
        """深层子目录路径。"""
        ref = TemplateRef(
            owner="org",
            repo="templates",
            path="a/b/c/d",
        )
        assert ref.path == "a/b/c/d"

    def test_registry_type_default(self) -> None:
        """registry_type 默认值为 github。"""
        ref = TemplateRef()
        assert ref.registry_type == "github"

    def test_registry_type_local(self) -> None:
        """registry_type 可设为 local。"""
        ref = TemplateRef(registry_type="local", local_path="/tmp/my-template")
        assert ref.registry_type == "local"
        assert ref.local_path == "/tmp/my-template"

    def test_local_path_default_none(self) -> None:
        """local_path 默认为 None。"""
        ref = TemplateRef()
        assert ref.local_path is None

    def test_local_ref_full(self) -> None:
        """完整的本地模板引用。"""
        ref = TemplateRef(
            registry_type="local",
            local_path="/home/user/templates/python",
            is_builtin=False,
        )
        assert ref.registry_type == "local"
        assert ref.local_path == "/home/user/templates/python"
        assert ref.is_builtin is False
        assert ref.owner is None
        assert ref.repo is None
