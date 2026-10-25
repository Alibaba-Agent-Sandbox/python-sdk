"""Strict local template discovery. Coarse tokens never authorize provider operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from agent_sandbox.models.errors import TemplateParseError
from agent_sandbox.models.template import SandboxTemplate

TEMPLATE_CACHE_DIR = Path.home() / ".abx" / "templates"


class ResolvedCapabilities(BaseModel):
    """Discovery derived from an explicitly validated template, empty when unknown."""

    capabilities: set[str] = Field(default_factory=set)
    matched: bool = False


def parse_template_data(data: dict[str, Any]) -> SandboxTemplate:
    """Validate specification 5, preserving unrelated application topology metadata."""
    normalized = dict(data)
    resources = normalized.get("resources", {}) or {}
    if "application" not in normalized and "cpu" in resources and "cpu_count" not in normalized:
        normalized["cpu_count"] = resources["cpu"]
    if "application" not in normalized and "memory" in resources and "memory_mb" not in normalized:
        normalized["memory_mb"] = resources["memory"]
    return SandboxTemplate.model_validate(normalized)


def _read(path: Path) -> SandboxTemplate:
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("template must be a mapping")
        return parse_template_data(data)
    except Exception as exc:
        raise TemplateParseError(f"Template at {path} is invalid: {exc}") from exc


async def resolve_capabilities(
    template_id: str | None = None, *, local_yaml_path: str | None = None
) -> ResolvedCapabilities:
    """Discover an explicit path or matching cached manifest without granting defaults."""
    return await resolve_capabilities_for(template_id, local_yaml_path=local_yaml_path)


async def resolve_capabilities_for(
    *template_ids: str | None, local_yaml_path: str | None = None
) -> ResolvedCapabilities:
    """Validate local metadata; an unknown remote reference makes no runtime claims.

    An explicit missing, unreadable or malformed file raises. Cached candidates
    match name, declared source aliases or directory name; matched invalid inputs
    raise instead of silently switching to another definition.
    """
    if local_yaml_path is not None:
        template = _read(Path(local_yaml_path))
        return ResolvedCapabilities(capabilities=template.discovery_capabilities(), matched=True)
    import yaml

    for template_id in dict.fromkeys(t for t in template_ids if t):
        for path in sorted(TEMPLATE_CACHE_DIR.rglob("template.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception:
                if path.parent.name == template_id:
                    _read(path)
                continue
            if not isinstance(data, dict):
                if path.parent.name == template_id:
                    _read(path)
                continue
            aliases = data.get("aliases", [])
            names = [data.get("name"), data.get("alias"), path.parent.name]
            if isinstance(aliases, list):
                names.extend(aliases)
            if template_id in names:
                template = _read(path)
                return ResolvedCapabilities(
                    capabilities=template.discovery_capabilities(), matched=True
                )
    return ResolvedCapabilities()
