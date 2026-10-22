"""Builtin lifecycle keeps its full HTTP contract without a local session daemon."""

from __future__ import annotations

import base64
import json
import struct
import sys

import pytest

from agent_sandbox.api.sandbox import Sandbox


@pytest.mark.parametrize("envd_version", ["0.5.2", "0.6.1"])
async def test_create_preserves_response_and_dials_envd_directly(
    httpx_mock, monkeypatch, tmp_path, envd_version
):
    monkeypatch.setitem(sys.modules, "agent_sandbox.engine", None)
    monkeypatch.setenv("ABX_ENGINE_SOCKET", str(tmp_path / "absent.sock"))
    httpx_mock.add_response(
        method="POST",
        url="https://platform.invalid/sandboxes",
        status_code=201,
        json={
            "sandboxID": "sbx-native-test",
            "templateID": "template-native-test",
            "alias": "native-test",
            "state": "running",
            "timeout": 123,
            "cpuCount": 4,
            "memoryMB": 4096,
            "metadata": {"owner": "native-regression"},
            "envdVersion": envd_version,
            "envdUrl": "https://envd.invalid",
            "envdAccessToken": "placeholder-envd-token",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url="https://envd.invalid/files?path=%2Ftmp%2Fbinary&username=user",
        content=b"\x00\xff",
    )
    events = [
        {"event": {"start": {"pid": 42}}},
        {"event": {"data": {"stdout": base64.b64encode(b"native\n").decode()}}},
        {"event": {"end": {"exitCode": 0}}},
    ]
    frames = b"".join(
        struct.pack(">BI", 0, len(raw)) + raw
        for raw in (json.dumps(event).encode() for event in events)
    )
    httpx_mock.add_response(
        method="POST",
        url="https://envd.invalid/process.Process/Start",
        content=frames,
        headers={"content-type": "application/connect+json"},
    )
    httpx_mock.add_response(
        method="DELETE", url="https://platform.invalid/sandboxes/sbx-native-test", status_code=204
    )
    sandbox = await Sandbox.create(
        "native-test",
        provider="alicloud-express",
        sandbox_api_key="placeholder-platform-key",
        sandbox_base_url="https://platform.invalid",
        timeout=123,
        request_timeout=7,
        cpu=4,
        memory=4096,
        disk=8192,
        gpu="test-gpu",
        metadata={"owner": "native-regression"},
        envs={"NATIVE_TEST": "1"},
    )
    try:
        assert sandbox.info.alias_name == "native-test"
        assert sandbox.info.metadata == {"owner": "native-regression"}
        assert sandbox.info.timeout == 123
        assert sandbox.info.cpu_count == 4
        assert sandbox.info.memory_mb == 4096
        assert await sandbox.files.read_bytes("/tmp/binary", max_bytes=2) == b"\x00\xff"
        result = await sandbox.commands.run("echo native")
        assert result.stdout == "native\n"
        assert result.exit_code == 0
    finally:
        await sandbox.kill()
    create, read, execute, delete = httpx_mock.get_requests()
    assert create.headers["authorization"] == "Bearer placeholder-platform-key"
    assert create.extensions["timeout"]["read"] == 7
    assert json.loads(create.content) == {
        "templateID": "native-test",
        "timeout": 123,
        "autoPause": False,
        "metadata": {"owner": "native-regression"},
        "envVars": {"NATIVE_TEST": "1"},
        "cpuCount": 4,
        "memoryMB": 4096,
        "diskSizeMB": 8192,
        "gpu": "test-gpu",
    }
    assert read.headers["x-access-token"] == "placeholder-envd-token"
    assert read.headers["authorization"] == "Basic dXNlcjo="
    body = execute.content
    if envd_version == "0.6.1":
        assert body[0] == 0
        assert int.from_bytes(body[1:5], "big") == len(body) - 5
        body = body[5:]
    assert json.loads(body)["process"]["cmd"] == "echo"
    assert delete.headers["authorization"] == "Bearer placeholder-platform-key"
