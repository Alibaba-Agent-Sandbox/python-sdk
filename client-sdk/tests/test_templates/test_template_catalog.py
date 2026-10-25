"""Offline validation of the ``examples/templates/`` fixtures.

``examples/templates/`` no longer holds a publishable template collection.
The single source of truth for official & community templates — content,
the machine-readable index, releases and CI — is the dedicated repository
``alibaba-agent-sandbox/awesome-templates``.  This repository keeps only a minimal
**fixture** (``python-hello``) so that the install / server pipelines stay
testable fully offline.

Covered contracts
-----------------
(a) ``template.yaml`` exists and parses through the *real* production
    loader (``utils.registry.load_template_from_yaml``) into a valid
    ``SandboxTemplate``.
(b) Required fields are present; every ``capabilities`` token is inside
    ``STANDARD_CAPABILITIES``.
(c) ``Dockerfile`` and ``README.md`` exist next to the YAML.
(d) The directory is *explicitly marked as a fixture* (README + YAML banner)
    and contains only the expected fixture folders — it must never
    silently grow back into a duplicate template collection.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
import yaml
from pydantic import ValidationError

from agent_sandbox.models.template import (
    SandboxTemplate,
)
from agent_sandbox.utils.registry import load_template_from_yaml

from .conftest import (
    EXPECTED_FIXTURE_TEMPLATES,
    REQUIRED_TEMPLATE_FILES,
    REQUIRED_YAML_KEYS,
    SOURCE_OF_TRUTH_URL,
)

if TYPE_CHECKING:
    from pathlib import Path

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _yaml_path(template_dir: Path) -> Path:
    return template_dir / "template.yaml"


def _load(template_dir: Path) -> SandboxTemplate:
    """Load through the real loader — the same code path ``abx install`` uses."""
    return load_template_from_yaml(_yaml_path(template_dir))


def _raw(template_dir: Path) -> dict:
    """Raw YAML mapping (pre-model), to assert on keys that the model defaults."""
    data = yaml.safe_load(_yaml_path(template_dir).read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{_yaml_path(template_dir)} is not a YAML mapping"
    return data


# ---------------------------------------------------------------------------
# (c) Required files
# ---------------------------------------------------------------------------


class TestRequiredFiles:
    """Every template folder ships the three mandatory files."""

    @pytest.mark.parametrize("filename", REQUIRED_TEMPLATE_FILES)
    def test_required_file_exists(self, template_dir: Path, filename: str) -> None:
        path = template_dir / filename
        assert path.is_file(), (
            f"{template_dir.name}: required file {filename!r} is missing (expected at {path})"
        )
        assert path.stat().st_size > 0, f"{template_dir.name}: {filename} exists but is empty"

    def test_no_unexpected_required_file_names(self, template_dir: Path) -> None:
        """Guard against typos such as ``sandbox_template.yaml`` / ``dockerfile``."""
        present = {p.name for p in template_dir.iterdir()}
        for alias in ("sandbox_template.yaml", "dockerfile"):
            assert alias not in present, (
                f"{template_dir.name}: found {alias!r} — the canonical name is "
                f"{REQUIRED_TEMPLATE_FILES[0]!r} / 'Dockerfile'"
            )


# ---------------------------------------------------------------------------
# (a) + (b) YAML validity
# ---------------------------------------------------------------------------


class TestTemplateYaml:
    """``template.yaml`` parses and satisfies the model contract."""

    def test_parses_with_real_loader(self, template_dir: Path) -> None:
        tmpl = _load(template_dir)
        assert isinstance(tmpl, SandboxTemplate)
        assert tmpl.name == template_dir.name

    def test_required_keys_declared_explicitly(self, template_dir: Path) -> None:
        raw = _raw(template_dir)
        missing = [k for k in REQUIRED_YAML_KEYS if k not in raw]
        assert not missing, (
            f"{template_dir.name}: template.yaml is missing required key(s): {missing}"
        )

    def test_name_is_kebab_case(self, template_dir: Path) -> None:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", template_dir.name), (
            f"{template_dir.name}: template names must be kebab-case"
        )

    def test_version_is_semver(self, template_dir: Path) -> None:
        version = _load(template_dir).version
        assert _SEMVER_RE.match(version), (
            f"{template_dir.name}: version {version!r} is not semver-like"
        )

    def test_description_non_empty(self, template_dir: Path) -> None:
        assert _load(template_dir).description.strip(), (
            f"{template_dir.name}: description must not be blank"
        )

    def test_tags_non_empty_and_lowercase(self, template_dir: Path) -> None:
        tags = _load(template_dir).tags
        assert tags, f"{template_dir.name}: declare at least one tag"
        for tag in tags:
            assert tag == tag.strip().lower(), (
                f"{template_dir.name}: tag {tag!r} should be trimmed lowercase"
            )

    def test_resources_when_declared_are_positive(self, template_dir: Path) -> None:
        tmpl = _load(template_dir)
        if tmpl.cpu_count is not None:
            assert tmpl.cpu_count > 0
        if tmpl.memory_mb is not None:
            assert tmpl.memory_mb > 0

    def test_dockerfile_has_from_line(self, template_dir: Path) -> None:
        """The hand-written Dockerfile must have a valid FROM line."""
        dockerfile = (template_dir / "Dockerfile").read_text(encoding="utf-8")
        from_lines = [
            line.strip()
            for line in dockerfile.splitlines()
            if line.strip().upper().startswith("FROM ")
        ]
        assert from_lines, f"{template_dir.name}: Dockerfile has no FROM line"


class TestWorkflows:
    """Fixture application service is distinct from a native interpreter."""

    def test_template_has_single_startup(self, template_dir: Path) -> None:
        tmpl = _load(template_dir)
        assert tmpl.spec_version == 5

    def test_no_old_capability_input(self, template_dir: Path) -> None:
        assert "capabilities" not in _raw(template_dir)
        assert "code" not in _load(template_dir).discovery_capabilities()

    def test_application_port_matches_provided_service(self, template_dir: Path) -> None:
        tmpl = _load(template_dir)
        for service in tmpl.provides.values():
            assert service["port"] in tmpl.ports

    def test_model_rejects_retired_input(self) -> None:
        with pytest.raises(ValidationError):
            SandboxTemplate.model_validate({"name": "x", "capabilities": ["code"]})


# ---------------------------------------------------------------------------
# (d) Fixture boundary: marked, minimal, never a duplicate collection
# ---------------------------------------------------------------------------


class TestFixtureBoundary:
    """The directory is a *fixture* — marked as such and kept minimal.

    These tests are the guardrail for the single-source-of-truth split: if a
    full template collection ever grows back here (or the fixture notice is
    dropped), the suite fails instead of silently re-diverging from the
    catalog repository.
    """

    def test_only_expected_fixture_templates_exist(self, template_dirs: list[Path]) -> None:
        names = sorted(d.name for d in template_dirs)
        assert names == sorted(EXPECTED_FIXTURE_TEMPLATES), (
            f"examples/templates/ must only contain the offline fixtures "
            f"{sorted(EXPECTED_FIXTURE_TEMPLATES)}, found {names}. Publishable "
            f"templates belong to {SOURCE_OF_TRUTH_URL} instead."
        )

    def test_index_readme_declares_fixture_status(self, catalog_readme: Path) -> None:
        readme = catalog_readme.read_text(encoding="utf-8").lower()
        assert "fixture" in readme, (
            "examples/templates/README.md must state that this directory holds "
            "offline fixtures only"
        )
        assert "publishing source" in readme, (
            "examples/templates/README.md must state that this directory is NOT "
            "the publishing source"
        )

    def test_index_readme_links_the_source_of_truth(self, catalog_readme: Path) -> None:
        readme = catalog_readme.read_text(encoding="utf-8")
        assert SOURCE_OF_TRUTH_URL in readme, (
            f"examples/templates/README.md must point at the single source of truth "
            f"({SOURCE_OF_TRUTH_URL})"
        )

    def test_index_readme_documents_remote_install_flow(self, catalog_readme: Path) -> None:
        readme = catalog_readme.read_text(encoding="utf-8")
        assert "abx template search" in readme
        assert "abx template install" in readme
        assert "ABX_TEMPLATE_INDEX_URL" in readme, (
            "README must document the index override for private mirrors"
        )

    def test_fixture_yaml_carries_a_fixture_banner(self, template_dirs: list[Path]) -> None:
        for folder in template_dirs:
            text = (folder / "template.yaml").read_text(encoding="utf-8")
            assert "FIXTURE" in text, (
                f"{folder.name}/template.yaml must carry an explicit FIXTURE banner "
                f"so it is never mistaken for a publishable template"
            )

    def test_fixture_readme_carries_a_fixture_notice(self, template_dirs: list[Path]) -> None:
        for folder in template_dirs:
            text = (folder / "README.md").read_text(encoding="utf-8")
            assert "fixture" in text.lower(), (
                f"{folder.name}/README.md must carry an explicit fixture notice"
            )
