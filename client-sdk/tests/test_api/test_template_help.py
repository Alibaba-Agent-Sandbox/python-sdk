"""Template help imports must work through this package's public namespace."""

import ast
import inspect

import pytest

import agent_sandbox

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
