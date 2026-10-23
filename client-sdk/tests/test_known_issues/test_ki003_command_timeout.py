"""KI-003: a command that outlives its timeout raises ``CommandTimeoutError``, not httpx's."""

from __future__ import annotations

import httpx
import pytest

from agent_sandbox.api.commands import CommandsModule
from agent_sandbox.models.errors import CommandTimeoutError, ConnectionError_, ExecutionError
from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
from tests.test_known_issues.helpers import (
    ENVD,
    body_of,
    frame,
    make_http,
    start_event,
    token,
)


def _commands() -> CommandsModule:
    return CommandsModule(
        ENVD, token(), ProcessProtocol(make_http()), operations={"exec.run", "exec.stream"}
    )


class _StallAfterStart(httpx.AsyncByteStream):
    """Streams the start frame, then times out like a command producing no further output."""

    async def __aiter__(self):  # type: ignore[no-untyped-def]
        yield frame(start_event(321))
        raise httpx.ReadTimeout("timed out")


async def test_run_raises_command_timeout_error(httpx_mock) -> None:
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"), url=f"{ENVD}/process.Process/Start")
    with pytest.raises(CommandTimeoutError) as err:
        await _commands().run("sleep 60", timeout=3)
    assert isinstance(err.value, ExecutionError)
    assert "3" in err.value.message
    assert not isinstance(err.value, httpx.HTTPError)


async def test_timeout_after_output_started_is_also_mapped(httpx_mock) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Start"):
            return httpx.Response(200, stream=_StallAfterStart())
        return httpx.Response(200, json={})

    httpx_mock.add_callback(respond, is_reusable=True)
    with pytest.raises(CommandTimeoutError):
        await _commands().run("sleep 60", timeout=3)


async def test_timed_out_process_is_killed_best_effort(httpx_mock) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Start"):
            return httpx.Response(200, stream=_StallAfterStart())
        return httpx.Response(200, json={})

    httpx_mock.add_callback(respond, is_reusable=True)
    with pytest.raises(CommandTimeoutError):
        await _commands().run("sleep 60", timeout=3)

    kills = [r for r in httpx_mock.get_requests() if r.url.path.endswith("/SendSignal")]
    assert [body_of(r) for r in kills] == [{"process": {"pid": 321}, "signal": "SIGNAL_SIGKILL"}]


async def test_kill_failure_never_masks_the_timeout(httpx_mock) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/Start"):
            return httpx.Response(200, stream=_StallAfterStart())
        return httpx.Response(404, content=b"process not found\n")

    httpx_mock.add_callback(respond, is_reusable=True)
    with pytest.raises(CommandTimeoutError):
        await _commands().run("sleep 60", timeout=3)


async def test_stream_and_start_map_timeouts_too(httpx_mock) -> None:
    for _ in range(2):
        httpx_mock.add_exception(httpx.ReadTimeout("t"), url=f"{ENVD}/process.Process/Start")
    cmds = _commands()
    with pytest.raises(CommandTimeoutError):
        async for _chunk in cmds.stream("sleep 60", timeout=2):
            pass
    reader = await cmds.start("sleep 60", timeout=2)
    with pytest.raises(CommandTimeoutError):
        await reader.collect()


async def test_connect_timeout_is_a_connection_error_not_a_command_timeout(httpx_mock) -> None:
    httpx_mock.add_exception(httpx.ConnectTimeout("no route"), url=f"{ENVD}/process.Process/Start")
    with pytest.raises(ConnectionError_):
        await _commands().run("true", timeout=3)
