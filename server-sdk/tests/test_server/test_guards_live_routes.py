"""HTTP routes call the env, URL and process guards."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any
from unittest import mock

import easy_sandbox.server.routes_browser as routes_browser
import easy_sandbox.server.routes_devtools as routes_devtools

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from ._live import Live


class TestEnvRoutes:
    def test_denied_env_key_is_forbidden(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/env", {"vars": {"EBX_GUARD_PROBE": "x"}})
        assert status == 403
        assert body["code"] == "env_var_denied"
        assert "EBX_GUARD_PROBE" not in os.environ

        status, body = live.post(
            "/shell", {"command": "true", "env": {"EBX_FROM_SHELL": "1"}, "timeout": 1}
        )
        assert status == 403
        assert body["code"] == "env_var_denied"

        status, body = live.post(
            "/pty/sessions", {"shell": "/bin/sh", "env": {"EBX_FROM_PTY": "1"}}
        )
        assert status == 403
        assert body["code"] == "env_var_denied"

    def test_ordinary_env_succeeds(self, live_server: Any) -> None:
        live: Live = live_server()
        name = "ORDINARY_GUARD_VAR"
        os.environ.pop(name, None)
        try:
            status, body = live.post("/env", {"vars": {name: "ok"}})
            assert status == 200
            assert name in body["updated"]
            assert os.environ[name] == "ok"

            status, body = live.post(
                "/shell",
                {
                    "command": "sh -c 'printf %s \"$ORDINARY_GUARD_VAR\"'",
                    "env": {name: "from-shell"},
                },
            )
            assert status == 200
            assert body["exit_code"] == 0
            assert body["stdout"] == "from-shell"
        finally:
            os.environ.pop(name, None)

    def test_empty_env_stays_allowed(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/env", {"vars": {}})
        assert status == 200
        assert body["updated"] == []

        status, body = live.post("/shell", {"command": "true", "env": {}})
        assert status == 200
        assert body["exit_code"] == 0

        status, created = live.post("/pty/sessions", {"shell": "/bin/sh", "env": {}})
        assert status == 200
        live.request("DELETE", f"/pty/sessions/{created['session_id']}")

    def test_denied_env_does_not_run_the_command(self, live_server: Any, tmp_path: Path) -> None:
        live: Live = live_server()
        marker = tmp_path / "ran"
        status, body = live.post(
            "/shell",
            {"command": f"sh -c 'echo ran > {marker}'", "env": {"EBX_TOUCH": "1"}, "timeout": 1},
        )
        assert status == 403
        assert body["code"] == "env_var_denied"
        assert not marker.exists()


class TestUrlRoutes:
    def test_private_url_is_forbidden(self, live_server: Any) -> None:
        live: Live = live_server(policy={"groups": {"browser": True}})
        status, body = live.post("/browser/navigate", {"url": "https://10.0.0.5/"})
        assert status == 403
        assert body["code"] == "url_denied"

        status, body = live.post("/browser/navigate", {"url": "https://127.0.0.1/"})
        assert status == 403
        assert body["code"] == "url_denied"

    def test_public_https_url_succeeds(self, live_server: Any) -> None:
        page = mock.MagicMock()
        page.is_closed.return_value = False
        page.url = "https://example.com/path"
        page.title.return_value = "Example"
        response = mock.MagicMock()
        response.status = 200
        page.goto.return_value = response
        saved = (
            routes_browser._playwright_instance,
            routes_browser._browser,
            routes_browser._page,
        )
        routes_browser._playwright_instance = mock.MagicMock()
        routes_browser._browser = mock.MagicMock()
        routes_browser._page = page
        try:
            live: Live = live_server(policy={"groups": {"browser": True}})
            status, body = live.post("/browser/navigate", {"url": "https://example.com/path"})
            assert status == 200
            assert body["url"] == "https://example.com/path"
            assert body["status"] == 200
            page.goto.assert_called_once()
            assert page.goto.call_args.args[0] == "https://example.com/path"
        finally:
            (
                routes_browser._playwright_instance,
                routes_browser._browser,
                routes_browser._page,
            ) = saved


class TestProcessRoutes:
    def test_proc_argv_is_forbidden(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/shell", {"command": "/proc/self/exe", "timeout": 1})
        assert status == 403
        assert body["code"] == "process_denied"

        status, raw, _ = live.request("POST", "/shell/stream", {"command": "/proc/self/exe"})
        assert status == 403
        assert raw["code"] == "process_denied"

        status, body = live.post("/process/start", {"command": "/proc/self/exe"})
        if status == 200:
            live.post(f"/process/{body['pid']}/signal", {"signal": 9})
        assert status == 403
        assert body["code"] == "process_denied"

    def test_normal_command_succeeds(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.post("/shell", {"command": "echo ok"})
        assert status == 200
        assert body["exit_code"] == 0
        assert body["stdout"] == "ok\n"

        status, started = live.post("/process/start", {"command": "true"})
        assert status == 200
        assert isinstance(started["pid"], int)

    def test_code_run_succeeds_and_refuses_proc_interpreter(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        live: Live = live_server(policy={"groups": {"dev_tools": True}})
        status, body = live.post("/code/run", {"language": "python", "code": "print(1)"})
        assert status == 200
        assert body["stdout"] == "1\n"
        assert body["exit_code"] == 0

        monkeypatch.setitem(routes_devtools._LANGUAGE_COMMANDS, "python", ["/proc/self/exe"])
        status, body = live.post(
            "/code/run", {"language": "python", "code": "print(1)", "timeout": 1}
        )
        assert status == 403
        assert body["code"] == "process_denied"
