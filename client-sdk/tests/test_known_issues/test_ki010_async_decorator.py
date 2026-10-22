"""KI-010: ``@sandbox`` on an ``async def`` function must await it in the generated remote script.

The script used to call ``func(*args)`` and print ``json.dumps(result, default=str)``: for a
coroutine function that serialised the *coroutine object* (``"<coroutine object double at 0x..>"``).
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from agent_sandbox.declarative.decorator import (
    _build_execution_script,
    _get_function_source,
    sandbox,
)
from agent_sandbox.models.process import ProcessResult


def _run_script(script: str) -> str:
    """Run a generated script the way the sandbox does (a fresh interpreter), return stdout."""
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


async def _double(x: int) -> int:
    return x * 2


async def _greet(name, greeting="hi"):
    import asyncio

    await asyncio.sleep(0)
    return {"msg": f"{greeting} {name}"}


def _script_for(fn: Any, args: list[Any], kwargs: dict[str, Any]) -> str:
    return _build_execution_script(
        func_name=fn.__name__,
        func_source=_get_function_source(fn),
        args_data=json.dumps({"args": args, "kwargs": kwargs}),
        serializer_type="json",
        is_async=True,
    )


def test_async_function_result_is_awaited_in_the_remote_script() -> None:
    assert json.loads(_run_script(_script_for(_double, [21], {}))) == 42


def test_async_function_with_kwargs_and_internal_awaits() -> None:
    out = _run_script(_script_for(_greet, ["bob"], {"greeting": "yo"}))
    assert json.loads(out) == {"msg": "yo bob"}


def test_sync_script_is_unchanged() -> None:
    def triple(x: int) -> int:
        return x * 3

    script = _build_execution_script(
        func_name="triple",
        func_source=_get_function_source(triple),
        args_data=json.dumps({"args": [2], "kwargs": {}}),
        serializer_type="json",
    )
    assert "asyncio" not in script
    assert json.loads(_run_script(script)) == 6


@patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
async def test_decorator_generates_an_awaiting_script_for_async_def(mock_cls: MagicMock) -> None:
    sb = AsyncMock()
    sb.commands.run = AsyncMock(
        return_value=ProcessResult(stdout="42\n", stderr="", exit_code=0, execution_time=0.0)
    )
    mock_cls.create = AsyncMock(return_value=sb)

    @sandbox(sandbox_api_key="k")
    async def double(x: int) -> int:
        return x * 2

    assert await double(21) == 42
    script = sb.files.write.await_args.args[1]
    assert json.loads(_run_script(script)) == 42


@patch("agent_sandbox.api.sandbox.Sandbox", new_callable=lambda: MagicMock)
def test_decorator_keeps_sync_functions_sync(mock_cls: MagicMock) -> None:
    sb = AsyncMock()
    sb.commands.run = AsyncMock(
        return_value=ProcessResult(stdout="6\n", stderr="", exit_code=0, execution_time=0.0)
    )
    mock_cls.create = AsyncMock(return_value=sb)

    @sandbox(sandbox_api_key="k")
    def triple(x: int) -> int:
        return x * 3

    assert triple(2) == 6
    assert "asyncio" not in sb.files.write.await_args.args[1]
