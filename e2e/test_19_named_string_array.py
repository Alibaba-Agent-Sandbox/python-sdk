"""Named JSON arrays through the actual uploaded server, Express and native CLI.

The fresh owned sandbox runs this checkout's server source, never a preinstalled
server with an unknown version. Sandbox-factory teardown owns cloud cleanup.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shlex
import subprocess
import zipfile
from pathlib import Path

import e2e_helpers as helpers
import pytest


@pytest.fixture()
def array_server(run, sandbox_factory):  # type: ignore[no-untyped-def]
    sb = sandbox_factory(timeout=600)
    remote = helpers.unique_dir("named-array")
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
@command("array_echo")
def echo(args: list[str]) -> list[str]:
    return args
@command("array_default")
def defaults(args: list[str] = ["seed"]) -> list[str]:
    args.append("new")
    return args
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
        assert next(c for c in commands if c.name == "array_echo").args[0].type == "string_array"
        yield sb, client
    finally:
        run(client.aclose())


def test_cloud_sdk_native_arrays_defaults_and_invalid_payloads(run, array_server):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import CommandArgumentError

    _, client = array_server
    value = ["-i", "literal file.wav", "λ中文", "$(literal-only)"]
    assert run(client.commands.run("array_echo", args=value)) == value
    assert run(client.commands.run("array_echo", args=[])) == []
    for _ in range(2):
        assert run(client.commands.run("array_default")) == ["seed", "new"]
    for invalid in ['["a"]', [1], [True], None, {"a": "b"}]:
        with pytest.raises(CommandArgumentError):
            run(client.commands.run("array_echo", args=invalid))
    with pytest.raises(CommandArgumentError):
        run(client.commands.run("array_echo"))


@pytest.mark.skipif(not os.environ.get("ABX_E2E_CLI"), reason="ABX_E2E_CLI not configured")
def test_cloud_native_cli_json_array(array_server):  # type: ignore[no-untyped-def]
    sb, _ = array_server
    value = ["-i", "literal file.wav", "λ中文", "$(literal-only)"]
    result = subprocess.run(
        [
            os.environ["ABX_E2E_CLI"],
            "--json",
            "run",
            sb.id,
            "array_echo",
            "--json-args",
            json.dumps({"args": value}),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, "native CLI named-array command failed"
    body = json.loads(result.stdout)
    assert body.get("result") == value or body.get("data", {}).get("result") == value
