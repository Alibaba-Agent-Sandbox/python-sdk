"""agent-sandbox-server (server-sdk) running inside a real sandbox (template ``python-hello``).

The official ``python-hello`` template ships the server but the platform does not start the image
``CMD`` for first-generation sandboxes, so the ``server`` fixture starts it explicitly. Everything
else goes through the public gateway URL ``https://<port>-<sandbox id>.<domain>``.
"""

from __future__ import annotations

import base64
import time

import pytest

import e2e_helpers as H

HOME = "/home/user"


def _dir() -> str:
    return f"{HOME}/{H.unique_dir('srv').split('/')[-1]}"


def test_health_and_command_catalogue(server):  # type: ignore[no-untyped-def]
    assert server.get("/health").json() == {"status": "ok"}
    names = {c["name"] for c in server.get("/commands").json()["commands"]}
    assert {"hello", "run_script"} <= names
    assert "_debug_info" not in names  # hidden=True


def test_run_registered_command(server):  # type: ignore[no-untyped-def]
    r = server.post("/commands/hello", json={"name": "e2e"})
    assert r.status_code == 200
    assert r.json() == {"result": "Hello, e2e!"}
    assert server.post("/commands/hello", json={}).json() == {"result": "Hello, World!"}


def test_run_script_command_executes_python(server):  # type: ignore[no-untyped-def]
    r = server.post("/commands/run_script", json={"code": "print(6*7)"})
    assert r.status_code == 200
    assert r.json()["result"].strip() == "42"


def test_unknown_command_is_404(server):  # type: ignore[no-untyped-def]
    assert server.post("/commands/does_not_exist", json={}).status_code == 404


def test_missing_required_argument_is_client_error(server):  # type: ignore[no-untyped-def]
    r = server.post("/commands/run_script", json={})
    assert 400 <= r.status_code < 500


def test_custom_route_from_template(server):  # type: ignore[no-untyped-def]
    r = server.get("/hello/e2e-user")
    assert r.status_code == 200
    assert r.json() == {"greeting": "Hello, e2e-user!"}


def test_capabilities_report_enabled_groups(server):  # type: ignore[no-untyped-def]
    groups = server.get("/capabilities").json()["groups"]
    assert groups["file_ops"] is True and groups["process"] is True and groups["system"] is True
    assert groups["browser"] is False


def test_system_info_and_ports(server):  # type: ignore[no-untyped-def]
    info = server.get("/system/info").json()
    assert info["os"] == "Linux" and info["cpu_count"] >= 1 and info["memory_total_mb"] > 0
    ports = {p["port"] for p in server.get("/ports").json()["listening"]}
    assert 9000 in ports


def test_files_upload_download_roundtrip_and_stat(server):  # type: ignore[no-untyped-def]
    d = _dir()
    content = b"server-sdk \x00\x01 binary \xff"
    r = server.post(
        "/files/upload-stream",
        json={"path": f"{d}/a.bin", "content_base64": base64.b64encode(content).decode()},
    )
    assert r.status_code == 200, r.text
    assert r.json()["bytes"] == len(content)
    dl = server.get("/files/download-stream", params={"path": f"{d}/a.bin"}).json()
    assert base64.b64decode(dl["content_base64"]) == content
    st = server.get("/files/stat", params={"path": f"{d}/a.bin"})
    assert st.status_code == 200
    assert st.json()["size"] == len(content) and st.json()["exists"] is True


def test_legacy_upload_and_download_routes(server):  # type: ignore[no-untyped-def]
    d = _dir()
    payload = base64.b64encode(b"legacy-route").decode()
    assert (
        server.post(
            "/files/upload-stream", json={"path": f"{d}/l.txt", "content_base64": payload}
        ).status_code
        == 200
    )
    r = server.get("/files/download-stream", params={"path": f"{d}/l.txt"})
    assert base64.b64decode(r.json()["content_base64"]) == b"legacy-route"


def test_files_mkdir_list_move_search_delete(server):  # type: ignore[no-untyped-def]
    d = _dir()
    assert server.post("/files/mkdir", json={"path": f"{d}/sub"}).status_code in (200, 201)
    for name in ("alpha.txt", "beta.log"):
        server.post(
            "/files/upload-stream",
            json={"path": f"{d}/{name}", "content_base64": base64.b64encode(b"x").decode()},
        )
    entries = server.get("/files/list", params={"path": d}).json()
    listed = entries["entries"] if isinstance(entries, dict) else entries
    types = {e["name"]: e["type"] for e in listed}
    assert types["sub"] == "directory" and types["alpha.txt"] == "file"

    mv = server.post(
        "/files/move", json={"source": f"{d}/alpha.txt", "destination": f"{d}/sub/moved.txt"}
    )
    assert mv.status_code == 200, mv.text
    found = server.post("/files/search", json={"path": d, "pattern": "*.txt"}).json()
    flat = str(found)
    assert "moved.txt" in flat and "beta.log" not in flat

    assert (
        server.request("DELETE", "/files", params={"path": f"{d}/sub/moved.txt"}).status_code == 200
    )
    gone = server.get("/files/stat", params={"path": f"{d}/sub/moved.txt"}).json()
    assert gone["exists"] is False


def test_files_outside_base_dir_are_rejected(server):  # type: ignore[no-untyped-def]
    r = server.get("/files/list", params={"path": "/etc"})
    assert r.status_code in (400, 403)
    r = server.get("/files/download-stream", params={"path": f"{HOME}/../../etc/passwd"})
    assert r.status_code in (400, 403, 404)


def test_shell_endpoint_runs_a_command(server):  # type: ignore[no-untyped-def]
    r = server.post("/shell", json={"command": "echo from-server-shell"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "from-server-shell" in body["stdout"]
    assert body["exit_code"] == 0


def test_process_start_list_signal(server):  # type: ignore[no-untyped-def]
    r = server.post("/process/start", json={"command": "sleep 113"})
    assert r.status_code == 200, r.text
    pid = r.json()["pid"]
    listed = server.get("/process/list").json()
    procs = listed["processes"] if isinstance(listed, dict) else listed
    assert any(p["pid"] == pid for p in procs)
    detail = server.get(f"/process/{pid}")
    assert detail.status_code == 200
    sig = server.post(f"/process/{pid}/signal", json={"signal": 15})
    assert sig.status_code == 200, sig.text

    def _gone() -> bool:
        d = server.get(f"/process/{pid}")
        return d.status_code == 404 or d.json().get("state") == "exited"

    H.eventually(_gone, timeout=20, interval=1, what="signalled process to exit")


def test_sdk_list_commands_returns_server_commands(run, server_sandbox, server):  # type: ignore[no-untyped-def]
    cmds = run(server_sandbox.list_commands())
    by_name = {c.name: c for c in cmds}
    assert by_name["hello"].args[0].name == "name"


def test_sdk_run_dispatches_to_the_server(run, server_sandbox, server):  # type: ignore[no-untyped-def]
    assert run(server_sandbox.run("hello", name="sdk")) == "Hello, sdk!"


def test_sdk_run_unknown_command_raises(run, server_sandbox, server):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import CommandNotFoundError

    with pytest.raises(CommandNotFoundError):
        run(server_sandbox.run("e2e_unknown_command"))


def test_server_survives_a_burst_of_requests(server):  # type: ignore[no-untyped-def]
    started = time.monotonic()
    codes = [server.post("/commands/hello", json={"name": str(i)}).status_code for i in range(15)]
    assert codes == [200] * 15
    assert time.monotonic() - started < 60
