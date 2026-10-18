"""End-to-end policy pipeline against a real in-process server."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Any

from agent_sandbox.server.registry import CommandRegistry
from agent_sandbox.server.router import RouteTable

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from ._live import Live

READER = "reader-token-123456"
WRITER = "writer-token-654321"
ADMIN = "admin-token-abcdef"


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_policy(**extra: Any) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "auth": {
            "tokens": [
                {"id": "reader", "token_sha256": sha(READER), "scopes": ["files:read"]},
                {"id": "writer", "token_sha256": sha(WRITER), "scopes": ["files:write"]},
                {"id": "admin", "token_sha256": sha(ADMIN), "scopes": ["*"]},
            ]
        }
    }
    policy.update(extra)
    return policy


def hdr(token: str, bearer: bool = False) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if bearer else {"X-Access-Token": token}


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class TestAuthentication:
    def test_health_is_open_and_others_need_a_token(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        assert live.get("/health")[0] == 200
        status, body = live.get("/capabilities")
        assert status == 401 and body["code"] == "unauthorized"

    def test_both_header_styles_work(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        assert live.get("/capabilities", headers=hdr(READER))[0] == 200
        assert live.get("/capabilities", headers=hdr(READER, bearer=True))[0] == 200

    def test_wrong_token(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        assert live.get("/capabilities", headers=hdr("nope"))[0] == 401
        assert live.get("/capabilities", headers=hdr(""))[0] == 401

    def test_gateway_header_plus_bearer_prefers_valid_one(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        headers = {"X-Access-Token": "gateway-injected", "Authorization": f"Bearer {READER}"}
        assert live.get("/capabilities", headers=headers)[0] == 200

    def test_ambiguous_x_access_token_rejected(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        raw = (
            f"GET /capabilities HTTP/1.1\r\nHost: 127.0.0.1:{live.port}\r\n"
            f"X-Access-Token: {READER}\r\n"
            f"X-Access-Token: {ADMIN}\r\nConnection: close\r\n\r\n"
        ).encode()
        import socket

        with socket.create_connection(("127.0.0.1", live.port), timeout=5) as s:
            s.sendall(raw)
            data = b""
            while chunk := s.recv(4096):
                data += chunk
        assert data.startswith(b"HTTP/1.0 400") or data.startswith(b"HTTP/1.1 400")
        assert b"ambiguous_credentials" in data

    def test_anonymous_disabled_when_tokens_configured_but_can_opt_in(
        self, live_server: Any
    ) -> None:
        policy = tokens_policy()
        policy["auth"]["allow_anonymous"] = True
        policy["auth"]["anonymous_scopes"] = ["files:read"]
        live: Live = live_server(policy=policy)
        status, body = live.get("/capabilities")
        assert status == 200 and body["identity"] == {"id": "anonymous", "scopes": ["files:read"]}

    def test_token_env_resolution(self, live_server: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ABX_T_ENV", "from-env-token")
        live: Live = live_server(
            policy={"auth": {"tokens": [{"id": "e", "token_env": "ABX_T_ENV", "scopes": ["*"]}]}}
        )
        assert live.get("/capabilities", headers=hdr("from-env-token"))[0] == 200
        assert live.get("/capabilities", headers=hdr("other"))[0] == 401

    def test_legacy_env_token_still_works_with_policy(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ABX_SERVER_TOKEN", "legacy-secret")
        live: Live = live_server(policy={"preset": "default"})
        assert live.get("/capabilities")[0] == 401
        status, body = live.get("/capabilities", headers=hdr("legacy-secret"))
        assert status == 200 and body["identity"]["id"] == "legacy"

    def test_legacy_scopes_can_be_narrowed(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ABX_SERVER_TOKEN", "legacy-secret")
        live: Live = live_server(policy={"auth": {"legacy_scopes": ["files:read"]}})
        assert live.post("/shell", {"command": "true"}, headers=hdr("legacy-secret"))[0] == 403


class TestScopes:
    def test_scope_enforced_per_endpoint(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server(policy=tokens_policy())
        path = str(sandbox_tree / "out" / "a.txt")
        status, body = live.get(f"/files/stat?path={path}", headers=hdr(READER))
        assert status == 200 and body["exists"] is True
        status, body = live.post(
            "/files/mkdir", {"path": str(sandbox_tree / "new")}, headers=hdr(READER)
        )
        assert status == 403
        assert body["code"] == "missing_scope" and body["scope"] == "files:write"
        assert body["endpoint"] == "files_mkdir" and body["type"] == "PolicyDenied"
        assert (
            live.post("/files/mkdir", {"path": str(sandbox_tree / "new")}, headers=hdr(WRITER))[0]
            == 200
        )
        assert live.get(f"/files/stat?path={path}", headers=hdr(WRITER))[0] == 403

    def test_move_requires_both_write_and_delete(
        self, live_server: Any, sandbox_tree: Path
    ) -> None:
        live: Live = live_server(policy=tokens_policy())
        body = {
            "source": str(sandbox_tree / "out" / "a.txt"),
            "destination": str(sandbox_tree / "out" / "b.txt"),
        }
        assert live.post("/files/move", body, headers=hdr(WRITER))[0] == 403
        assert live.post("/files/move", body, headers=hdr(ADMIN))[0] == 200

    def test_namespace_wildcard_scope(self, live_server: Any, sandbox_tree: Path) -> None:
        policy = tokens_policy()
        policy["auth"]["tokens"][0]["scopes"] = ["files:*"]
        live: Live = live_server(policy=policy)
        status, _ = live.post(
            "/files/mkdir", {"path": str(sandbox_tree / "x")}, headers=hdr(READER)
        )
        assert status == 200
        assert live.post("/shell", {"command": "true"}, headers=hdr(READER))[0] == 403

    def test_scope_override_in_rule(self, live_server: Any, sandbox_tree: Path) -> None:
        policy = tokens_policy(endpoints={"files_stat": {"scopes": ["files:write"]}})
        live: Live = live_server(policy=policy)
        path = str(sandbox_tree / "out" / "a.txt")
        assert live.get(f"/files/stat?path={path}", headers=hdr(READER))[0] == 403
        assert live.get(f"/files/stat?path={path}", headers=hdr(WRITER))[0] == 200

    def test_disabled_endpoint_is_404_even_for_admin(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy(endpoints={"shell": {"enabled": False}}))
        status, body = live.post("/shell", {"command": "true"}, headers=hdr(ADMIN))
        assert status == 404 and body["code"] == "endpoint_disabled"

    def test_group_disabled_is_404(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy(groups={"process": False}))
        status, body = live.post("/shell", {"command": "true"}, headers=hdr(ADMIN))
        assert status == 404 and body["code"] == "endpoint_disabled"

    def test_custom_route_scopes(self, live_server: Any) -> None:
        table = RouteTable()

        @table.route(
            "GET",
            "/hello",
            group=__import__(
                "agent_sandbox.server.router", fromlist=["CapabilityGroup"]
            ).CapabilityGroup.CORE,
            name="hello",
            scopes=["hello:read"],
        )
        def hello(request: Any) -> Any:
            from agent_sandbox.server.types import ServerResponse

            return ServerResponse.ok({"hi": request.context["policy"].identity.id})

        policy = {
            "auth": {
                "tokens": [
                    {"id": "yes", "token_sha256": sha("yes-token-xxxx"), "scopes": ["hello:read"]},
                    {"id": "no", "token_sha256": sha("no-token-xxxxx"), "scopes": ["files:read"]},
                ]
            }
        }
        live: Live = live_server(policy=policy, route_table=table)
        assert live.get("/hello", headers=hdr("yes-token-xxxx")) == (200, {"hi": "yes"})
        assert live.get("/hello", headers=hdr("no-token-xxxxx"))[0] == 403


class TestCommandScopes:
    def make(self, live_server: Any) -> Live:
        registry = CommandRegistry()

        @registry.command("greet")
        def greet(name: str = "x") -> str:
            return f"hi {name}"

        registry.register("deploy", lambda: "deployed", scopes=["deploy"])
        policy = {
            "auth": {
                "tokens": [
                    {
                        "id": "runner",
                        "token_sha256": sha("runner-token-1"),
                        "scopes": ["commands:list", "commands:run"],
                    },
                    {
                        "id": "deployer",
                        "token_sha256": sha("deployer-token-1"),
                        "scopes": ["commands:*", "deploy"],
                    },
                ]
            }
        }
        return live_server(policy=policy, registry=registry)

    def test_listing_only_shows_runnable_commands(self, live_server: Any) -> None:
        live = self.make(live_server)
        _, body = live.get("/commands", headers=hdr("runner-token-1"))
        assert [c["name"] for c in body["commands"]] == ["greet"]
        _, body = live.get("/commands", headers=hdr("deployer-token-1"))
        assert sorted(c["name"] for c in body["commands"]) == ["deploy", "greet"]

    def test_run_requires_command_scope(self, live_server: Any) -> None:
        live = self.make(live_server)
        status, body = live.post("/commands/deploy", {}, headers=hdr("runner-token-1"))
        assert status == 403 and body["scope"] == "deploy"
        status, body = live.post("/commands/deploy", {}, headers=hdr("deployer-token-1"))
        assert status == 200 and body["result"] == "deployed"
        assert live.post("/commands/greet", {"name": "z"}, headers=hdr("runner-token-1"))[1] == {
            "result": "hi z"
        }


class TestLimitsAndRates:
    def test_rate_limit_returns_429_with_retry_after(self, live_server: Any) -> None:
        live: Live = live_server(
            policy=tokens_policy(endpoints={"system_info": {"limits": {"rate_per_minute": 2}}})
        )
        statuses = [live.get("/system/info", headers=hdr(ADMIN))[0] for _ in range(3)]
        assert statuses == [200, 200, 429]
        status, body, headers = live.request("GET", "/system/info", headers=hdr(ADMIN))
        assert status == 429 and body["code"] == "rate_limited"
        assert int(headers["retry-after"]) >= 1

    def test_rate_limit_is_per_identity(self, live_server: Any) -> None:
        policy = tokens_policy(endpoints={"system_info": {"limits": {"rate_per_minute": 1}}})
        policy["auth"]["tokens"][0]["scopes"] = ["system:read"]
        live: Live = live_server(policy=policy)
        assert live.get("/system/info", headers=hdr(READER))[0] == 200
        assert live.get("/system/info", headers=hdr(READER))[0] == 429
        assert live.get("/system/info", headers=hdr(ADMIN))[0] == 200

    def test_concurrency_limit(self, live_server: Any) -> None:
        live: Live = live_server(
            policy=tokens_policy(
                endpoints={
                    "shell": {"limits": {"max_concurrency": 1}},
                }
            )
        )
        results: list[int] = []

        def slow() -> None:
            results.append(live.post("/shell", {"command": "sleep 1"}, headers=hdr(ADMIN))[0])

        t = threading.Thread(target=slow)
        t.start()
        time.sleep(0.4)
        status, body = live.post("/shell", {"command": "true"}, headers=hdr(ADMIN))
        assert status == 429 and body["code"] == "concurrency_limited"
        t.join()
        assert results == [200]
        assert live.post("/shell", {"command": "true"}, headers=hdr(ADMIN))[0] == 200

    def test_request_size_cap_per_endpoint(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server(
            policy=tokens_policy(
                endpoints={"files_upload_stream": {"limits": {"max_request_bytes": 200}}}
            )
        )
        body = {"path": str(sandbox_tree / "big"), "content_base64": b64(b"x" * 1000)}
        status, resp = live.post("/files/upload-stream", body, headers=hdr(ADMIN))
        assert status == 413 and resp["code"] == "payload_too_large" and resp["limit"] == 200
        assert not (sandbox_tree / "big").exists()


def _audit_events(caplog: pytest.LogCaptureFixture, expected: int) -> list[dict[str, Any]]:
    """The audit line is written after the response; wait for it instead of racing."""
    deadline = time.monotonic() + 3
    while True:
        events = [json.loads(r.message) for r in caplog.records if r.name.endswith("audit")]
        if len(events) >= expected or time.monotonic() > deadline:
            return events
        time.sleep(0.02)


class TestAudit:
    def test_deny_mode_logs_only_denials(
        self, live_server: Any, caplog: pytest.LogCaptureFixture, sandbox_tree: Path
    ) -> None:
        live: Live = live_server(policy=tokens_policy())
        with caplog.at_level(logging.INFO, logger="agent_sandbox.server.audit"):
            live.get(f"/files/stat?path={sandbox_tree}", headers=hdr(READER))
            live.post("/files/mkdir", {"path": str(sandbox_tree / "n")}, headers=hdr(READER))
            events = _audit_events(caplog, expected=1)
        assert len(events) == 1
        event = events[0]
        assert event["endpoint"] == "files_mkdir" and event["decision"] == "deny"
        assert event["identity"] == "reader" and event["code"] == "missing_scope"
        assert "token" not in json.dumps(event).lower()

    def test_all_mode_logs_allowed_with_resolved_paths(
        self, live_server: Any, caplog: pytest.LogCaptureFixture, sandbox_tree: Path
    ) -> None:
        live: Live = live_server(policy=tokens_policy(endpoints={"files_stat": {"audit": "all"}}))
        path = str(sandbox_tree / "out" / "a.txt")
        with caplog.at_level(logging.INFO, logger="agent_sandbox.server.audit"):
            live.get(f"/files/stat?path={path}", headers=hdr(READER))
            event = _audit_events(caplog, expected=1)[-1]
        assert event["decision"] == "allow" and event["paths"] == [path]

    def test_off_mode_is_silent(self, live_server: Any, caplog: pytest.LogCaptureFixture) -> None:
        live: Live = live_server(policy=tokens_policy(defaults={"audit": "off"}))
        with caplog.at_level(logging.INFO, logger="agent_sandbox.server.audit"):
            live.get("/capabilities")
        assert not [r for r in caplog.records if r.name.endswith("audit")]

    def test_audit_line_is_single_json_even_with_hostile_path(
        self, live_server: Any, caplog: pytest.LogCaptureFixture, sandbox_tree: Path
    ) -> None:
        live: Live = live_server(policy=tokens_policy(defaults={"audit": "all"}))
        evil = str(sandbox_tree / 'a\nINJECTED {"x":1}')
        with caplog.at_level(logging.INFO, logger="agent_sandbox.server.audit"):
            live.get(
                "/files/stat?path=" + evil.replace("\n", "%0A").replace(" ", "%20"),
                headers=hdr(READER),
            )
            _audit_events(caplog, expected=1)
        records = [r for r in caplog.records if r.name.endswith("audit")]
        assert records
        for record in records:
            assert "\n" not in record.message
            json.loads(record.message)


class TestDiscovery:
    def test_v2_document_and_legacy_superset(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy(preset="transfer-only"))
        status, body = live.get("/capabilities", headers=hdr(READER))
        assert status == 200
        assert body["api_version"] == 2 and "groups" in body
        assert body["identity"] == {"id": "reader", "scopes": ["files:read"]}
        assert body["policy"]["preset"] == "transfer-only" and body["policy"]["configured"]
        eps = body["endpoints"]
        assert eps["download"]["allowed"] is True
        assert eps["upload"]["allowed"] is False and eps["upload"]["reason"] == "missing_scope"
        assert eps["files_list"]["reason"] == "endpoint_disabled"
        assert eps["shell"]["enabled"] is True or eps["shell"]["reason"] == "endpoint_disabled"
        assert eps["download"]["method"] == "GET" and eps["download"]["path"] == "/download"

    def test_denied_endpoints_do_not_leak_config(self, live_server: Any) -> None:
        policy = tokens_policy(
            endpoints={"files_stat": {"paths": {"allow": ["/srv/secret-place"]}}}
        )
        live: Live = live_server(policy=policy)
        _, body = live.get("/capabilities", headers=hdr(WRITER))
        entry = body["endpoints"]["files_stat"]
        assert entry["allowed"] is False and "paths" not in entry and "limits" not in entry
        _, body = live.get("/capabilities", headers=hdr(READER))
        assert body["endpoints"]["files_stat"]["paths"]["allow"] == ["/srv/secret-place"]

    def test_wildcard_identity_gets_warning(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        _, body = live.get("/capabilities", headers=hdr(ADMIN))
        assert any("wildcard" in w for w in body["warnings"])
        _, body = live.get("/capabilities", headers=hdr(READER))
        assert body["warnings"] == []

    def test_revision_changes_with_policy(self, live_server: Any) -> None:
        a: Live = live_server(policy=tokens_policy())
        b: Live = live_server(policy=tokens_policy(preset="read-only"))
        ra = a.get("/capabilities", headers=hdr(ADMIN))[1]["policy"]["revision"]
        rb = b.get("/capabilities", headers=hdr(ADMIN))[1]["policy"]["revision"]
        assert ra != rb

    def test_check_endpoint_matches_enforcement(self, live_server: Any, sandbox_tree: Path) -> None:
        policy = tokens_policy(
            endpoints={"files_download_stream": {"paths": {"allow": [str(sandbox_tree / "out")]}}}
        )
        live: Live = live_server(policy=policy)
        ok = {"endpoint": "files_download_stream", "path": str(sandbox_tree / "out" / "a.txt")}
        bad = {"endpoint": "files_download_stream", "path": str(sandbox_tree / "secret" / "s.txt")}
        assert live.post("/capabilities/check", ok, headers=hdr(READER))[1]["allowed"] is True
        decision = live.post("/capabilities/check", bad, headers=hdr(READER))[1]
        assert decision["allowed"] is False and decision["code"] == "path_not_allowed"
        status, body = live.get(f"/files/download-stream?path={bad['path']}", headers=hdr(READER))
        assert status == 403 and body["code"] == decision["code"]
        assert (
            live.post("/capabilities/check", {"endpoint": "upload"}, headers=hdr(READER))[1]["code"]
            == "missing_scope"
        )

    def test_check_does_not_reveal_existence(self, live_server: Any, sandbox_tree: Path) -> None:
        policy = tokens_policy(
            endpoints={"files_stat": {"paths": {"allow": [str(sandbox_tree / "out")]}}}
        )
        live: Live = live_server(policy=policy)
        present = {"endpoint": "files_stat", "path": str(sandbox_tree / "out" / "a.txt")}
        missing = {"endpoint": "files_stat", "path": str(sandbox_tree / "out" / "nope.txt")}
        a = live.post("/capabilities/check", present, headers=hdr(READER))[1]
        b = live.post("/capabilities/check", missing, headers=hdr(READER))[1]
        assert a == b | {"endpoint": "files_stat"} and a["allowed"] is True

    def test_check_validates_input(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        for bad in (
            {},
            {"endpoint": 5},
            {"endpoint": "x", "paths": "no"},
            {"endpoint": "x", "op": "fly"},
            {"endpoint": "x", "path": 1},
        ):
            assert live.post("/capabilities/check", bad, headers=hdr(ADMIN))[0] == 400

    def test_unconfigured_server_serves_additive_discovery(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = live.get("/capabilities")
        assert status == 200
        assert body["groups"]["file_ops"] is True and body["groups"]["browser"] is False
        assert body["policy"]["configured"] is False
        assert body["endpoints"]["files_list"]["allowed"] is True
        navigate = body["endpoints"]["browser_navigate"]
        assert navigate["reason"] == "endpoint_disabled"
        assert navigate["rule"] == "default:opt-in:browser"


class TestSecrets:
    def test_env_get_hides_server_and_identity_secrets(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MY_PLAIN_NAME", "visible")
        monkeypatch.setenv("ABX_UPLOADER_CRED", "super-secret-1")
        policy = {
            "auth": {
                "tokens": [
                    {"id": "a", "token_env": "ABX_UPLOADER_CRED", "scopes": ["*"]},
                ]
            }
        }
        live: Live = live_server(policy=policy)
        _, body = live.get("/env", headers=hdr("super-secret-1"))
        assert body["variables"].get("MY_PLAIN_NAME") == "visible"
        assert "ABX_UPLOADER_CRED" not in body["variables"]
        assert "super-secret-1" not in json.dumps(body)

    def test_child_processes_do_not_inherit_token_env(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CRED_FOR_ADMIN", "child-leak-check")
        policy = {"auth": {"tokens": [{"id": "a", "token_env": "CRED_FOR_ADMIN", "scopes": ["*"]}]}}
        live: Live = live_server(policy=policy)
        status, body = live.post("/shell", {"command": "env"}, headers=hdr("child-leak-check"))
        assert status == 200 and "child-leak-check" not in body["stdout"]
        assert "PATH=" in body["stdout"]

    def test_env_set_refuses_secret_names_and_allow_list(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CRED_X", "tok-xxxxxxxx")
        policy = {
            "auth": {"tokens": [{"id": "a", "token_env": "CRED_X", "scopes": ["*"]}]},
            "endpoints": {"env_set": {"params": {"allow_vars": ["APP_*"]}}},
        }
        live: Live = live_server(policy=policy)
        h = hdr("tok-xxxxxxxx")
        assert live.post("/env", {"vars": {"APP_A": "1"}}, headers=h)[0] == 200
        status, body = live.post("/env", {"vars": {"OTHER": "1"}}, headers=h)
        assert status == 403 and body["code"] == "env_var_not_allowed"
        assert live.post("/env", {"vars": {"CRED_X": "1"}}, headers=h)[0] == 403
        monkeypatch.delenv("APP_A", raising=False)

    def test_unconfigured_server_does_not_scrub_env(
        self, live_server: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LEGACY_VISIBLE_VAR", "inherited")
        live: Live = live_server()
        _, body = live.post("/shell", {"command": "env"})
        assert "LEGACY_VISIBLE_VAR=inherited" in body["stdout"]
