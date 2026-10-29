"""Tests for declarative/decorator.py — @sandbox 装饰器。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_sandbox.declarative.decorator import (
    _build_execution_script,
    _get_function_source,
    sandbox,
)
from agent_sandbox.models.process import ProcessResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_sandbox(
    *,
    stdout: str = "null",
    stderr: str = "",
    exit_code: int = 0,
) -> AsyncMock:
    """Build a mock Sandbox with commands.run / files.write / kill stubs."""
    mock_sb = AsyncMock()
    mock_sb.commands = AsyncMock()
    mock_sb.commands.run = AsyncMock(
        return_value=ProcessResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            execution_time=0.1,
        ),
    )
    mock_sb.files = AsyncMock()
    mock_sb.files.write = AsyncMock()
    mock_sb.kill = AsyncMock()
    return mock_sb


# ---------------------------------------------------------------------------
# Sync function decoration
# ---------------------------------------------------------------------------


class TestSyncDecoration:
    """@sandbox on synchronous functions."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_basic_call(self, mock_sandbox_cls: MagicMock) -> None:
        """Decorated sync function runs successfully."""
        mock_sb = _make_mock_sandbox(stdout=json.dumps({"result": 42}))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(template="test-tpl", sandbox_api_key="k")
        def my_func(x: int) -> dict[str, Any]:
            return {"result": x}

        result = my_func(42)
        assert result == {"result": 42}

        # Sandbox lifecycle checks
        mock_sandbox_cls.create.assert_awaited_once()
        mock_sb.files.write.assert_awaited_once()
        mock_sb.commands.run.assert_awaited()
        mock_sb.kill.assert_awaited_once()

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_with_kwargs(self, mock_sandbox_cls: MagicMock) -> None:
        """Kwargs are correctly passed through."""
        mock_sb = _make_mock_sandbox(stdout=json.dumps("hello world"))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(sandbox_api_key="k")
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting} {name}"

        result = greet("world", greeting="hello")
        assert result == "hello world"


# ---------------------------------------------------------------------------
# Async function decoration
# ---------------------------------------------------------------------------


class TestAsyncDecoration:
    """@sandbox on async functions."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    async def test_async_call(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(stdout=json.dumps([1, 2, 3]))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(sandbox_api_key="k")
        async def async_fn(data: list[int]) -> list[int]:
            return data

        result = await async_fn([1, 2, 3])
        assert result == [1, 2, 3]
        mock_sb.kill.assert_awaited_once()


@pytest.mark.asyncio
@patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
async def test_sync_decorator_inside_running_loop(mock_sandbox_cls: MagicMock) -> None:
    mock_sb = _make_mock_sandbox(stdout=json.dumps("ok"))
    mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

    @sandbox(sandbox_api_key="placeholder")
    def example() -> str:
        return "ok"

    assert example() == "ok"
    mock_sb.kill.assert_awaited_once()


# ---------------------------------------------------------------------------
# keep_alive mode
# ---------------------------------------------------------------------------


class TestKeepAlive:
    """keep_alive=True prevents sandbox.kill()."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_keep_alive_no_kill(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(stdout=json.dumps(None))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(keep_alive=True, sandbox_api_key="k")
        def noop() -> None:
            return None

        noop()
        mock_sb.kill.assert_not_awaited()
        mock_sb.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# sandbox_id reuse
# ---------------------------------------------------------------------------


class TestSandboxIdReuse:
    """sandbox_id reuses an existing sandbox via connect()."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_connect_instead_of_create(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(stdout=json.dumps("ok"))
        mock_sandbox_cls.connect = AsyncMock(return_value=mock_sb)

        @sandbox(sandbox_id="sbx-existing", sandbox_api_key="k")
        def fn() -> str:
            return "ok"

        result = fn()
        assert result == "ok"
        mock_sandbox_cls.connect.assert_awaited_once()
        # sandbox_id mode: should NOT kill
        mock_sb.kill.assert_not_awaited()
        mock_sb.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Package installation
# ---------------------------------------------------------------------------


class TestPackageInstallation:
    """packages= triggers pip install before execution."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_packages_installed(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(stdout=json.dumps(None))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(packages=["numpy", "pandas"], sandbox_api_key="k")
        def fn() -> None:
            return None

        fn()

        # commands.run calls: python3 --version (detect) + pip install + script exec + rm cleanup
        assert mock_sb.commands.run.await_count >= 3
        all_calls = [str(c) for c in mock_sb.commands.run.await_args_list]
        pip_calls = [c for c in all_calls if "pip install" in c]
        assert len(pip_calls) >= 1, f"Expected pip install call, got: {all_calls}"
        # Must use 'python3 -m pip' (not bare pip)
        assert "-m pip install" in pip_calls[0]
        assert "numpy" in pip_calls[0]
        assert "pandas" in pip_calls[0]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Remote execution failures raise RuntimeError."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_nonzero_exit_code(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(
            stdout="",
            stderr="Traceback: SomeError",
            exit_code=1,
        )
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(sandbox_api_key="k")
        def failing_fn() -> None:
            raise ValueError("boom")

        with pytest.raises(RuntimeError, match="Remote execution failed"):
            failing_fn()

        # Sandbox should still be killed on error
        mock_sb.kill.assert_awaited_once()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestGetFunctionSource:
    """_get_function_source extracts the function body."""

    def test_simple_function(self) -> None:
        def sample(x: int) -> int:
            return x + 1

        source = _get_function_source(sample)
        assert "def sample" in source
        assert "return x + 1" in source

    def test_removes_decorator(self) -> None:
        """Decorator lines should be stripped."""

        # _get_function_source is designed to skip decorator lines
        def plain_func() -> str:
            return "hello"

        source = _get_function_source(plain_func)
        assert source.strip().startswith("def plain_func")


class TestBuildExecutionScript:
    """_build_execution_script produces valid Python."""

    def test_json_script(self) -> None:
        script = _build_execution_script(
            func_name="add",
            func_source="def add(a, b):\n    return a + b\n",
            args_data=json.dumps({"args": [1, 2], "kwargs": {}}),
            serializer_type="json",
        )
        assert "import json" in script
        assert "def add(a, b):" in script
        assert "add(*args, **kwargs)" in script
        assert "json.dumps" in script


# ---------------------------------------------------------------------------
# Import from top-level
# ---------------------------------------------------------------------------


class TestTopLevelImport:
    """sandbox decorator is accessible from agent_sandbox."""

    def test_import_from_declarative(self) -> None:
        from agent_sandbox.declarative import sandbox as sb

        assert callable(sb)

    def test_import_from_top(self) -> None:
        from agent_sandbox import sandbox as sb

        assert callable(sb)


# ---------------------------------------------------------------------------
# Template wiring
# ---------------------------------------------------------------------------


class TestTemplateWiring:
    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_template_is_forwarded(self, mock_sandbox_cls: MagicMock) -> None:
        """The template param is forwarded to Sandbox.create."""
        mock_sb = _make_mock_sandbox(stdout=json.dumps(None))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(template="my-tpl", sandbox_api_key="k")
        def fn() -> None:
            return None

        fn()
        call_kw = mock_sandbox_cls.create.call_args
        effective_tpl = call_kw.args[0] if call_kw.args else call_kw.kwargs.get("template")
        assert effective_tpl == "my-tpl"


# ---------------------------------------------------------------------------
# CPU / Memory pass-through
# ---------------------------------------------------------------------------


class TestCpuMemoryPassThrough:
    """cpu= and memory= are forwarded to Sandbox.create()."""

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_cpu_memory_forwarded(self, mock_sandbox_cls: MagicMock) -> None:
        mock_sb = _make_mock_sandbox(stdout=json.dumps(None))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(cpu=4, memory=2048, sandbox_api_key="k")
        def fn() -> None:
            return None

        fn()

        call_kw = mock_sandbox_cls.create.call_args.kwargs
        assert call_kw["cpu"] == 4
        assert call_kw["memory"] == 2048

    @patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
    def test_cpu_memory_default_none(self, mock_sandbox_cls: MagicMock) -> None:
        """When cpu/memory are not specified, None is passed."""
        mock_sb = _make_mock_sandbox(stdout=json.dumps(None))
        mock_sandbox_cls.create = AsyncMock(return_value=mock_sb)

        @sandbox(sandbox_api_key="k")
        def fn() -> None:
            return None

        fn()

        call_kw = mock_sandbox_cls.create.call_args.kwargs
        assert call_kw["cpu"] is None
        assert call_kw["memory"] is None
