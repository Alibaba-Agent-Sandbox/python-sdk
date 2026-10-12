"""Minimal TOML writer for the small, scalar-only documents ``config.toml`` holds."""

from __future__ import annotations

import json
from typing import Any


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def _key(name: str) -> str:
    if name and all(c.isalnum() or c in "-_" for c in name):
        return name
    return json.dumps(name, ensure_ascii=False)


def dumps_toml(doc: dict[str, Any]) -> str:
    """Serialise nested dicts of scalars/lists to TOML (tables sorted after scalars)."""
    lines: list[str] = []

    def emit(table: dict[str, Any], path: list[str]) -> None:
        scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
        tables = {k: v for k, v in table.items() if isinstance(v, dict)}
        if path and (scalars or not tables):
            if lines:
                lines.append("")
            lines.append("[" + ".".join(_key(p) for p in path) + "]")
        for k, v in scalars.items():
            lines.append(f"{_key(k)} = {_scalar(v)}")
        for k, v in tables.items():
            emit(v, [*path, k])

    emit(doc, [])
    return "\n".join(lines) + ("\n" if lines else "")
