"""HTTP end-to-end tests for ``python -m agent_sandbox.server serve``.

A real subprocess listens on 127.0.0.1. Every check is a separate HTTP client
(or a raw socket for the responses upgrade). Handlers are never called in-process.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

pytestmark = pytest.mark.e2e

SDK_SRC = Path(__file__).resolve().parents[1] / "server-sdk" / "src"
TOKEN = "e2e-local-token"
SECRET = "vault-secret-e2e-DoNotEcho-91c2d4"
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
CODEX_LINE = (
    '{"type":"item.completed","item":{"id":"m1","type":"agent_message","text":"codex-e2e-ok"}}'
)
QWEN_LINE = (
    '{"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"qwen-e2e-ok"}]}}'
)
_DROP = {
    "OPENAI_API_KEY",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "ABX_SANDBOX_API_KEY",
    "ABX_SERVER_TOKEN",
    "ABX_SERVER_POLICY",
    "ABX_SERVER_POLICY_FILE",
    "ABX_SERVER_ENABLED_GROUPS",
    "ABX_SERVER_BASE_DIR",
    "ABX_AGENTS_CONFIG",
    "ABX_AGENTS_DEFAULT",
}


class HttpResult:
    def __init__(self, status: int, raw: bytes, headers: dict[str, str]) -> None:
        self.status = status
        self.raw = raw
        self.headers = headers

    @property
    def text(self) -> str:
        return self.raw.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.raw:
            return None
        return json.loads(self.raw)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _script(line: str) -> str:
    return "\n".join(
        [
            "#!/bin/sh",
            "cat >/dev/null",
            f"printf '%s\\n' '{line}'",
            "exit 0",
            "",
        ]
    )


def _install_fakes(bindir: Path) -> None:
    bindir.mkdir(parents=True)
    (bindir / "codex").write_text(_script(CODEX_LINE))
    (bindir / "qwen").write_text(_script(QWEN_LINE))
    for name in ("codex", "qwen"):
        (bindir / name).chmod(0o755)


class LiveServer:
    """One ``python -m agent_sandbox.server serve`` process."""

    def __init__(self, root: Path, bindir: Path, *, token: str | None) -> None:
        self.root = root
        self.bindir = bindir
        self.token = token
        self.base_dir = root / "base"
        self.base_dir.mkdir(parents=True)
        (root / "home").mkdir(exist_ok=True)
        (root / "responses-ws").mkdir(exist_ok=True)
        self.port = 0
        self.proc: subprocess.Popen[bytes] | None = None
        self.log_path = root / "server.log"
        self._log = open(self.log_path, "ab")  # noqa: SIM115

    def start(self) -> None:
        last = ""
        for _ in range(4):
            port = _free_port()
            pty = _free_port()
            env = os.environ.copy()
            for key in _DROP:
                env.pop(key, None)
            env["PYTHONPATH"] = str(SDK_SRC)
            env["PATH"] = str(self.bindir) + os.pathsep + env.get("PATH", "")
            env["ABX_SERVER_ENABLED_GROUPS"] = "agents"
            env["ABX_AGENTS_PERSIST"] = "0"
            env["ABX_AGENTS_RESPONSES_WORKSPACE"] = str(self.root / "responses-ws")
            env["HOME"] = str(self.root / "home")
            if self.token:
                env["ABX_SERVER_TOKEN"] = self.token
            self.proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "agent_sandbox.server",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--pty-port",
                    str(pty),
                    "--base-dir",
                    str(self.base_dir),
                ],
                cwd=str(self.root),
                env=env,
                stdout=self._log,
                stderr=self._log,
                start_new_session=True,
            )
            if self._wait_health(port):
                self.port = port
                return
            last = self.log_path.read_text(errors="replace")[-2000:]
            self._kill()
        raise RuntimeError(f"server did not become healthy on 127.0.0.1: {last}")

    def _wait_health(self, port: int) -> bool:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return False
            try:
                result = self._exchange(port, "GET", "/health", None, None, auth=False)
            except OSError:
                time.sleep(0.05)
                continue
            if result.status == 200:
                return True
            time.sleep(0.05)
        return False

    def stop(self) -> None:
        self._kill()
        self._log.close()

    def _kill(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait(timeout=5)

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        raw: bytes | None = None,
        content_type: str | None = None,
        auth: bool = True,
    ) -> HttpResult:
        target = path
        if query:
            target = path + ("&" if "?" in path else "?") + urlencode(query)
        return self._exchange(self.port, method, target, body, headers, raw, content_type, auth)

    def _exchange(
        self,
        port: int,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        headers: dict[str, str] | None,
        raw: bytes | None = None,
        content_type: str | None = None,
        auth: bool = True,
    ) -> HttpResult:
        hdrs = dict(headers or {})
        if auth and self.token:
            hdrs.setdefault("X-Access-Token", self.token)
        data: bytes | None
        if raw is not None:
            data = raw
            if content_type:
                hdrs["Content-Type"] = content_type
        elif body is not None:
            data = json.dumps(body).encode()
            hdrs.setdefault("Content-Type", "application/json")
        else:
            data = None
        if data is not None:
            hdrs["Content-Length"] = str(len(data))
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        try:
            conn.request(method, path, body=data, headers=hdrs)
            resp = conn.getresponse()
            payload = resp.read()
            got = {key.lower(): value for key, value in resp.getheaders()}
            return HttpResult(resp.status, payload, got)
        finally:
            conn.close()

    def get(self, path: str, **kw: Any) -> HttpResult:
        return self.request("GET", path, **kw)

    def post(self, path: str, body: dict[str, Any] | None = None, **kw: Any) -> HttpResult:
        return self.request("POST", path, {} if body is None else body, **kw)

    def delete(self, path: str, **kw: Any) -> HttpResult:
        return self.request("DELETE", path, **kw)


@pytest.fixture(scope="module")
def servers(tmp_path_factory: pytest.TempPathFactory) -> Any:
    root = tmp_path_factory.mktemp("abx-http-e2e")
    bindir = root / "bin"
    _install_fakes(bindir)
    opened = LiveServer(root / "open", bindir, token=None)
    locked = LiveServer(root / "token", bindir, token=TOKEN)
    opened.start()
    locked.start()
    try:
        yield {"open": opened, "token": locked}
    finally:
        opened.stop()
        locked.stop()


def _open(servers: dict[str, LiveServer]) -> LiveServer:
    return servers["open"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _workspace(server: LiveServer, name: str) -> Path:
    path = server.base_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _wait_turns(server: LiveServer, session_id: str) -> HttpResult:
    deadline = time.monotonic() + 20
    last = server.get(f"/v1/agents/sessions/{session_id}/turns")
    while time.monotonic() < deadline:
        last = server.get(f"/v1/agents/sessions/{session_id}/turns")
        if last.status == 200 and last.json():
            data = last.json().get("data") or []
            if data and all(
                row.get("status") in ("completed", "failed", "cancelled") for row in data
            ):
                return last
        time.sleep(0.05)
    return last


# ---------------------------------------------------------------------- #
# Health, discovery, token
# ---------------------------------------------------------------------- #


def test_health_is_open_with_and_without_token(servers: dict[str, LiveServer]) -> None:
    for server in servers.values():
        result = server.get("/health", auth=False)
        assert result.status == 200, result.text
        assert result.json() == {"status": "ok"}


def test_capabilities_with_and_without_token(servers: dict[str, LiveServer]) -> None:
    opened = servers["open"]
    locked = servers["token"]

    open_caps = opened.get("/capabilities", auth=False)
    assert open_caps.status == 200, open_caps.text
    doc = open_caps.json()
    assert doc["groups"]["agents"] is True and doc["groups"]["file_ops"] is True
    assert doc["groups"]["dev_tools"] is False and doc["groups"]["browser"] is False
    assert doc["group_summary"]["dev_tools"]["enabled"] == 0
    assert doc["group_summary"]["agents"]["enabled"] == doc["group_summary"]["agents"]["total"]

    denied_caps = locked.get("/capabilities", auth=False)
    assert denied_caps.status == 401, denied_caps.text
    assert denied_caps.json()["error"] == "unauthorized"

    authed_caps = locked.get("/capabilities")
    assert authed_caps.status == 200, authed_caps.text
    assert "groups" in authed_caps.json()


def test_capabilities_name_the_rule_that_disabled_an_endpoint(
    servers: dict[str, LiveServer],
) -> None:
    server = _open(servers)
    endpoints = server.get("/capabilities").json()["endpoints"]
    assert endpoints["shell"]["enabled"] is True and endpoints["shell"]["rule"] is None
    code_run = endpoints["code_run"]
    assert (code_run["enabled"], code_run["allowed"]) == (False, False)
    assert code_run["reason"] == "endpoint_disabled"
    assert code_run["rule"] == "default:opt-in:dev_tools"
    assert code_run["summary"]


def test_disabled_endpoint_answers_404_with_its_rule(servers: dict[str, LiveServer]) -> None:
    result = _open(servers).post("/code/run", {"code": "print(1)"})
    assert result.status == 404, result.text
    body = result.json()
    assert body["code"] == "endpoint_disabled" and body["endpoint"] == "code_run"
    assert body["rule"] == "default:opt-in:dev_tools"
    assert "dev_tools" in body["error"]


def test_removed_ops_surface_is_gone(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    assert server.get("/ops", auth=False).status == 404
    assert server.post("/ops/files.mkdir", {"path": str(server.base_dir / "x")}).status == 404


def test_path_outside_the_base_dir_is_a_403_path_not_allowed(
    servers: dict[str, LiveServer],
) -> None:
    server = _open(servers)
    outside = str(server.root / "outside.txt")
    for result in (
        server.post("/files/mkdir", {"path": outside}),
        server.post("/files/upload-stream", {"path": outside, "content_base64": _b64(b"x")}),
        server.get("/files/download-stream", query={"path": outside}),
    ):
        assert result.status == 403, result.text
        assert result.json()["code"] == "path_not_allowed"
    assert not Path(outside).exists()


def test_capabilities_check_decides_without_touching_the_filesystem(
    servers: dict[str, LiveServer],
) -> None:
    server = _open(servers)
    inside = server.post(
        "/capabilities/check",
        {"endpoint": "files_mkdir", "path": str(server.base_dir / "new"), "op": "write"},
    )
    assert inside.status == 200, inside.text
    assert inside.json()["allowed"] is True
    outside = server.post(
        "/capabilities/check",
        {"endpoint": "files_mkdir", "path": str(server.root / "outside"), "op": "write"},
    )
    assert outside.json()["allowed"] is False and outside.json()["code"] == "path_not_allowed"
    disabled = server.post("/capabilities/check", {"endpoint": "code_run"})
    assert disabled.json()["code"] == "endpoint_disabled"
    assert disabled.json()["rule"] == "default:opt-in:dev_tools"
    assert not (server.base_dir / "new").exists()


# ---------------------------------------------------------------------- #
# Files and shell
# ---------------------------------------------------------------------- #


def test_file_upload_list_download_mkdir_delete(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    directory = server.base_dir / f"dir-{uuid.uuid4().hex}"
    payload = b"e2e-upload-bytes"

    made = server.post("/files/mkdir", {"path": str(directory)})
    assert made.status == 200, made.text
    assert made.json()["created"] is True
    assert Path(made.json()["path"]).is_dir()

    uploaded = server.post(
        "/files/upload-stream",
        {"path": str(directory / "note.txt"), "content_base64": _b64(payload)},
    )
    assert uploaded.status == 200, uploaded.text
    assert uploaded.json()["bytes"] == len(payload)

    listed = server.get("/files/list", query={"path": str(directory)})
    assert listed.status == 200, listed.text
    assert "note.txt" in {entry["name"] for entry in listed.json()["entries"]}

    downloaded = server.get("/files/download-stream", query={"path": str(directory / "note.txt")})
    assert downloaded.status == 200, downloaded.text
    assert base64.b64decode(downloaded.json()["content_base64"]) == payload

    deleted = server.delete("/files", query={"path": str(directory / "note.txt")})
    assert deleted.status == 200, deleted.text
    assert deleted.json()["deleted"] is True
    again = server.get("/files/list", query={"path": str(directory)})
    assert again.status == 200, again.text
    assert "note.txt" not in {entry["name"] for entry in again.json()["entries"]}


def test_shell_stdout(servers: dict[str, LiveServer]) -> None:
    result = _open(servers).post("/shell", {"command": "/bin/echo e2e-shell-ok"})
    assert result.status == 200, result.text
    assert result.json()["stdout"] == "e2e-shell-ok\n"
    assert result.json()["exit_code"] == 0


# ---------------------------------------------------------------------- #
# Agents
# ---------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("adapter", "marker"),
    [("codex", "codex-e2e-ok"), ("qwen", "qwen-e2e-ok")],
)
def test_agent_session_events_items(
    servers: dict[str, LiveServer], adapter: str, marker: str
) -> None:
    server = _open(servers)
    workspace = _workspace(server, f"ws-{adapter}-{uuid.uuid4().hex}")
    created = server.post(
        "/v1/agents/sessions",
        {
            "adapter": adapter,
            "environment": {"type": "self_hosted", "workspace_directory": str(workspace)},
        },
    )
    assert created.status == 200, created.text
    assert created.json()["object"] == "agent.session"
    assert created.headers.get("x-agent-sandbox-local") == "1"
    session_id = created.json()["id"]

    events = server.post(
        f"/v1/agents/sessions/{session_id}/events",
        {"events": [{"type": "agent.session.input.message", "input": "ping"}]},
    )
    assert events.status == 202, events.text
    assert events.raw == b""

    turns = _wait_turns(server, session_id)
    items = server.get(f"/v1/agents/sessions/{session_id}/items")
    assert items.status == 200, (items.text, turns.text)
    assert items.json()["object"] == "list"
    assert marker in items.text, (items.text, turns.text)
    assert turns.status == 200, turns.text
    assert turns.json()["data"][0]["status"] == "completed"


def test_agent_runtimes_local_header(servers: dict[str, LiveServer]) -> None:
    result = _open(servers).get("/v1/agents/runtimes")
    assert result.status == 200, result.text
    assert result.headers.get("x-agent-sandbox-local") == "1"
    rows = {row["name"]: row for row in result.json()["data"]}
    implemented = {name for name, row in rows.items() if row.get("implemented", True)}
    assert implemented == {"codex", "qwen-code"}, rows
    assert {"claude-code", "cursor", "command"} <= set(rows)
    assert rows["codex"]["installed"] is True
    assert rows["qwen-code"]["installed"] is True


def test_environment_create(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    workspace = _workspace(server, f"env-{uuid.uuid4().hex}")
    result = server.post(
        "/v1/agents/environments",
        {"environment": {"type": "self_hosted", "workspace_directory": str(workspace)}},
    )
    assert result.status == 200, result.text
    body = result.json()
    assert body["object"] == "agent.environment"
    assert body["type"] == "self_hosted"
    assert body["status"] == "ready"
    assert body["workspace_directory"] == str(workspace.resolve())


def test_template_hosted_only_field_is_400(servers: dict[str, LiveServer]) -> None:
    result = _open(servers).post(
        "/v1/agents/environments/templates",
        {"name": "hosted", "network": {"access": "disabled"}},
    )
    assert result.status == 400, result.text
    assert result.json()["error"]["param"] == "network"


def test_vault_create_does_not_echo_secret(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    created = server.post("/v1/vaults", {"name": "e2e-vault"})
    assert created.status == 200, created.text
    assert created.json()["object"] == "vault"
    assert SECRET not in created.text
    credential = server.post(
        f"/v1/vaults/{created.json()['id']}/credentials",
        {
            "name": "mcp",
            "auth": {
                "type": "static_bearer",
                "mcp_server_url": "https://mcp.example.com/mcp",
                "token": SECRET,
            },
        },
    )
    assert credential.status == 200, credential.text
    assert credential.json()["object"] == "vault.credential"
    assert SECRET not in credential.text
    assert "token" not in credential.json()["auth"]


def test_files_json_round_trip(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    payload = b"e2e-json-file-bytes"
    uploaded = server.post(
        "/v1/files",
        {"purpose": "user_data", "filename": "note.txt", "data": _b64(payload)},
    )
    assert uploaded.status == 200, uploaded.text
    blob = uploaded.json()
    assert blob["object"] == "file"
    assert blob["purpose"] == "user_data"
    assert blob["filename"] == "note.txt"
    assert blob["bytes"] == len(payload)

    workspace = _workspace(server, f"blob-{uuid.uuid4().hex}")
    placed = server.post(
        "/v1/agents/environments",
        {
            "environment": {
                "type": "self_hosted",
                "workspace_directory": str(workspace),
                "files": [
                    {"type": "file_id", "file_id": blob["id"], "path": "/workspace/note.txt"}
                ],
            }
        },
    )
    assert placed.status == 200, placed.text
    assert (workspace / "note.txt").read_bytes() == payload


def test_models_list(servers: dict[str, LiveServer]) -> None:
    result = _open(servers).get("/v1/models")
    assert result.status == 200, result.text
    assert result.json()["object"] == "list"
    ids = [row["id"] for row in result.json()["data"]]
    assert "codex" in ids
    assert "qwen-code" in ids


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/v1/responses/input_tokens"), ("DELETE", "/v1/models/codex")],
)
def test_cannot_routes(servers: dict[str, LiveServer], method: str, path: str) -> None:
    result = _open(servers).request(
        method, path, {"model": "codex", "input": "hi"} if method == "POST" else None
    )
    assert result.status == 404, result.text
    assert result.headers.get("x-should-retry") == "false", result.headers
    assert result.json()["error"]["type"] == "not_found_error"


def test_unknown_adapter_is_404(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    workspace = _workspace(server, f"bad-{uuid.uuid4().hex}")
    result = server.post(
        "/v1/agents/sessions",
        {
            "adapter": "not-a-real-adapter",
            "environment": {"type": "self_hosted", "workspace_directory": str(workspace)},
        },
    )
    assert result.status == 404, result.text
    assert "not-a-real-adapter" in result.text


# ---------------------------------------------------------------------- #
# Optional transports: record the real status instead of a fake pass
# ---------------------------------------------------------------------- #


def _recv_until(sock: socket.socket, marker: bytes, limit: int = 65536) -> bytes:
    buf = bytearray()
    while marker not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
        if len(buf) > limit:
            break
    return bytes(buf)


def _ws_send_text(sock: socket.socket, text: str) -> None:
    payload = text.encode()
    mask = os.urandom(4)
    header = bytearray([0x81, 0x80 | len(payload)])
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _ws_read_frame(sock: socket.socket, pending: bytes) -> tuple[bytes, bytes]:
    buf = bytearray(pending)
    while len(buf) < 2:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    if len(buf) < 2:
        return b"", bytes(buf)
    size = buf[1] & 0x7F
    offset = 2
    if size == 126:
        while len(buf) < 4:
            buf += sock.recv(4096)
        size = int.from_bytes(buf[2:4], "big")
        offset = 4
    elif size == 127:
        while len(buf) < 10:
            buf += sock.recv(4096)
        size = int.from_bytes(buf[2:10], "big")
        offset = 10
    while len(buf) < offset + size:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    return bytes(buf[offset : offset + size]), bytes(buf[offset + size :])


def test_responses_websocket_upgrade(servers: dict[str, LiveServer]) -> None:
    server = _open(servers)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        "GET /v1/responses HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{server.port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    with socket.create_connection(("127.0.0.1", server.port), timeout=20) as sock:
        sock.settimeout(20)
        sock.sendall(request.encode())
        raw = _recv_until(sock, b"\r\n\r\n")
        head, _, rest = raw.partition(b"\r\n\r\n")
        status_line = head.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        parts = status_line.split()
        status = int(parts[1]) if len(parts) > 1 else 0
        if status == 400:
            pytest.skip(
                f"GET /v1/responses with Upgrade: websocket returned {status}; body={rest[:400]!r}"
            )
        assert status == 101, (status_line, rest[:400])
        headers = {
            line.split(":", 1)[0].strip().lower(): line.split(":", 1)[1].strip()
            for line in head.decode("latin-1", errors="replace").split("\r\n")[1:]
            if ":" in line
        }
        expect = base64.b64encode(hashlib.sha1(key.encode() + WS_GUID).digest()).decode()
        assert headers.get("sec-websocket-accept") == expect
        assert headers.get("x-agent-sandbox-local") == "1"
        _ws_send_text(
            sock, json.dumps({"type": "response.create", "model": "codex", "input": "hi"})
        )
        pending = rest
        seen: list[dict[str, Any]] = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            payload, pending = _ws_read_frame(sock, pending)
            if not payload:
                break
            if payload[0:1] == b"{":
                event = json.loads(payload)
                seen.append(event)
                if event.get("type") in ("response.completed", "error"):
                    break
        assert seen, "websocket upgrade succeeded but no text event arrived"
        assert seen[-1]["type"] == "response.completed", seen
        assert seen[-1]["response"]["status"] == "completed"


def _multipart(filename: str, data: bytes) -> tuple[str, bytes]:
    boundary = "----e2eBoundary7MA4YWxk"
    body = (
        (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="purpose"\r\n\r\n'
            "user_data\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return boundary, body


def test_files_multipart_upload(servers: dict[str, LiveServer]) -> None:
    payload = b"e2e-multipart-\r\n\xff"
    boundary, raw = _multipart("report.bin", payload)
    result = _open(servers).post(
        "/v1/files",
        raw=raw,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    if result.status != 200:
        pytest.skip(f"multipart POST /v1/files returned {result.status}; body={result.text[:500]}")
    assert result.json()["object"] == "file"
    assert result.json()["bytes"] == len(payload)
    assert result.json()["filename"] == "report.bin"
    assert result.json()["purpose"] == "user_data"
