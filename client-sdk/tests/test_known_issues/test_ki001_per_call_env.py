"""KI-001: ``commands.run(cmd, env={...})`` must reach envd as ``process.envs``.

envd's ``ProcessConfig`` message has ``map<string,string> envs = 3``; the SDK used to send
``envVars`` (the *sandbox create* spelling), which protobuf-JSON silently ignores, so per-call
environment variables never reached the command.
"""

from __future__ import annotations

from agent_sandbox.api.commands import CommandsModule
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

START_URL = f"{ENVD}/process.Process/Start"


def _commands() -> CommandsModule:
    return CommandsModule(ENVD, token(), ProcessProtocol(make_http()))


async def test_run_sends_per_call_env_as_envs(httpx_mock) -> None:
    httpx_mock.add_response(
        url=START_URL,
        method="POST",
        content=process_stream(start_event(7), stdout_event("per-call\n"), end_event(0)),
    )
    result = await _commands().run("printenv E2E_CALL_ENV", env={"E2E_CALL_ENV": "per-call"})

    process = body_of(httpx_mock.get_request())["process"]
    assert process["envs"] == {"E2E_CALL_ENV": "per-call"}
    assert "envVars" not in process
    assert result.stdout == "per-call\n"


async def test_start_and_stream_send_env_as_envs(httpx_mock) -> None:
    for _ in range(2):
        httpx_mock.add_response(
            url=START_URL, method="POST", content=process_stream(start_event(8), end_event(0))
        )
    cmds = _commands()
    reader = await cmds.start("env", env={"A": "1"})
    await reader.collect()
    _ = [c async for c in cmds.stream("env", env={"B": "2"})]

    first, second = (body_of(r)["process"] for r in httpx_mock.get_requests())
    assert first["envs"] == {"A": "1"}
    assert second["envs"] == {"B": "2"}


async def test_run_without_env_sends_no_envs_key(httpx_mock) -> None:
    httpx_mock.add_response(
        url=START_URL, method="POST", content=process_stream(start_event(9), end_event(0))
    )
    await _commands().run("true")
    process = body_of(httpx_mock.get_request())["process"]
    assert "envs" not in process
    assert "envVars" not in process
