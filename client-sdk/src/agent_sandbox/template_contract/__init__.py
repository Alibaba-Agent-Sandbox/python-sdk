"""SDK admission for the immutable, template-owner maintained v1 contract.

This module validates literals. Native Devs expressions require the Devs parser;
the Python SDK never substitutes environment values or implements another DSL.
Compiled documents may contain secrets and must remain private in memory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

from .normalize import (
    MAX_YAML_BYTES,
    compile_template_v1,
    normalize_template_v1,
    parse_yaml_v1,
    schema_for_stage,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_SCHEMA = json.loads(Path(__file__).with_name("template-v1.schema.json").read_text())
_VALIDATORS = {
    stage: Draft202012Validator(schema_for_stage(_SCHEMA, stage)).validate
    for stage in ("intent", "resolved")
}


def _read_yaml_document(path: str | Path) -> tuple[bytes, Any]:
    """Read bounded bytes and apply the shared Core1.2 admission before any resource I/O."""
    with Path(path).open("rb") as source:
        raw = source.read(MAX_YAML_BYTES + 1)
    return raw, parse_yaml_v1(raw)


def normalize_document(manifest: dict[str, Any], *, provider: str | None = None) -> dict[str, Any]:
    """Admit public v1 intent without evaluating expressions or resolving secrets."""
    return normalize_template_v1(manifest, _VALIDATORS["intent"], provider=provider)


def compile_literal_document(
    manifest: dict[str, Any],
    *,
    provider: str,
    validate_provider: Callable[[str, Any, str], Any] | None = None,
) -> dict[str, Any]:
    """Compile a literal or Devs-resolved v1 snapshot, rejecting unresolved input."""

    def reject_expressions(value: Any) -> None:
        if isinstance(value, str) and "${" in value:
            raise ValueError(
                "Template v1: unresolved native expressions require the Devs parser; "
                "pass its resolved v1 snapshot or literal values"
            )
        if isinstance(value, dict):
            for key, item in value.items():
                reject_expressions(key)
                reject_expressions(item)
        elif isinstance(value, list):
            for item in value:
                reject_expressions(item)

    reject_expressions(manifest)
    return compile_template_v1(
        manifest, _VALIDATORS["resolved"], provider=provider, validate_provider=validate_provider
    )


__all__ = ["normalize_document", "compile_literal_document"]
