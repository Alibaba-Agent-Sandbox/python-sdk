"""KI-004: kill / send_signal / send_input / connect / update must address the process correctly.

envd (``process.proto``)::

    SendSignalRequest { ProcessSelector process = 1; Signal signal = 2; }
    SendInputRequest  { ProcessSelector process = 1; ProcessInput input = 2; }
    ConnectRequest    { ProcessSelector process = 1; }
    ProcessSelector   { oneof { uint32 pid = 1; string tag = 2; } }
    Signal            { SIGNAL_SIGTERM = 15; SIGNAL_SIGKILL = 9; }
    ProcessInput      { oneof { bytes stdin = 1; bytes pty = 2; } }   # bytes are base64 in JSON

The SDK used to post a flat ``{"pid": N, ...}`` body, which envd ignores (``process not found``).
"""

from __future__ import annotations

import base64

import pytest

from agent_sandbox.api.commands import CommandsModule
from agent_sandbox.models.errors import EnvdRpcError
from agent_sandbox.providers.shared.e2b.process import ProcessProtocol
from tests.test_known_issues.helpers import (
    ENVD,
    body_of,
    end_event,
    make_http,
    process_stream,
    start_event,
    stdout_event,
    token,
)


def _commands() -> CommandsModule:
    return CommandsModule(ENVD, token(), ProcessProtocol(make_http()))


def _ok(httpx_mock, rpc: str) -> None:  # type: ignore[no-untyped-def]
    httpx_mock.add_response(url=f"{ENVD}/process.Process/{rpc}", method="POST", json={})


async def test_kill_sends_sigkill_with_process_selector(httpx_mock) -> None:
    _ok(httpx_mock, "SendSignal")
    await _commands().kill(42)
    assert body_of(httpx_mock.get_request()) == {
        "process": {"pid": 42},
        "signal": "SIGNAL_SIGKILL",
    }


@pytest.mark.parametrize(("number", "name"), [(15, "SIGNAL_SIGTERM"), (9, "SIGNAL_SIGKILL")])
async def test_send_signal_uses_envd_signal_enum(httpx_mock, number: int, name: str) -> None:
    _ok(httpx_mock, "SendSignal")
    await _commands().send_signal(1234, number)
    assert body_of(httpx_mock.get_request()) == {"process": {"pid": 1234}, "signal": name}


async def test_send_signal_default_is_sigterm(httpx_mock) -> None:
    _ok(httpx_mock, "SendSignal")
    await _commands().send_signal(5)
    assert body_of(httpx_mock.get_request())["signal"] == "SIGNAL_SIGTERM"


@pytest.mark.parametrize("signal", [2, 1, 0, -1, 65, True])
async def test_signals_envd_cannot_deliver_are_rejected_before_any_request(
    httpx_mock, signal: int
) -> None:
    """envd's ``Signal`` enum has only SIGTERM/SIGKILL (its pids are no OS pids: no ``kill``)."""
    with pytest.raises(ValueError, match="SIGTERM.*SIGKILL"):
        await _commands().send_signal(5, signal)
    assert httpx_mock.get_requests() == []


async def test_send_input_wraps_data_as_base64_stdin(httpx_mock) -> None:
    _ok(httpx_mock, "SendInput")
    await _commands().send_input(42, "typed-input\n")
    body = body_of(httpx_mock.get_request())
    assert body["process"] == {"pid": 42}
    assert set(body) == {"process", "input"}
    assert base64.b64decode(body["input"]["stdin"]) == b"typed-input\n"


async def test_send_input_encodes_non_ascii_as_utf8(httpx_mock) -> None:
    _ok(httpx_mock, "SendInput")
    await _commands().send_input(1, "héllo\n")
    stdin = body_of(httpx_mock.get_request())["input"]["stdin"]
    assert base64.b64decode(stdin).decode("utf-8") == "héllo\n"


async def test_numeric_string_pid_is_sent_as_number_and_other_strings_as_tag(httpx_mock) -> None:
    for _ in range(2):
        _ok(httpx_mock, "SendSignal")
    cmds = _commands()
    await cmds.send_signal("77", 9)
    await cmds.send_signal("my-tag", 9)
    first, second = (body_of(r)["process"] for r in httpx_mock.get_requests())
    assert first == {"pid": 77}
    assert second == {"tag": "my-tag"}


async def test_connect_to_process_uses_process_selector(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"{ENVD}/process.Process/Connect",
        method="POST",
        content=process_stream(start_event(42), stdout_event("hi"), end_event(0)),
    )
    reader = await ProcessProtocol(make_http()).connect_to_process(ENVD, token(), pid=42)
    chunks = await reader.collect()
    assert body_of(httpx_mock.get_request()) == {"process": {"pid": 42}}
    assert "hi" in "".join(c.data for c in chunks)


async def test_update_uses_process_selector(httpx_mock) -> None:
    _ok(httpx_mock, "Update")
    await ProcessProtocol(make_http()).update(
        ENVD, token(), pid=42, pty={"size": {"cols": 80, "rows": 24}}
    )
    assert body_of(httpx_mock.get_request()) == {
        "process": {"pid": 42},
        "pty": {"size": {"cols": 80, "rows": 24}},
    }


async def test_process_not_found_surfaces_as_envd_rpc_error(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"{ENVD}/process.Process/SendInput",
        method="POST",
        status_code=404,
        content=b"process not found\n",
    )
    with pytest.raises(EnvdRpcError) as err:
        await _commands().send_input(99999, "x")
    assert err.value.status_code == 404
    assert "process not found" in str(err.value)
    assert ENVD not in str(err.value)
