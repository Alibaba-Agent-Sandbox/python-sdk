"""HTTP-level hardening: framing, duplicate params, method override, odd routes."""

from __future__ import annotations

import base64
import json
import socket
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._live import Live


def raw_exchange(port: int, request: bytes) -> tuple[int, bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(request)
        chunks: list[bytes] = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    blob = b"".join(chunks)
    status_line = blob.split(b"\r\n", 1)[0].decode("latin-1")
    parts = status_line.split(" ")
    return (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0), blob


def post_raw(port: int, path: str, headers: list[str], body: bytes = b"{}") -> tuple[int, bytes]:
    head = "\r\n".join([f"POST {path} HTTP/1.1", f"Host: 127.0.0.1:{port}", *headers, "", ""])
    return raw_exchange(port, head.encode() + body)


class TestContentLength:
    def test_non_numeric_rejected(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        status, _ = post_raw(live.port, "/files/mkdir", ["Content-Length: abc"])
        assert status == 400

    def test_negative_rejected(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        status, _ = post_raw(live.port, "/files/mkdir", ["Content-Length: -5"])
        assert status == 400

    def test_signed_plus_rejected(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        status, _ = post_raw(live.port, "/files/mkdir", ["Content-Length: +2"])
        assert status == 400

    def test_duplicate_conflicting_rejected(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        status, _ = post_raw(live.port, "/files/mkdir", ["Content-Length: 2", "Content-Length: 40"])
        assert status == 400

    def test_valid_still_works(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        body = json.dumps({"path": str(sandbox_tree / "newdir")}).encode()
        status, _ = post_raw(live.port, "/files/mkdir", [f"Content-Length: {len(body)}"], body)
        assert status == 200
        assert (sandbox_tree / "newdir").is_dir()


class TestPolicyModeFraming:
    def test_transfer_encoding_rejected_in_policy_mode(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server(policy={"preset": "default"})
        status, _ = post_raw(
            live.port,
            "/files/mkdir",
            ["Transfer-Encoding: chunked"],
            b"2\r\n{}\r\n0\r\n\r\n",
        )
        assert status == 400

    def test_duplicate_query_param_rejected_in_policy_mode(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server(policy={"preset": "default"})
        status, body = live.get("/files/stat?path=out/a.txt&path=secret/s.txt")
        assert status == 400
        assert "duplicate" in json.dumps(body).lower()

    def test_duplicate_query_param_rejected_without_a_policy(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server()
        target = sandbox_tree / "out" / "a.txt"
        status, body = live.get(f"/files/stat?path={target}&path={target}")
        assert status == 400
        assert "duplicate" in json.dumps(body).lower()


class TestMethodOverride:
    def test_override_header_ignored(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(policy={"preset": "read-only"})
        status, _, _ = live.request(
            "GET",
            "/files?path=out/a.txt",
            headers={"X-HTTP-Method-Override": "DELETE", "X-Method-Override": "DELETE"},
        )
        assert status in (404, 405)
        assert (sandbox_tree / "out" / "a.txt").exists()

    def test_override_query_ignored(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(policy={"preset": "read-only"})
        status, _, _ = live.request("POST", "/files/stat?_method=DELETE&path=out/a.txt", {})
        assert status in (404, 405)
        assert (sandbox_tree / "out" / "a.txt").exists()

    def test_denied_delete_stays_denied(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(policy={"preset": "read-only"})
        status, body, _ = live.request("DELETE", "/files", {"path": "out/a.txt"})
        assert status in (403, 404)
        assert (sandbox_tree / "out" / "a.txt").exists()
        assert isinstance(body, dict)

    def test_unsupported_methods(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server()
        for method in ("PATCH", "TRACE", "OPTIONS"):
            status, _, _ = live.request(method, "/health")
            assert status in (404, 405, 501), method


class TestRouteNormalisation:
    def test_encoded_slash_does_not_reach_other_route(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server(policy={"preset": "transfer-only"})
        status, _ = live.get("/files%2Fstat?path=out/a.txt")
        assert status == 404

    def test_double_slash_and_trailing_slash_do_not_bypass(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server(policy={"preset": "transfer-only"})
        for path in ("//files/stat?path=out/a.txt", "/files/stat/?path=out/a.txt"):
            status, _ = live.get(path)
            assert status in (404, 403), path

    def test_case_variants_are_not_routes(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(policy={"preset": "transfer-only"})
        status, _ = live.get("/FILES/stat?path=out/a.txt")
        assert status == 404

    def test_endpoint_disabled_hidden_as_404(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(policy={"preset": "transfer-only"})
        status, body = live.get("/files/stat?path=out/a.txt")
        assert status == 404
        assert body["code"] == "endpoint_disabled"


class TestBodyLimit:
    def test_lying_content_length_cannot_exceed_cap(
        self, live_server: Any, sandbox_tree: Any
    ) -> None:
        live: Live = live_server(
            policy={
                "endpoints": {"upload": {"limits": {"max_request_bytes": 1000}}},
            }
        )
        payload = json.dumps(
            {"path": "big.bin", "content_base64": base64.b64encode(b"x" * 5000).decode()}
        )
        status, _ = post_raw(
            live.port, "/upload", [f"Content-Length: {len(payload)}"], payload.encode()
        )
        assert status == 413
        assert not (sandbox_tree / "big.bin").exists()

    def test_under_cap_is_accepted(self, live_server: Any, sandbox_tree: Any) -> None:
        live: Live = live_server(
            policy={"endpoints": {"upload": {"limits": {"max_request_bytes": 100000}}}}
        )
        status, _ = live.post(
            "/upload",
            {
                "path": str(sandbox_tree / "ok.bin"),
                "content_base64": base64.b64encode(b"hello").decode(),
            },
        )
        assert status == 200
