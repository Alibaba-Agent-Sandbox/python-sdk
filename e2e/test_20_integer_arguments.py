"""Integer JSON argument validation through the actual uploaded server, Express and SDK.

The fresh owned sandbox runs this checkout's server source, never a preinstalled
server with an unknown version. Sandbox-factory teardown owns cloud cleanup.
"""

from __future__ import annotations

import hashlib
import io
import shlex
import zipfile
from pathlib import Path

import e2e_helpers as helpers
import pytest


@pytest.fixture()
def integer_server(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(timeout=600)
    remote = helpers.unique_dir("named-integer")
    source = Path(__file__).resolve().parents[1] / "server-sdk/src/agent_sandbox/server"
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("agent_sandbox/__init__.py", "")
        for path in sorted(source.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json"}:
                archive.write(path, "agent_sandbox/server/" + str(path.relative_to(source)))
    payload = data.getvalue()
    run(sb.files.make_dir(remote))
    run(sb.files.write(remote + "/source.zip", payload))
    expected_sha = hashlib.sha256(payload).hexdigest()
    unpack = (
        "import hashlib,pathlib,zipfile; "
        f"p=pathlib.Path({remote + '/source.zip'!r}); "
        f"assert hashlib.sha256(p.read_bytes()).hexdigest()=={expected_sha!r}; "
        f"zipfile.ZipFile(p).extractall({remote!r})"
    )
    installed = run(sb.commands.run("python3 -c " + shlex.quote(unpack), timeout=30))
    assert installed.exit_code == 0, "owned server source extraction failed"
    code = """from agent_sandbox.server import command, SandboxServer
calls = []
@command("integer_echo")
def echo(seconds: int) -> int:
    calls.append(seconds)
    return seconds
@command("integer_calls")
def count() -> list[int]:
    return calls
@command("boolean_echo")
def boolean_echo(flag: bool) -> bool:
    return flag
SandboxServer(policy={"groups": {"terminal": False}}).serve(9000)
"""
    run(sb.files.write(remote + "/commands.py", code))
    client = run(
        sb.start_server(command="python3 " + shlex.quote(remote + "/commands.py"), timeout=60)
    )
    try:
        commands = helpers.eventually(
            lambda: run(client.commands.list()),
            timeout=45,
            interval=1,
            what="owned command catalogue through the eventually ready port gateway",
        )
        assert next(c for c in commands if c.name == "integer_echo").args[0].type == "integer"
        yield sb, client
    finally:
        run(client.aclose())


def test_cloud_boolean_integer_refusal_before_dispatch(run, integer_server):  # type: ignore[no-untyped-def]
    import httpx

    from agent_sandbox.models.errors import CommandArgumentError

    sb, client = integer_server
    with httpx.Client(base_url=sb.network.get_url(9000), timeout=30) as raw:
        for value in [True, False]:
            response = raw.post("/commands/integer_echo", json={"seconds": value})
            assert response.status_code == 400
            assert response.json()["type"] == "TypeError"
            assert run(client.commands.run("integer_calls")) == []
            with pytest.raises(CommandArgumentError):
                run(client.commands.run("integer_echo", seconds=value))
            assert run(client.commands.run("integer_calls")) == []
        for value in [0, 1, -3, "12"]:
            assert run(client.commands.run("integer_echo", seconds=value)) == int(value)
        assert run(client.commands.run("integer_calls")) == [0, 1, -3, 12]
        for flag in [True, False, "true", "false"]:
            assert run(client.commands.run("boolean_echo", flag=flag)) is (
                str(flag).lower() == "true"
            )
