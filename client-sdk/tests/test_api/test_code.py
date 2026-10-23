"""Interpreter semantic regressions: exact operations and no shell fallback."""

from unittest.mock import AsyncMock

import httpx
import pytest

from agent_sandbox.api.code import CodeContextModule
from agent_sandbox.models.errors import ProviderFeatureNotSupportedError

OPS = {
    "code.execute",
    "code.default-context.execute",
    "code.context.create",
    "code.context.execute",
    "code.context.list",
    "code.context.restart",
    "code.context.delete",
}


@pytest.fixture
def protocol():
    p = AsyncMock()
    p.create_context.return_value = {"contextId": "temporary-context"}
    p.run_code.return_value = {"stdout": "42\n", "stderr": "", "exitCode": 0}
    p.list_contexts.return_value = [{"contextId": "existing"}]
    return p


def module(protocol, operations=OPS):
    return CodeContextModule(
        "sandbox",
        "https://guest",
        AsyncMock(),
        protocol,
        operations=operations,
        provider_id="fixture",
    )


async def test_stateless_uses_exact_operation_without_public_context_requirements(protocol):
    result = await module(protocol, {"code.execute"}).run("print(42)")
    assert result.text == "42" and result.stdout == "42\n" and result.success
    assert protocol.run_code.call_args.kwargs["mode"] == "stateless"
    assert protocol.run_code.call_args.kwargs["context_id"] is None
    protocol.create_context.assert_not_awaited()
    protocol.remove_context.assert_not_awaited()


async def test_execution_failure_is_preserved(protocol):
    protocol.run_code.side_effect = RuntimeError("execution failed")
    with pytest.raises(RuntimeError, match="execution failed"):
        await module(protocol).run("fail")


async def test_explicit_default_context_does_not_create_or_delete(protocol):
    await module(protocol).run("x = 1", mode="default-context")
    assert protocol.run_code.call_args.kwargs["mode"] == "default-context"
    assert protocol.run_code.call_args.kwargs["context_id"] is None
    protocol.create_context.assert_not_awaited()
    protocol.remove_context.assert_not_awaited()


async def test_explicit_context_is_preserved(protocol):
    await module(protocol).run("x", context_id="owned-by-caller")
    assert protocol.run_code.call_args.kwargs["context_id"] == "owned-by-caller"
    protocol.create_context.assert_not_awaited()
    protocol.remove_context.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"context_id": "ctx"},
        {"mode": "default-context"},
        {"on_stdout": lambda s: None},
        {"on_result": lambda r: None},
    ],
)
async def test_stateless_support_does_not_imply_context_or_stream(protocol, kwargs):
    with pytest.raises(ProviderFeatureNotSupportedError):
        await module(protocol, {"code.execute"}).run("must not execute", **kwargs)
    protocol.run_code.assert_not_awaited()
    protocol.create_context.assert_not_awaited()


async def test_404_is_preserved_and_never_shell_falls_back(protocol):
    request = httpx.Request("POST", "https://guest/interpreter")
    response = httpx.Response(404, request=request)
    protocol.run_code.side_effect = httpx.HTTPStatusError(
        "missing runtime", request=request, response=response
    )
    with pytest.raises(httpx.HTTPStatusError):
        await module(protocol).run("payload", context_id="ctx")
    protocol.run_code.assert_awaited_once()
    protocol.create_context.assert_not_awaited()


@pytest.mark.parametrize(
    ("method", "op", "args"),
    [
        ("create_context", "code.context.create", ()),
        ("list_contexts", "code.context.list", ()),
        ("restart_context", "code.context.restart", ("ctx",)),
        ("remove_context", "code.context.delete", ("ctx",)),
    ],
)
async def test_context_operations_are_individually_gated(protocol, method, op, args):
    with pytest.raises(ProviderFeatureNotSupportedError, match=op):
        await getattr(module(protocol, {"code.execute"}), method)(*args)
    await getattr(module(protocol, {op}), method)(*args)
    target = {"remove_context": "remove_context"}.get(method, method)
    getattr(protocol, target).assert_awaited_once()


async def test_invalid_mode_is_rejected_without_network(protocol):
    with pytest.raises(ValueError):
        await module(protocol).run("payload", mode="unknown")
    with pytest.raises(ValueError):
        await module(protocol).run("payload", context_id="ctx", mode="default-context")
    protocol.run_code.assert_not_awaited()


async def test_nested_response_preserves_exit_and_elapsed(protocol):
    protocol.run_code.return_value = {
        "result": {
            "text": "answer",
            "stdout": "a",
            "stderr": "bad",
            "exit_code": 3,
            "execution_time": 1.2,
        }
    }
    result = await module(protocol).run("payload", context_id="ctx")
    assert (result.text, result.exit_code, result.execution_time, result.success) == (
        "answer",
        3,
        1.2,
        False,
    )
