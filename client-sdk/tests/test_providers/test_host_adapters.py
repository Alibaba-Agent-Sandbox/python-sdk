"""Host-side adapters: wire names pinned by ``epp-methods.json``, per-create options, ports.url."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from agent_sandbox import ProviderSandbox as Sandbox
from agent_sandbox.models import errors as E  # noqa: N812
from agent_sandbox.models.sandbox import SandboxConfig
from agent_sandbox.providers import exec_provider as xp
from agent_sandbox.providers.base import FEATURES
from agent_sandbox.providers.epp import map_error
from agent_sandbox.transport.streaming import StreamReader
from tests.iso import iso  # noqa: F401

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
TABLE = {m["method"]: m for m in json.loads((FIXTURES / "epp-methods.json").read_text())["methods"]}
ALL_FEATURES = frozenset(FEATURES)
EPP = "epp://fake/sbx-1"

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "number": (int, float),
    "null": (type(None),),
}


def _type_ok(value: Any, spec: str) -> bool:
    for alt in spec.split("|"):
        if alt == "integer" and isinstance(value, bool):
            continue
        if isinstance(value, _TYPES[alt]):
            return True
    return False


def check_against_table(method: str, params: dict[str, Any]) -> None:
    entry = TABLE.get(method)
    assert entry is not None, f"adapter calls '{method}', which epp-methods.json does not list"
    spec = entry["params"]
    unknown = set(params) - set(spec)
    assert not unknown, f"{method}: params {sorted(unknown)} are not in the method table"
    for name, rule in spec.items():
        if rule["required"]:
            assert name in params, f"{method}: required param '{name}' is not sent"
        if name in params:
            assert _type_ok(params[name], rule["type"]), (
                f"{method}.{name}={params[name]!r} is not {rule['type']}"
            )


class FakeClient:
    """Stands in for ``EppClient``: records calls and answers with canned results."""

    provider_id = "fake"
    failure = None

    def __init__(self, *, no_connect: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.queues: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}
        self.no_connect = no_connect

    def open_stream(self, process_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        queue.put_nowait({"method": "exec.output", "stream": "stdout", "data": "hi"})
        queue.put_nowait({"method": "exec.exit", "exit_code": 0})
        self.queues[process_id] = queue
        return queue

    def close_stream(self, process_id: str) -> None:
        self.queues.pop(process_id, None)

    async def call(self, method: str, params: dict[str, Any] | None = None, **_kw: Any) -> Any:
        params = dict(params or {})
        self.calls.append((method, params))
        check_against_table(method, params)
        if method == "sandbox.connect" and self.no_connect:
            raise map_error({"code": -32601, "message": "unknown method"}, "fake")
        record = {"sandbox_id": "sbx-1", "template": "base", "status": "running"}
        return {
            "sandbox.create": record,
            "sandbox.get": record,
            "sandbox.connect": record,
            "sandbox.list": {"sandboxes": [record]},
            "exec.run": {"exit_code": 0, "stdout": "x", "stderr": ""},
            "exec.start": {"process_id": "proc-1"},
            "process.list": {"processes": [{"pid": "proc-1", "command": "sleep"}, {"pid": 7}]},
            "files.read": {"content_b64": "", "size": 0},
            "files.list": {"entries": []},
            "files.stat": {"name": "a", "path": "/a", "type": "file", "size": 1},
            "ports.url": {"url": "https://p.example/8080", "headers": {"X-T": "1"}},
        }.get(method, {})


async def _exercise_every_adapter(client: FakeClient, *, stream: bool) -> None:
    feats = ALL_FEATURES if stream else ALL_FEATURES - {"exec.stream"}
    sandbox = xp.ExecSandboxProtocol(client, feats, frozenset({"token"}))  # type: ignore[arg-type]
    await sandbox.create(
        SandboxConfig(
            template="base",
            secure=False,
            provider_options={"mode": "x", "token": "s3cr3t"},
        ),
        request_timeout=5.0,
    )
    await sandbox.connect("sbx-1")
    await sandbox.get_info("sbx-1")
    await sandbox.list(limit=5)
    await sandbox.set_timeout("sbx-1", 60)
    await sandbox.pause("sbx-1")
    await sandbox.resume("sbx-1")
    await sandbox.port_url("sbx-1", 8080)
    await sandbox.kill("sbx-1")

    fs = xp.ExecFilesystemProtocol(client, feats, None)  # type: ignore[arg-type]
    token: Any = None
    await fs.stat(EPP, token, path="/a")
    await fs.list_dir(EPP, token, path="/")
    await fs.make_dir(EPP, token, path="/d")
    await fs.remove(EPP, token, path="/d")
    await fs.move(EPP, token, source="/a", destination="/b")
    await fs.upload_file(EPP, token, path="/a", content=b"x")
    await fs.download_file(EPP, token, path="/a")

    proc = xp.ExecProcessProtocol(client, feats, None)  # type: ignore[arg-type]
    reader = await proc.start(EPP, token, cmd="echo", args=["hi"], timeout=5)
    assert isinstance(reader, StreamReader)
    assert [c async for c in reader]
    await proc.list_processes(EPP, token)
    await proc.send_signal(EPP, token, pid="proc-1", signal=9)
    await proc.send_signal(EPP, token, pid=7, signal=9)
    await proc.send_signal(EPP, token, pid=7, signal=9)
    await proc.send_input(EPP, token, pid="proc-1", data="x")


@pytest.mark.parametrize("stream", [True, False], ids=["exec.stream", "exec.run-only"])
async def test_adapter_params_match_the_method_table(stream):
    client = FakeClient()
    await _exercise_every_adapter(client, stream=stream)
    sent = {m for m, _ in client.calls}
    expected = {
        name
        for name, entry in TABLE.items()
        if entry["host_calls"] and name not in ("initialize", "shutdown")
    }
    if not stream:
        expected -= {"exec.start"}
    else:
        expected -= {"exec.run"}
    assert sent >= expected, sorted(expected - sent)
    assert "files.move" in sent
    move = next(p for m, p in client.calls if m == "files.move")
    assert set(move) == {"sandbox_id", "source", "destination"}


def test_method_table_is_consistent():
    for name, entry in TABLE.items():
        assert entry["support"] in ("required", "optional", "extension"), name
        assert entry["feature"] is None or entry["feature"] in ALL_FEATURES, name
        for rule in entry["params"].values():
            assert set(rule) == {"type", "required"}
    assert TABLE["sandbox.get"]["support"] == "required"
    assert TABLE["sandbox.connect"]["support"] == "optional"
    assert TABLE["process.kill"]["params"]["pid"]["type"] == "string|integer"
    assert TABLE["exec.start"]["result"] == "{process_id: string}"


async def test_create_sends_secure_only_when_specified_and_filters_secret_options():
    client = FakeClient()
    sandbox = xp.ExecSandboxProtocol(client, ALL_FEATURES, frozenset({"token"}))  # type: ignore[arg-type]
    await sandbox.create(SandboxConfig(template="base"))
    params = client.calls[-1][1]
    assert "secure" not in params and "options" not in params
    await sandbox.create(
        SandboxConfig(template="base", secure=False, provider_options={"m": 1, "token": "zzz"})
    )
    params = client.calls[-1][1]
    assert params["secure"] is False
    assert params["options"] == {"m": 1}
    assert "zzz" not in json.dumps(params)
    await sandbox.create(SandboxConfig(template="base", secure=True))
    assert client.calls[-1][1]["secure"] is True


async def test_connect_falls_back_to_get_once_and_remembers():
    client = FakeClient(no_connect=True)
    sandbox = xp.ExecSandboxProtocol(client, ALL_FEATURES)  # type: ignore[arg-type]
    assert (await sandbox.connect("sbx-1")).sandbox_id == "sbx-1"
    assert (await sandbox.connect("sbx-1")).sandbox_id == "sbx-1"
    methods = [m for m, _ in client.calls]
    assert methods == ["sandbox.connect", "sandbox.get", "sandbox.get"]


async def test_connect_does_not_swallow_real_errors():
    class Failing(FakeClient):
        async def call(self, method, params=None, **kw):
            raise map_error({"code": -32002, "message": "nope"}, "fake")

    sandbox = xp.ExecSandboxProtocol(Failing(), ALL_FEATURES)  # type: ignore[arg-type]
    with pytest.raises(E.SandboxNotFoundError) as exc:
        await sandbox.connect("x")
    assert exc.value.code == "E2009"
    assert exc.value.message == "nope"


async def test_sandbox_not_found_is_one_error_for_every_sandbox_call():
    class Gone(FakeClient):
        async def call(self, method, params=None, **kw):
            raise map_error({"code": -32002, "message": "gone"}, "fake")

    sandbox = xp.ExecSandboxProtocol(Gone(), ALL_FEATURES)  # type: ignore[arg-type]
    for call in (
        sandbox.get_info("x"),
        sandbox.set_timeout("x", 5),
        sandbox.pause("x"),
        sandbox.resume("x"),
    ):
        with pytest.raises(E.SandboxNotFoundError):
            await call


def test_plugin_can_name_sandbox_not_found_itself():
    exc = map_error(
        {"code": -32002, "message": "no such sandbox", "data": {"sdk_code": "E2009"}}, "fake"
    )
    assert isinstance(exc, E.SandboxNotFoundError)
    assert exc.code == "E2009"


async def test_port_url_requires_the_feature():
    sandbox = xp.ExecSandboxProtocol(FakeClient(), ALL_FEATURES - {"ports.url"})  # type: ignore[arg-type]
    assert sandbox.has_port_url is False
    with pytest.raises(E.ProviderFeatureNotSupportedError):
        await sandbox.port_url("sbx-1", 80)


async def test_process_info_accepts_string_ids():
    client = FakeClient()
    proc = xp.ExecProcessProtocol(client, ALL_FEATURES, None)  # type: ignore[arg-type]
    infos = await proc.list_processes(EPP, None)  # type: ignore[arg-type]
    assert [i.pid for i in infos] == ["proc-1", 7]


async def test_stream_timeout_is_a_typed_error(monkeypatch):
    class Silent(FakeClient):
        def open_stream(self, process_id):
            queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
            self.queues[process_id] = queue
            return queue

    client = Silent()
    proc = xp.ExecProcessProtocol(client, ALL_FEATURES, None)  # type: ignore[arg-type]
    reader = await proc.start(EPP, None, cmd="sleep", args=["9"], timeout=0)  # type: ignore[arg-type]
    real_wait_for = asyncio.wait_for

    async def fast(awaitable, timeout):
        return await real_wait_for(awaitable, 0.05)

    monkeypatch.setattr(asyncio, "wait_for", fast)
    with pytest.raises(E.CommandTimeoutError):
        async for _ in reader:
            pass


ECHO_PLUGIN = """\
import json, sys

def send(o):
    sys.stdout.write(json.dumps(o) + "\\n"); sys.stdout.flush()

state = {"opts": {}}
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    rid, method, p = msg["id"], msg["method"], msg.get("params") or {}
    if method == "initialize":
        res = {"protocol": "epp/1", "plugin": {"name": "echo", "version": "1"},
               "features": ["sandbox.lifecycle", "ports.url"],
               "operation_contract_version": 1,
               "operations": {'cli': ['sandbox.create',
         'sandbox.get',
         'sandbox.list',
         'sandbox.delete',
         'exec.run',
         'files.read',
         'files.write',
         'files.list',
         'files.stat',
         'files.remove',
         'files.move',
         'ports.resolve'],
 'python': ['sandbox.create',
            'sandbox.get',
            'sandbox.list',
            'sandbox.delete',
            'exec.run',
            'files.read',
            'files.write',
            'files.list',
            'files.stat',
            'files.remove',
            'files.move',
            'ports.resolve']}, "workflow_inputs": ["managed"], "startup_modes": ["exec", "none"]}
    elif method == "sandbox.create":
        state["create"] = p
        res = {"sandbox_id": "echo-1", "template": p.get("template", "base"), "status": "running",
               "metadata": {"create": json.dumps(p, sort_keys=True)}}
    elif method == "sandbox.get":
        res = {"sandbox_id": p["sandbox_id"], "template": "base", "status": "running",
               "metadata": {"via": "get"}}
    elif method == "sandbox.kill":
        res = {}
    elif method == "ports.url":
        res = {"url": "https://echo.example/%s/%s" % (p["sandbox_id"], p["port"]),
               "headers": {"X-Echo": "1"}}
    elif method == "shutdown":
        send({"jsonrpc": "2.0", "id": rid, "result": {}}); break
    else:
        send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown method"}})
        continue
    send({"jsonrpc": "2.0", "id": rid, "result": res})
"""

ECHO_MANIFEST = """\
manifest_version = 1
operation_contract_version = 1
[operations]
cli = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
python = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
[workflow]
inputs = ["managed"]
startups = ["exec", "none"]

[provider]
id = "echo-prov"
name = "Echo"
version = "0.1.0"

[compat]
requires = { sdk = ">=0.3" }

[runtime]
kind = "exec"
command = ["python3", "./provider.py"]

[features]
supported = ["sandbox.lifecycle", "ports.url"]

[config.fields.mode]
type = "string"

[config.fields.token]
type = "string"
secret = true
"""


@pytest.fixture
def echo(iso, tmp_path):  # noqa: F811
    from agent_sandbox.providers import installer

    src = tmp_path / "echo-src"
    src.mkdir()
    (src / "abx-provider.toml").write_text(ECHO_MANIFEST, encoding="utf-8")
    (src / "provider.py").write_text(ECHO_PLUGIN, encoding="utf-8")
    installer.install(str(src), yes=True)
    return iso


async def test_sandbox_create_passes_options_and_secure_to_the_plugin(echo):
    sb = await Sandbox.create(
        provider="echo-prov",
        provider_options={"mode": "fast", "token": "hunter2-secret"},
        secure=False,
    )
    try:
        sent = json.loads(sb._info.metadata["create"])
        assert sent["secure"] is False
        assert sent["options"] == {"mode": "fast"}
        assert "hunter2-secret" not in json.dumps(sent)
    finally:
        await sb.kill()


async def test_sandbox_create_without_secure_sends_no_hint(echo):
    sb = await Sandbox.create(provider="echo-prov")
    try:
        sent = json.loads(sb._info.metadata["create"])
        assert "secure" not in sent and "options" not in sent
    finally:
        await sb.kill()


async def test_network_resolves_through_ports_url(echo):
    sb = await Sandbox.create(provider="echo-prov")
    try:
        url, headers = await sb.network.resolve(8080)
        assert url == f"https://echo.example/{sb.id}/8080"
        assert headers == {"X-Echo": "1"}
        assert await sb.network.resolve_url(3000) == f"https://echo.example/{sb.id}/3000"
        with pytest.raises(E.ProviderFeatureNotSupportedError):
            sb.network.get_url(8080)  # async-only providers have no native URL fallback
    finally:
        await sb.kill()


async def test_connect_uses_get_when_plugin_has_no_connect(echo):
    sb = await Sandbox.create(provider="echo-prov")
    try:
        again = await Sandbox.connect(sb.id, provider="echo-prov")
        assert again._info.metadata["via"] == "get"
        await again.close()
    finally:
        await sb.kill()


async def test_builtin_network_stays_local():

    from tests.network_support import provider_network

    net = provider_network(sandbox_id="sbx-1", domain="example.com", secure=True, access_token="t")
    url, headers = await net.resolve(80)
    assert url == "https://80-sbx-1.example.com"
    assert headers == {"X-Access-Token": "t"}
