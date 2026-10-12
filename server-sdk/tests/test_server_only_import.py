"""``easy-sandbox-server`` must work in a container without the client distribution.

A server-only install has no ``easy_sandbox/__init__.py`` (``easy_sandbox`` is an implicit
namespace package without ``__version__``), so server code may import only ``easy_sandbox.server``.
"""

from __future__ import annotations

import ast
from pathlib import Path

SERVER_SRC = Path(__file__).resolve().parents[1] / "src" / "easy_sandbox" / "server"


def _imported_modules(tree: ast.AST) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
            if node.module == "easy_sandbox":
                modules.extend(f"easy_sandbox.{alias.name}" for alias in node.names)
    return modules


def test_server_sources_never_import_the_client_namespace_root() -> None:
    offenders: list[str] = []
    for path in sorted(SERVER_SRC.rglob("*.py")):
        for module in _imported_modules(ast.parse(path.read_text("utf-8"))):
            top = module.split(".")
            if top[0] == "easy_sandbox" and top[:2] != ["easy_sandbox", "server"]:
                offenders.append(f"{path.relative_to(SERVER_SRC)}: {module}")
    assert not offenders, f"server code must not depend on the client distribution: {offenders}"


def test_server_exposes_its_own_version() -> None:
    import easy_sandbox.server as server

    assert server.__version__
