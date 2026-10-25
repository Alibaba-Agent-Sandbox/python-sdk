"""Template help imports must work through this package's public namespace."""

import ast
import inspect
import re
from pathlib import Path

import pytest

import agent_sandbox
import agent_sandbox.code_interpreter as code_interpreter

TEMPLATE_METHODS = (
    "build",
    "build_in_background",
    "get_build_status",
    "exists",
    "alias_exists",
    "assign_tags",
    "remove_tags",
    "get_tags",
)


@pytest.mark.parametrize(
    "entry",
    [
        getattr(template, method)
        for template in (agent_sandbox.Template, agent_sandbox.AsyncTemplate)
        for method in TEMPLATE_METHODS
    ]
    + [
        agent_sandbox.Template().from_python_image().set_start_cmd,
        agent_sandbox.Template().from_python_image().set_ready_cmd,
        agent_sandbox.default_build_logger,
        agent_sandbox.wait_for_port,
        agent_sandbox.wait_for_url,
        agent_sandbox.wait_for_process,
        agent_sandbox.wait_for_file,
        agent_sandbox.wait_for_timeout,
    ],
    ids=lambda entry: entry.__qualname__,
)
def test_template_help_imports_use_public_exports(entry: object) -> None:
    doc = inspect.getdoc(entry) or ""
    imports = [line.strip() for line in doc.splitlines() if line.strip().startswith("from ")]
    assert imports, "The example must include its documented imports"
    for statement in imports:
        node = ast.parse(statement).body[0]
        assert isinstance(node, ast.ImportFrom)
        assert node.module == "agent_sandbox"
        namespace: dict[str, object] = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<help import>", "exec"), namespace)
        for imported in node.names:
            assert namespace[imported.asname or imported.name] is getattr(
                agent_sandbox, imported.name
            )


@pytest.mark.parametrize(
    ("entry", "module"),
    [
        (agent_sandbox.Sandbox, "agent_sandbox"),
        (agent_sandbox.AsyncSandbox, "agent_sandbox"),
        (code_interpreter.Sandbox, "agent_sandbox.code_interpreter"),
        (code_interpreter.AsyncSandbox, "agent_sandbox.code_interpreter"),
    ],
)
def test_sandbox_class_help_imports_resolve_to_the_correct_entry(
    entry: object, module: str
) -> None:
    statements = [
        line.strip()
        for line in (inspect.getdoc(entry) or "").splitlines()
        if line.strip().startswith("from ")
    ]
    assert statements
    for statement in statements:
        node = ast.parse(statement).body[0]
        assert isinstance(node, ast.ImportFrom)
        assert node.module == module
        namespace: dict[str, object] = {}
        exec(statement, namespace)
        assert namespace[node.names[0].name] is entry


def test_all_shipped_python_help_uses_the_owned_namespace() -> None:
    root = Path(__file__).resolve().parents[3]
    upstream_import = re.compile(r"\b(?:from|import)\s+e2b(?:_code_interpreter)?(?=[.\s]|$)")
    for package in ("client-sdk", "server-sdk"):
        source_root = root / package / "src"
        assert source_root.is_dir()
        sources = list(source_root.rglob("*.py"))
        assert sources
        for source in sources:
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ):
                    doc = ast.get_docstring(node) or ""
                    assert not upstream_import.search(doc), source.relative_to(root)
