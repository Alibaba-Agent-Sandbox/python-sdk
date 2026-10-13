"""Endpoints added for client/server alignment, exercised over real HTTP."""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._live import Live


def sse_events(raw: Any) -> list[tuple[str, dict[str, Any]]]:
    text = raw.decode() if isinstance(raw, bytes) else str(raw)
    events: list[tuple[str, dict[str, Any]]] = []
    for block in text.split("\n\n"):
        name, data = "", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if name:
            events.append((name, json.loads(data) if data else {}))
    return events


class TestShell:
    def test_cwd_env_timeout(self, live_server: Any, tmp_path: Path) -> None:
        live: Live = live_server()
        status, body = live.post(
            "/shell",
            {
                "command": "sh -c 'pwd; echo $GREETING'",
                "cwd": str(tmp_path),
                "env": {"GREETING": "hi"},
            },
        )
        assert status == 200
        assert body["stdout"].split() == [str(tmp_path.resolve()), "hi"]

    def test_timeout_is_enforced(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/shell", {"command": "sleep 5", "timeout": 0.3})
        assert status == 500 and body["type"] == "TimeoutError"

    def test_bad_cwd_is_400(self, live_server: Any, tmp_path: Path) -> None:
        live: Live = live_server()
        status, _ = live.post("/shell", {"command": "true", "cwd": str(tmp_path / "missing")})
        assert status == 400

    def test_cwd_outside_the_base_dir_is_denied(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/shell", {"command": "true", "cwd": "/definitely/not/here"})
        assert status == 403 and body["code"] == "path_not_allowed"

    def test_stream_honours_env(self, live_server: Any) -> None:
        live: Live = live_server()
        _, raw, _ = live.request(
            "POST", "/shell/stream", {"command": "sh -c 'echo $X'", "env": {"X": "streamed"}}
        )
        events = sse_events(raw)
        assert ("stdout", {"data": "streamed"}) in events
        assert events[-1] == ("exit", {"exit_code": 0})


class TestProcessIO:
    def test_capture_output_and_stdin_roundtrip(self, live_server: Any) -> None:
        live: Live = live_server()
        status, started = live.post(
            "/process/start", {"command": "cat", "capture_output": True, "stdin": True}
        )
        assert status == 200
        pid = started["pid"]
        status, wrote = live.post(f"/process/{pid}/stdin", {"data": "ping\n", "eof": True})
        assert status == 200 and wrote == {"pid": pid, "written": 5, "closed": True}
        status, out = live.get(f"/process/{pid}/output?wait=5&since=0")
        assert status == 200
        text = "".join(e["data"] for e in out["events"] if e["stream"] == "stdout")
        assert text == "ping\n"
        deadline = time.time() + 5
        while out["state"] != "exited" and time.time() < deadline:
            _, out = live.get(f"/process/{pid}/output?wait=1&since={out['next']}")
        assert out["state"] == "exited" and out["exit_code"] == 0

    def test_since_cursor_only_returns_new_events(self, live_server: Any) -> None:
        live: Live = live_server()
        _, started = live.post(
            "/process/start",
            {"command": "sh -c 'echo one; sleep 0.3; echo two'", "capture_output": True},
        )
        pid = started["pid"]
        _, first = live.get(f"/process/{pid}/output?wait=5")
        cursor = first["next"]
        _, rest = live.get(f"/process/{pid}/output?wait=5&since={cursor}")
        joined = "".join(e["data"] for e in first["events"] + rest["events"])
        assert joined.replace("\n", "") == "onetwo"
        assert all(e["seq"] >= cursor for e in rest["events"])

    def test_stdin_requires_flag(self, live_server: Any) -> None:
        live: Live = live_server()
        _, started = live.post("/process/start", {"command": "sleep 2"})
        status, _ = live.post(f"/process/{started['pid']}/stdin", {"data": "x"})
        assert status == 409

    def test_output_requires_capture(self, live_server: Any) -> None:
        live: Live = live_server()
        _, started = live.post("/process/start", {"command": "sleep 2"})
        status, _ = live.get(f"/process/{started['pid']}/output")
        assert status == 409

    def test_unknown_pid_and_bad_input(self, live_server: Any) -> None:
        live: Live = live_server()
        assert live.post("/process/999999/stdin", {"data": "x"})[0] == 404
        assert live.get("/process/999999/output")[0] == 404
        _, started = live.post(
            "/process/start", {"command": "cat", "stdin": True, "capture_output": True}
        )
        pid = started["pid"]
        assert live.post(f"/process/{pid}/stdin", {})[0] == 400
        assert live.post(f"/process/{pid}/stdin", {"data_base64": "!!"})[0] == 400
        assert live.get(f"/process/{pid}/output?since=abc")[0] == 400
        live.post(f"/process/{pid}/stdin", {"eof": True})

    def test_base64_stdin(self, live_server: Any) -> None:
        live: Live = live_server()
        _, started = live.post(
            "/process/start", {"command": "cat", "stdin": True, "capture_output": True}
        )
        pid = started["pid"]
        payload = base64.b64encode(b"\x00bin\n").decode()
        status, wrote = live.post(f"/process/{pid}/stdin", {"data_base64": payload, "eof": True})
        assert status == 200 and wrote["written"] == 5


class TestFilesWatch:
    def test_reports_created_modified_deleted(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server()
        watched = sandbox_tree / "out"

        def mutate() -> None:
            time.sleep(0.5)
            (watched / "new.txt").write_text("1")
            time.sleep(0.4)
            (watched / "a.txt").write_text("alpha-changed-longer")
            time.sleep(0.4)
            (watched / "new.txt").unlink()

        thread = threading.Thread(target=mutate)
        thread.start()
        _, raw, _ = live.request("GET", f"/files/watch?path={watched}&timeout=3&interval=0.1")
        thread.join()
        events = sse_events(raw)
        assert events[0][0] == "ready"
        assert events[-1] == ("end", {"reason": "timeout"})
        changes = {(e["type"], Path(e["path"]).name) for n, e in events if n == "change"}
        assert ("created", "new.txt") in changes
        assert ("modified", "a.txt") in changes
        assert ("deleted", "new.txt") in changes

    def test_validation(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server()
        assert live.get("/files/watch")[0] == 400
        assert live.get(f"/files/watch?path={sandbox_tree}/missing")[0] == 404
        assert live.get(f"/files/watch?path={sandbox_tree}&interval=x")[0] == 400
        assert live.get("/files/watch?path=/etc")[0] == 403


class TestPtyRest:
    def test_detail_and_resize(self, live_server: Any) -> None:
        live: Live = live_server()
        status, created = live.post("/pty/sessions", {"shell": "/bin/sh", "cols": 80, "rows": 24})
        assert status in (200, 201)
        sid = created["id"] if "id" in created else created["session_id"]
        try:
            status, detail = live.get(f"/pty/sessions/{sid}")
            assert status == 200 and detail["cols"] == 80 and detail["alive"] is True
            status, resized = live.post(f"/pty/sessions/{sid}/resize", {"cols": 100, "rows": 30})
            assert status == 200 and (resized["cols"], resized["rows"]) == (100, 30)
            assert live.get(f"/pty/sessions/{sid}")[1]["rows"] == 30
            assert live.post(f"/pty/sessions/{sid}/resize", {"cols": 0, "rows": 5})[0] == 400
            assert live.post(f"/pty/sessions/{sid}/resize", {"cols": "x"})[0] == 400
        finally:
            live.request("DELETE", f"/pty/sessions/{sid}")
        assert live.get(f"/pty/sessions/{sid}")[0] == 404
        assert live.post(f"/pty/sessions/{sid}/resize", {"cols": 5, "rows": 5})[0] == 404


class TestLegacyDiscovery:
    def test_capabilities_is_superset_of_legacy_shape(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.get("/capabilities")
        assert status == 200
        assert isinstance(body["groups"], dict)
        assert body["groups"]["file_ops"] is True
        assert body["groups"]["dev_tools"] is False
        assert "endpoints" in body

    def test_python_is_default_interpreter_for_code_run(self, live_server: Any) -> None:
        live: Live = live_server(policy={"groups": {"dev_tools": True}})
        status, body = live.post(
            "/code/run", {"language": "python", "code": "import sys; print(sys.version_info[0])"}
        )
        assert status == 200
        assert body["stdout"].strip() == "3"
        assert sys.version_info[0] == 3
