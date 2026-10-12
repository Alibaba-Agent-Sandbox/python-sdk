"""Policy enforcement for exec-style, devtools and browser endpoints."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from ._live import Live


class TestShellRules:
    def test_allow_commands_by_basename_and_full_path(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={"endpoints": {"shell": {"params": {"allow_commands": ["echo", "ls"]}}}}
        )
        assert live.post("/shell", {"command": "echo hi"})[0] == 200
        status, body = live.post("/shell", {"command": "/bin/echo hi"})
        assert status == 200
        status, body = live.post("/shell", {"command": "cat /etc/hostname"})
        assert status == 403 and body["code"] == "command_not_allowed"
        status, body = live.post("/shell", {"command": "/usr/bin/cat /etc/hostname"})
        assert status == 403

    def test_deny_commands_glob(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={"endpoints": {"shell": {"params": {"deny_commands": ["rm", "mk*"]}}}}
        )
        assert live.post("/shell", {"command": "rm -rf /tmp/x"})[0] == 403
        assert live.post("/shell", {"command": "/bin/rm x"})[0] == 403
        assert live.post("/shell", {"command": "mkdir x"})[0] == 403
        assert live.post("/shell", {"command": "echo ok"})[0] == 200

    def test_rules_apply_to_stream_and_process_start(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={
                "endpoints": {
                    "@defaults": {"params": {"deny_commands": ["env"]}},
                }
            }
        )
        status, body, _ = live.request("POST", "/shell/stream", {"command": "env"})
        assert status == 403
        assert live.post("/process/start", {"command": "env"})[0] == 403

    def test_timeout_cap(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={"endpoints": {"shell": {"limits": {"timeout_seconds": 1}}}}
        )
        status, body = live.post("/shell", {"command": "sleep 5", "timeout": 60})
        assert status == 500 and body["type"] == "TimeoutError"

    def test_output_truncation(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={"endpoints": {"shell": {"limits": {"max_output_bytes": 10}}}}
        )
        status, body = live.post("/shell", {"command": "sh -c 'yes a | head -c 500'"})
        assert status == 200 and body["truncated"] is True and len(body["stdout"]) == 10

    def test_cwd_is_guarded(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server(
            policy={"endpoints": {"shell": {"paths": {"allow": [str(sandbox_tree / "out")]}}}}
        )
        status, body = live.post("/shell", {"command": "pwd", "cwd": str(sandbox_tree / "out")})
        assert status == 200
        status, body = live.post("/shell", {"command": "pwd", "cwd": str(sandbox_tree / "secret")})
        assert status == 403 and body["code"].startswith("path_")
        status, body = live.post("/shell", {"command": "pwd", "cwd": "/"})
        assert status == 403


class TestSecretEnvironment:
    def test_server_secrets_never_reach_children(self, live_server: Any, monkeypatch: Any) -> None:
        token = "scrub-test-token-123"
        monkeypatch.setenv("MY_SERVER_TOKEN", token)
        monkeypatch.setenv("UNRELATED_VAR", "kept")
        live: Live = live_server(
            policy={
                "auth": {"tokens": [{"id": "a", "token_env": "MY_SERVER_TOKEN", "scopes": ["*"]}]}
            }
        )
        h = {"X-Access-Token": token}
        status, body = live.post("/shell", {"command": "env"}, headers=h)
        assert status == 200
        assert token not in body["stdout"]
        assert "UNRELATED_VAR=kept" in body["stdout"]
        status, body = live.post(
            "/shell", {"command": "true", "env": {"MY_SERVER_TOKEN": "x"}}, headers=h
        )
        assert status == 403 and body["code"] == "env_var_not_allowed"

    def test_env_endpoint_redacts_server_secrets(self, live_server: Any, monkeypatch: Any) -> None:
        token = "redact-test-token-123"
        monkeypatch.setenv("MY_SERVER_TOKEN", token)
        live: Live = live_server(
            policy={
                "auth": {"tokens": [{"id": "a", "token_env": "MY_SERVER_TOKEN", "scopes": ["*"]}]}
            }
        )
        status, body = live.get("/env", headers={"X-Access-Token": token})
        assert status == 200
        assert token not in str(body)


class TestDevtools:
    def test_code_run_language_allow_list(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={
                "groups": {"dev_tools": True},
                "endpoints": {"code_run": {"params": {"languages": ["python"]}}},
            }
        )
        status, body = live.post("/code/run", {"language": "python", "code": "print(1)"})
        assert status == 200
        status, body = live.post("/code/run", {"language": "bash", "code": "echo 1"})
        assert status == 403 and body["code"] == "language_not_allowed"

    def test_code_run_timeout_cap_and_truncation(self, live_server: Any) -> None:
        live: Live = live_server(
            policy={
                "groups": {"dev_tools": True},
                "endpoints": {
                    "code_run": {"limits": {"timeout_seconds": 1, "max_output_bytes": 5}}
                },
            }
        )
        status, body = live.post(
            "/code/run", {"language": "python", "code": "print('x'*100)", "timeout": 60}
        )
        assert status == 200
        assert len(body["stdout"]) <= 5

    def test_devtools_group_off_by_default(self, live_server: Any) -> None:
        live: Live = live_server()
        status, _ = live.post("/code/run", {"language": "python", "code": "print(1)"})
        assert status == 404

    def test_git_diff_requires_file_when_deny_rules_exist(
        self, live_server: Any, sandbox_tree: Path, monkeypatch: Any
    ) -> None:
        repo = sandbox_tree
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        monkeypatch.chdir(repo)
        live: Live = live_server(
            policy={
                "groups": {"dev_tools": True},
                "endpoints": {"git_diff": {"paths": {"deny": [str(repo / "secret")]}}},
            }
        )
        status, body = live.get(f"/git/diff?path={repo}")
        assert status in (400, 403)
        status, body = live.get(f"/git/diff?path={repo}&file=secret/s.txt")
        assert status in (400, 403)


class TestBrowserUrlRules:
    def _live(self, live_server: Any, **params: Any) -> Live:
        return live_server(
            policy={
                "groups": {"browser": True},
                "endpoints": {"browser_navigate": {"params": params}},
            }
        )

    def test_url_deny(self, live_server: Any) -> None:
        live = self._live(live_server, url_deny=["*://169.254.*"])
        status, body = live.post("/browser/navigate", {"url": "http://169.254.169.254/latest"})
        assert status == 403 and body["code"] == "url_not_allowed"

    def test_url_allow_list(self, live_server: Any) -> None:
        live = self._live(live_server, url_allow=["https://example.com/*"])
        status, body = live.post("/browser/navigate", {"url": "https://evil.test/"})
        assert status == 403 and body["code"] == "url_not_allowed"

    def test_non_http_schemes_blocked(self, live_server: Any) -> None:
        live = self._live(live_server, url_deny=["http://never.invalid/*"])
        for url in ("file:///etc/passwd", "javascript:alert(1)", "ftp://x/y"):
            status, body = live.post("/browser/navigate", {"url": url})
            assert status == 403, url

    def test_block_private_networks(self, live_server: Any) -> None:
        live = self._live(live_server, block_private_networks=True)
        for url in (
            "http://127.0.0.1:1/",
            "http://localhost/",
            "http://[::1]/",
            "http://10.0.0.1/",
        ):
            status, body = live.post("/browser/navigate", {"url": url})
            assert status == 403, url
