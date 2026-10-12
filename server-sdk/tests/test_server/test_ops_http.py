"""``POST /ops/{id}`` and ``GET /ops`` on a real server; legacy routes stay on the v1 dispatcher."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import socket
from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.server.router import CapabilityGroup
from easy_sandbox.server.types import ServerResponse

if TYPE_CHECKING:
    from pathlib import Path

    from ._live import Live

READER = "reader-token-123456"
ADMIN = "admin-token-abcdef"
TOKEN = "legacy-secret-token"


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_policy(**extra: Any) -> dict[str, Any]:
    policy: dict[str, Any] = {
        "auth": {
            "tokens": [
                {"id": "reader", "token_sha256": sha(READER), "scopes": ["files:read"]},
                {"id": "admin", "token_sha256": sha(ADMIN), "scopes": ["*"]},
            ]
        }
    }
    policy.update(extra)
    return policy


def hdr(token: str, bearer: bool = False) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if bearer else {"X-Access-Token": token}


def op(live: Live, op_id: str, args: Any = None, **kw: Any) -> tuple[int, Any, dict[str, str]]:
    return live.request("POST", f"/ops/{op_id}", {} if args is None else args, **kw)


def same_as_legacy(
    live: Live,
    op_id: str,
    args: dict[str, Any],
    method: str,
    path: str,
    body: Any = None,
    **kw: Any,
) -> tuple[int, Any]:
    legacy_status, legacy_body, _ = live.request(method, path, body, **kw)
    status, resp, _ = op(live, op_id, args, **kw)
    assert (status, resp) == (legacy_status, legacy_body), (op_id, resp, legacy_body)
    return status, resp


class TestParityWithLegacyRoutes:
    def test_health(self, live_server: Any) -> None:
        live: Live = live_server()
        assert same_as_legacy(live, "core.health", {}, "GET", "/health") == (200, {"status": "ok"})

    def test_files_roundtrip_and_errors(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server()
        a = str(sandbox_tree / "out" / "a.txt")
        out = str(sandbox_tree / "out")
        assert (
            same_as_legacy(live, "files.list", {"path": out}, "GET", f"/files/list?path={out}")[0]
            == 200
        )
        assert (
            same_as_legacy(live, "files.stat", {"path": a}, "GET", f"/files/stat?path={a}")[0]
            == 200
        )
        status, body = same_as_legacy(
            live, "files.download", {"path": a}, "GET", f"/download?path={a}"
        )
        assert status == 200 and base64.b64decode(body["content_base64"]) == b"alpha"
        assert same_as_legacy(live, "files.download", {}, "GET", "/download")[0] == 400
        outside = str(sandbox_tree.parent / "outside.txt")
        status, _ = same_as_legacy(
            live, "files.download", {"path": outside}, "GET", f"/download?path={outside}"
        )
        assert status == 400

    def test_upload_mkdir_move_delete(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server()
        target = sandbox_tree / "out" / "up.txt"
        content = base64.b64encode(b"hello").decode()
        status, body, _ = op(live, "files.upload", {"path": str(target), "content_base64": content})
        assert status == 200 and body == {"path": str(target), "bytes": 5}
        assert target.read_bytes() == b"hello"
        assert op(live, "files.mkdir", {"path": str(sandbox_tree / "out" / "d")})[0] == 200
        moved = sandbox_tree / "out" / "d" / "moved.txt"
        status, _, _ = op(live, "files.move", {"source": str(target), "destination": str(moved)})
        assert status == 200 and moved.exists() and not target.exists()
        status, _, _ = op(live, "files.delete", {"path": str(moved)})
        assert status == 200 and not moved.exists()
        same_as_legacy(live, "files.delete", {}, "DELETE", "/files")

    def test_commands_run_and_stream(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body = same_as_legacy(
            live, "commands.run", {"command": "echo hi"}, "POST", "/shell", {"command": "echo hi"}
        )
        assert status == 200 and body["stdout"] == "hi\n"
        assert same_as_legacy(live, "commands.run", {}, "POST", "/shell", {})[0] == 400
        legacy = live.request("POST", "/shell/stream", {"command": "echo hi"})
        via_ops = op(live, "commands.stream", {"command": "echo hi"})
        assert legacy[0] == via_ops[0] == 200
        assert legacy[1] == via_ops[1] and b"event: exit" in via_ops[1]
        assert via_ops[2]["content-type"] == "text/event-stream"

    def test_path_parameters_and_not_found(self, live_server: Any) -> None:
        live: Live = live_server()
        assert (
            same_as_legacy(live, "process.get", {"pid": "999999"}, "GET", "/process/999999")[0]
            == 404
        )
        status, body, _ = op(live, "process.get", {})
        assert status == 400 and body["code"] == "args.missing"
        assert op(live, "process.get", {"pid": ["x"]})[1]["code"] == "args.type"

    def test_custom_commands(self, live_server: Any) -> None:
        from easy_sandbox.server.registry import CommandRegistry

        commands = CommandRegistry()

        @commands.command("Hello-World.v2")
        def hello(name: str = "x") -> str:
            return f"hi {name}"

        live: Live = live_server(registry=commands)
        status, body = same_as_legacy(
            live,
            "custom.hello_world_v2",
            {"name": "bob"},
            "POST",
            "/commands/Hello-World.v2",
            {"name": "bob"},
        )
        assert (status, body) == (200, {"result": "hi bob"})
        same_as_legacy(live, "custom.list", {}, "GET", "/commands")

    def test_capabilities_stay_v1_shaped(self, live_server: Any) -> None:
        live: Live = live_server()
        status, via_ops, _ = op(live, "core.capabilities")
        legacy = live.get("/capabilities")
        assert status == legacy[0] == 200 and via_ops == legacy[1]
        assert "groups" in via_ops and "ops" not in via_ops

    def test_ws_only_operation_is_not_callable_over_http(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body, _ = op(live, "terminal.connect")
        assert status == 400 and body["code"] == "op.not_callable"

    def test_legacy_aliases_resolve(self, live_server: Any) -> None:
        live: Live = live_server()
        assert op(live, "shell", {"command": "echo a"})[1]["stdout"] == "a\n"


class TestMounting:
    def test_unknown_and_disabled_share_one_404_shape(self, live_server: Any) -> None:
        live: Live = live_server()
        s1, unknown, _ = op(live, "nothing.here")
        s2, disabled, _ = op(live, "devtools.git.status", {"path": "/tmp"})
        assert s1 == s2 == 404
        assert unknown["code"] == disabled["code"] == "op.not_enabled"
        assert unknown["error"].replace("nothing.here", "X") == disabled["error"].replace(
            "devtools.git.status", "X"
        )
        assert set(unknown) == set(disabled)
        legacy_status, legacy_body = live.get("/git/status?path=/tmp")
        assert legacy_status == 404 and legacy_body["error"].endswith("is disabled")

    def test_enabled_group_mounts_its_operations(self, live_server: Any) -> None:
        live: Live = live_server()
        live.server.route_table.enable_group(CapabilityGroup.DEV_TOOLS)
        assert op(live, "devtools.git.status", {"path": "/tmp"})[0] != 404

    def test_unknown_native_ids_are_never_mounted(self, live_server: Any) -> None:
        live: Live = live_server()
        for op_id in ("core.reload", "x", "files", "Files.List", "files.list.more"):
            status, body, _ = op(live, op_id)
            assert status == 404 and body["code"] == "op.not_enabled", op_id

    def test_user_registered_v1_route_wins_over_ops_hook(self, live_server: Any) -> None:
        from easy_sandbox.server.router import RouteTable

        table = RouteTable()
        table.register(
            "POST",
            "/ops/custom",
            lambda r: ServerResponse.ok({"mine": True}),
            group=CapabilityGroup.CORE,
            name="mine",
        )
        live: Live = live_server(route_table=table)
        assert live.request("POST", "/ops/custom", {})[:2] == (200, {"mine": True})

    def test_other_shapes_keep_the_v1_404(self, live_server: Any) -> None:
        live: Live = live_server()
        for method, path in (("GET", "/ops/files.list"), ("POST", "/ops"), ("POST", "/ops/a/b")):
            status, body, _ = live.request(method, path, {} if method == "POST" else None)
            assert status == 404 and body == {"error": f"Not found: {path}", "type": "ValueError"}


class TestRequestBody:
    def test_invalid_json_and_non_objects(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body, _ = live.request("POST", "/ops/commands.run", raw_body=b"{nope")
        assert status == 400 and body["type"] == "ValueError"
        status, body, _ = live.request("POST", "/ops/commands.run", raw_body=b"[1]")
        assert status == 400 and body["code"] == "args.invalid"

    def test_empty_body_is_empty_arguments(self, live_server: Any) -> None:
        live: Live = live_server()
        status, body, _ = live.request("POST", "/ops/core.health")
        assert (status, body) == (200, {"status": "ok"})

    def test_unknown_arguments_are_ignored_on_legacy_bindings(self, live_server: Any) -> None:
        live: Live = live_server()
        assert op(live, "commands.run", {"command": "echo a", "bogus": 1})[0] == 200

    def test_transfer_encoding_is_refused(self, live_server: Any) -> None:
        live: Live = live_server()
        raw = (
            b"POST /ops/core.health HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n"
            b"Connection: close\r\n\r\n0\r\n\r\n"
        )
        with socket.create_connection(("127.0.0.1", live.port), timeout=5) as s:
            s.sendall(raw)
            data = b""
            while chunk := s.recv(4096):
                data += chunk
        assert b" 400 " in data.split(b"\r\n")[0] and b"unsupported_encoding" in data


class TestDiscovery:
    def test_get_ops_lists_what_is_mounted(self, live_server: Any) -> None:
        live: Live = live_server()
        status, doc, _ = live.request("GET", "/ops")
        assert status == 200
        assert doc["api"] == "easy-sandbox/2" and doc["catalog_version"] == 1
        ids = [e["id"] for e in doc["ops"]]
        assert doc["count"] == len(ids) and ids == sorted(ids)
        assert "files.list" in ids and "core.describe" in ids and "commands.run" in ids
        assert not any(i.startswith(("browser.", "devtools.", "agents.")) for i in ids)
        files_list = next(e for e in doc["ops"] if e["id"] == "files.list")
        assert files_list["effects"] == ["read"] and files_list["rpc"] == "/ops/files.list"
        assert files_list["http"] == [{"method": "GET", "path": "/files/list", "legacy": True}]
        assert doc["policy"] == {"configured": False, "preset": None}

    def test_core_describe_filters(self, live_server: Any) -> None:
        live: Live = live_server()
        _, doc, _ = op(live, "core.describe", {"namespace": "files"})
        assert {e["id"].split(".")[0] for e in doc["ops"]} == {"files"}
        _, doc, _ = op(live, "core.describe", {"ids": ["files.list", "commands.*", "nope.x"]})
        assert [e["id"] for e in doc["ops"]] == ["commands.run", "commands.stream", "files.list"]
        assert op(live, "core.describe", {"ids": "files.list"})[1]["code"] == "args.type"
        assert op(live, "core.describe", {"all": 1})[1]["code"] == "args.unknown"

    def test_get_ops_query_arguments(self, live_server: Any) -> None:
        live: Live = live_server()
        _, doc, _ = live.request("GET", "/ops?namespace=system&ids=system.info&ids=files.list")
        assert [e["id"] for e in doc["ops"]] == ["system.info"]

    def test_hidden_commands_are_not_listed(self, live_server: Any) -> None:
        from easy_sandbox.server.registry import CommandRegistry

        commands = CommandRegistry()
        commands.register("shown", lambda: "a")
        commands.register("secret", lambda: "b", hidden=True)
        live: Live = live_server(registry=commands)
        ids = [e["id"] for e in live.request("GET", "/ops")[1]["ops"]]
        assert "custom.shown" in ids and "custom.secret" not in ids
        assert op(live, "custom.secret")[1] == {"result": "b"}


class TestLegacyAuthentication:
    @pytest.fixture
    def secured(self, live_server: Any, monkeypatch: pytest.MonkeyPatch) -> Live:
        monkeypatch.setenv("EBX_SERVER_TOKEN", TOKEN)
        live: Live = live_server()
        return live

    def test_401_precedes_404_and_health_is_anonymous(self, secured: Live) -> None:
        for op_id in ("files.list", "nothing.here", "devtools.git.status"):
            status, body, _ = op(secured, op_id)
            assert status == 401 and body["code"] == "unauthorized", op_id
        assert secured.request("GET", "/ops")[0] == 401
        assert op(secured, "core.health")[:2] == (200, {"status": "ok"})

    def test_valid_credentials(self, secured: Live) -> None:
        assert op(secured, "commands.run", {"command": "echo a"}, headers=hdr(TOKEN))[0] == 200
        assert (
            op(secured, "commands.run", {"command": "echo a"}, headers=hdr(TOKEN, True))[0] == 200
        )
        assert secured.request("GET", "/ops", headers=hdr(TOKEN))[0] == 200
        assert op(secured, "nothing.here", headers=hdr(TOKEN))[0] == 404

    def test_wrong_and_conflicting_credentials(self, secured: Live) -> None:
        assert op(secured, "files.list", headers=hdr("nope"))[0] == 401
        both = {"X-Access-Token": TOKEN, "Authorization": "Bearer other"}
        assert op(secured, "files.list", headers=both)[0] == 401
        same = {"X-Access-Token": TOKEN, "Authorization": f"Bearer {TOKEN}"}
        assert op(secured, "commands.run", {"command": "echo a"}, headers=same)[0] == 200

    def test_legacy_routes_still_use_their_own_header_rules(self, secured: Live) -> None:
        assert secured.get("/commands")[0] == 401
        assert secured.get("/commands", headers=hdr(TOKEN))[0] == 200
        assert secured.get("/commands", headers=hdr(TOKEN, True))[0] == 401


class TestOneDecisionSource:
    """The v1 dispatcher and ``/ops`` consult the same ``PolicyEngine``."""

    def test_missing_scope_is_the_same_403(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        legacy = live.request("POST", "/shell", {"command": "echo a"}, headers=hdr(READER))
        via_ops = op(live, "commands.run", {"command": "echo a"}, headers=hdr(READER))
        assert legacy[0] == via_ops[0] == 403
        assert legacy[1] == via_ops[1] and via_ops[1]["code"] == "missing_scope"
        assert op(live, "commands.run", {"command": "echo a"}, headers=hdr(ADMIN))[0] == 200

    def test_disabled_endpoint_and_group_are_not_enabled(self, live_server: Any) -> None:
        live: Live = live_server(
            policy=tokens_policy(endpoints={"shell": {"enabled": False}}, groups={"system": False})
        )
        assert live.request("POST", "/shell", {"command": "x"}, headers=hdr(ADMIN))[0] == 404
        status, body, _ = op(live, "commands.run", {"command": "x"}, headers=hdr(ADMIN))
        assert status == 404 and body["code"] == "op.not_enabled"
        assert live.get("/system/info", headers=hdr(ADMIN))[0] == 404
        assert op(live, "system.info", headers=hdr(ADMIN))[0] == 404

    def test_rate_limit_bucket_is_shared(self, live_server: Any) -> None:
        policy = tokens_policy(endpoints={"system_info": {"limits": {"rate_per_minute": 2}}})
        live: Live = live_server(policy=policy)
        assert op(live, "system.info", headers=hdr(ADMIN))[0] == 200
        assert live.get("/system/info", headers=hdr(ADMIN))[0] == 200
        status, body, headers = op(live, "system.info", headers=hdr(ADMIN))
        assert status == 429 and body["code"] == "rate_limited"
        assert int(headers["retry-after"]) >= 1
        legacy_status, _, legacy_headers = live.request("GET", "/system/info", headers=hdr(ADMIN))
        assert legacy_status == 429 and "retry-after" in legacy_headers

    def test_path_rules_apply_through_ops(self, live_server: Any, sandbox_tree: Path) -> None:
        out = str(sandbox_tree / "out")
        live: Live = live_server(
            policy=tokens_policy(endpoints={"files_stat": {"paths": {"allow": [out]}}})
        )
        ok = str(sandbox_tree / "out" / "a.txt")
        bad = str(sandbox_tree / "secret" / "s.txt")
        assert (
            same_as_legacy(
                live,
                "files.stat",
                {"path": ok},
                "GET",
                f"/files/stat?path={ok}",
                headers=hdr(ADMIN),
            )[0]
            == 200
        )
        status, body = same_as_legacy(
            live, "files.stat", {"path": bad}, "GET", f"/files/stat?path={bad}", headers=hdr(ADMIN)
        )
        assert status == 403 and body["code"] == "path_not_allowed"

    def test_upload_limit_from_the_rule_applies(self, live_server: Any, sandbox_tree: Path) -> None:
        live: Live = live_server(
            policy=tokens_policy(endpoints={"upload": {"limits": {"max_bytes": 4}}})
        )
        target = str(sandbox_tree / "out" / "big.txt")
        content = base64.b64encode(b"0123456789").decode()
        status, body, _ = op(
            live, "files.upload", {"path": target, "content_base64": content}, headers=hdr(ADMIN)
        )
        assert status == 413 and body["code"] == "payload_too_large"

    def test_discovery_is_principal_filtered_without_an_oracle(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        reader = {e["id"] for e in live.request("GET", "/ops", headers=hdr(READER))[1]["ops"]}
        admin = {e["id"] for e in live.request("GET", "/ops", headers=hdr(ADMIN))[1]["ops"]}
        assert "files.list" in reader and "commands.run" not in reader
        assert reader < admin and "commands.run" in admin
        status, doc, _ = live.request("GET", "/ops", headers=hdr(READER))
        assert doc["principal"]["id"] == "reader" and doc["policy"]["configured"] is True
        listed = next(e for e in doc["ops"] if e["id"] == "files.list")
        assert listed["effective"]["scopes"] == ["files:read"]

    def test_denials_are_audited_with_the_endpoint_name(
        self, live_server: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        live: Live = live_server(policy=tokens_policy())
        with caplog.at_level(logging.INFO, logger="easy_sandbox.server.audit"):
            op(live, "commands.run", {"command": "echo a"}, headers=hdr(READER))
            op(live, "nothing.here", headers=hdr(READER))
            op(live, "files.list", {"path": "/"}, headers=hdr("bad-token"))
        events = [json.loads(r.message) for r in caplog.records if r.name.endswith("audit")]
        by_endpoint = {e["endpoint"]: e for e in events}
        assert by_endpoint["shell"]["code"] == "missing_scope"
        assert (
            by_endpoint["shell"]["identity"] == "reader" and by_endpoint["shell"]["status"] == 403
        )
        assert by_endpoint["nothing.here"]["code"] == "op.not_enabled"
        assert by_endpoint["nothing.here"]["status"] == 404
        assert any(e["status"] == 401 and e["identity"] is None for e in events)

    def test_duplicate_credential_headers_are_ambiguous(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        raw = (
            f"POST /ops/files.list HTTP/1.1\r\nHost: x\r\nX-Access-Token: {READER}\r\n"
            f"X-Access-Token: {ADMIN}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        ).encode()
        with socket.create_connection(("127.0.0.1", live.port), timeout=5) as s:
            s.sendall(raw)
            data = b""
            while chunk := s.recv(4096):
                data += chunk
        assert b" 400 " in data.split(b"\r\n")[0] and b"ambiguous_credentials" in data

    def test_bearer_works_on_ops_in_policy_mode(self, live_server: Any) -> None:
        live: Live = live_server(policy=tokens_policy())
        assert op(live, "files.list", {"path": "/nonexistent"}, headers=hdr(READER, True))[0] != 401
