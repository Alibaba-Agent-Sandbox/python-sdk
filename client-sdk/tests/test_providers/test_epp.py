# ruff: noqa: E501, N812
"""EPP/1 client against the reference plugin and purpose-built misbehaving plugins."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
import time
from typing import TYPE_CHECKING

import pytest

from agent_sandbox.models import errors as E
from agent_sandbox.providers import epp, store
from agent_sandbox.providers.epp import EppClient, exit_code_for, map_error, scrubbed_env

if TYPE_CHECKING:
    from pathlib import Path

INIT = {
    "protocol": "epp/1",
    "host": {"name": "test", "version": "0"},
    "provider_id": "t",
    "config": {},
    "core": {},
    "locale": "en",
}


def _script(tmp_path: Path, body: str) -> list[str]:
    path = tmp_path / "plugin.py"
    path.write_text(
        "import json, sys\n"
        "def send(o):\n"
        "    sys.stdout.write(json.dumps(o) + '\\n'); sys.stdout.flush()\n" + textwrap.dedent(body),
        encoding="utf-8",
    )
    return [sys.executable, str(path)]


def _client(tmp_path, body, **kw) -> EppClient:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    return EppClient(
        "t",
        _script(tmp_path, body),
        cwd=data,
        env=scrubbed_env(data),
        startup_timeout=kw.pop("startup_timeout", 3.0),
        call_timeout=kw.pop("call_timeout", 3.0),
        **kw,
    )


LOOP = """
for line in sys.stdin:
    msg = json.loads(line)
    m = msg.get("method")
    if m == "initialize":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocol": "epp/1", "features": ["sandbox.lifecycle"]}})
    elif m == "shutdown":
        send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        break
    else:
        handle(msg)
"""


def serve(handler_body: str) -> str:
    """A plugin whose ``handle(msg)`` is *handler_body* (indented one level, ``msg`` in scope)."""
    body = textwrap.indent(textwrap.dedent(handler_body).strip("\n"), "    ")
    return "def handle(msg):\n" + body + "\n" + LOOP


@pytest.mark.asyncio
async def test_handshake_and_ping(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        send({"jsonrpc": "2.0", "id": msg["id"], "result": msg["params"]})
    """),
    )
    result = await client.start(INIT)
    try:
        assert result["protocol"] == "epp/1"
        assert client.features == frozenset({"sandbox.lifecycle"})
        assert await client.call("echo", {"a": 1}) == {"a": 1}
        results = await asyncio.gather(*(client.call("echo", {"n": i}) for i in range(20)))
        assert [r["n"] for r in results] == list(range(20))
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_protocol_mismatch_is_version_error(tmp_path):
    client = _client(
        tmp_path,
        """
        for line in sys.stdin:
            msg = json.loads(line)
            send({"jsonrpc": "2.0", "id": msg["id"], "result": {"protocol": "epp/9"}})
    """,
    )
    with pytest.raises(E.ProviderVersionError) as exc:
        await client.start(INIT)
    assert exc.value.code == "E8013"


@pytest.mark.asyncio
async def test_startup_timeout(tmp_path):
    client = _client(tmp_path, "import time\ntime.sleep(30)\n", startup_timeout=0.5)
    t0 = time.monotonic()
    with pytest.raises(E.ProviderTimeoutError) as exc:
        await client.start(INIT)
    assert exc.value.code == "E8022" and time.monotonic() - t0 < 10


@pytest.mark.asyncio
async def test_call_timeout(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        import time; time.sleep(30)
    """),
        call_timeout=0.4,
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderTimeoutError):
            await client.call("slow", {})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_missing_executable(tmp_path):
    client = EppClient("t", [str(tmp_path / "nope")], cwd=tmp_path, env=scrubbed_env(tmp_path))
    with pytest.raises(E.ProviderProcessError) as exc:
        await client.start(INIT)
    assert exc.value.code == "E8021"


@pytest.mark.asyncio
async def test_plugin_exits_during_startup_includes_stderr(tmp_path):
    client = _client(tmp_path, "sys.stderr.write('boom: missing dependency\\n')\nsys.exit(4)\n")
    with pytest.raises(E.ProviderProcessError) as exc:
        await client.start(INIT)
    assert "missing dependency" in str(exc.value)


@pytest.mark.asyncio
async def test_crash_mid_session_fails_pending_and_future_calls(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        sys.stderr.write("fatal: oops\\n"); sys.stderr.flush()
        import os; os._exit(3)
    """),
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderProcessError) as exc:
            await client.call("die", {})
        assert "oops" in str(exc.value)
        with pytest.raises(E.ProviderProcessError):
            await client.call("echo", {})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_garbage_line_is_protocol_error(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        sys.stdout.write("this is not json\\n"); sys.stdout.flush()
    """),
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderProtocolError) as exc:
            await client.call("bad", {})
        assert exc.value.code == "E8020"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_oversized_line_is_protocol_error(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        sys.stdout.write("x" * (9 * 1024 * 1024) + "\\n"); sys.stdout.flush()
    """),
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderProtocolError):
            await client.call("big", {})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_error_response_is_mapped(tmp_path):
    client = _client(
        tmp_path,
        serve("""
        send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32002, "message": "gone", "data": {"sdk_code": "E2000"}}})
    """),
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderResourceNotFoundError):
            await client.call("nf", {})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_secret_values_are_redacted_everywhere(tmp_path):
    secret = "s3cr3t-token-value"
    client = _client(
        tmp_path,
        serve(f"""
        sys.stderr.write("token=" + {secret!r} + "\\n"); sys.stderr.flush()
        send({{"jsonrpc": "2.0", "id": msg["id"], "error": {{"code": -32000, "message": "bad " + {secret!r}}}}})
    """),
        secrets=[secret],
    )
    await client.start(INIT)
    try:
        with pytest.raises(E.ProviderError) as exc:
            await client.call("leak", {})
        await asyncio.sleep(0.2)
        assert secret not in str(exc.value)
        assert secret not in client.stderr_tail
        assert "***" in client.stderr_tail
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_close_terminates_process_group(tmp_path):
    pidfile = tmp_path / "child.pid"
    client = _client(
        tmp_path,
        serve(f"""
        import subprocess
        child = subprocess.Popen(["sleep", "60"])
        open({str(pidfile)!r}, "w").write(str(child.pid))
        send({{"jsonrpc": "2.0", "id": msg["id"], "result": {{}}}})
    """),
    )
    await client.start(INIT)
    await client.call("spawn", {})
    child = int(pidfile.read_text())
    await client.close()
    await asyncio.sleep(0.3)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


class TestScrubbedEnv:
    def test_only_allowlist_and_data_dir(self, tmp_path):
        env = scrubbed_env(
            tmp_path,
            ["MY_PASS"],
            environ={
                "PATH": "/bin",
                "HOME": "/h",
                "LC_ALL": "C",
                "ABX_SANDBOX_API_KEY": "secret",
                "E2B_API_KEY": "secret",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "MY_PASS": "yes",
                "RANDOM": "x",
            },
        )
        assert set(env) == {
            "PATH",
            "HOME",
            "LC_ALL",
            "MY_PASS",
            "ABX_PROVIDER_DATA_DIR",
            "PYTHONDONTWRITEBYTECODE",
        }
        assert env["ABX_PROVIDER_DATA_DIR"] == str(tmp_path)

    def test_resolve_command_confines_dot_slash(self, tmp_path):
        (tmp_path / "p.py").write_text("")
        argv = epp.resolve_command(["python3", "./p.py", "plain"], tmp_path)
        assert argv == ["python3", str((tmp_path / "p.py").resolve()), "plain"]
        with pytest.raises(E.ProviderManifestError):
            epp.resolve_command(["./../x"], tmp_path / "sub")


class TestMapError:
    @pytest.mark.parametrize(
        ("code", "data", "cls", "exit_code"),
        [
            (-32001, {}, E.AuthenticationError, 3),
            (-32001, {"sdk_code": "E1001"}, E.InvalidAPIKeyError, 3),
            (-32002, {}, E.ProviderResourceNotFoundError, 4),
            (-32002, {"sdk_code": "E2000"}, E.ProviderResourceNotFoundError, 4),
            (-32002, {"sdk_code": "E2001"}, E.TemplateNotFoundError, 4),
            (-32002, {"sdk_code": "E4001"}, E.FileNotFoundError_, 4),
            (-32003, {"details": {"feature": "pty"}}, E.ProviderFeatureNotSupportedError, 1),
            (-32004, {}, E.QuotaExceededError, 6),
            (-32005, {}, E.ProviderTimeoutError, 5),
            (-32006, {}, E.ProviderConfigError, 2),
            (-32000, {}, E.ProviderError, 1),
            (-32000, {"sdk_code": "E4001"}, E.FileNotFoundError_, 4),
            (-32000, {"sdk_code": "E3001"}, E.CommandTimeoutError, 5),
            (-32601, {}, E.ProviderProtocolError, 1),
            (123, {}, E.ProviderProtocolError, 1),
        ],
    )
    def test_codes(self, code, data, cls, exit_code):
        exc = map_error({"code": code, "message": "m", "data": data}, "prov")
        assert type(exc) is cls
        assert exit_code_for(exc) == exit_code

    def test_feature_error_is_both_provider_and_capability_error(self):
        exc = map_error(
            {"code": -32003, "message": "no", "data": {"details": {"feature": "pty"}}}, "p"
        )
        assert isinstance(exc, E.ProviderError) and isinstance(exc, E.CapabilityNotSupportedError)
        assert exc.code == "E8004"

    def test_text_is_sanitised(self):
        exc = map_error(
            {"code": -32000, "message": "\x1b[31mred\x1b[0m\x00 tok-12345", "data": {}},
            "p",
            secrets=["tok-12345"],
        )
        assert "\x1b" not in exc.message and "\x00" not in exc.message
        assert "tok-12345" not in exc.message

    def test_exit_code_for_other_errors(self):
        assert exit_code_for(E.ProviderNotFoundError("x")) == 4
        assert exit_code_for(E.ProviderTrustError("x")) == 2
        assert exit_code_for(E.ProviderMismatchError("x")) == 2
        assert exit_code_for(E.ProviderIntegrityError("x")) == 1
        assert exit_code_for(ValueError("x")) == 1


@pytest.mark.asyncio
async def test_reference_plugin_env_is_scrubbed_and_config_arrives_via_initialize(
    local_process, monkeypatch
):
    from agent_sandbox.providers import registry
    from agent_sandbox.transport.config import load_config

    monkeypatch.setenv("ABX_SANDBOX_API_KEY", "parent-secret-1")
    monkeypatch.setenv("E2B_API_KEY", "parent-secret-2")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "parent-secret-3")
    provider = registry.get_provider("local-process")
    cfg = load_config(
        provider="local-process", provider_options={"debug": True, "token": "tok-abcdefgh"}
    )
    infra = await provider.build_infra(cfg)
    try:
        res = await infra.sandbox_protocol._c.call("debug.env", {})
        blob = json.dumps(res)
        assert "parent-secret" not in blob and "tok-abcdefgh" not in blob
        assert res["env"]["ABX_PROVIDER_DATA_DIR"] == str(store.data_dir("local-process"))
        assert res["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
        assert not any(k.startswith(("ABX_SANDBOX", "E2B_", "AWS_")) for k in res["env"])
        assert set(res["config_keys"]) == {"debug", "token"}
        await infra.sandbox_protocol._c.call("debug.leak", {})
        await asyncio.sleep(0.2)
        assert "tok-abcdefgh" not in infra.sandbox_protocol._c.stderr_tail
    finally:
        await infra.close()
