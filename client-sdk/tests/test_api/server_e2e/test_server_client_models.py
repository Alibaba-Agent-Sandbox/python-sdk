"""Pure unit tests: error mapping, models, ServerCapabilities, URL derivation, legacy servers."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.api.server_capabilities import ENDPOINT_GROUPS, ServerCapabilities
from easy_sandbox.api.server_client import ServerClient, error_from_response
from easy_sandbox.models import errors
from easy_sandbox.models.server import (
    ProcessOutput,
    ProcessOutputEvent,
    ServerFileEntry,
    ServerWatchEvent,
    TransferResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            (
                401,
                {"error": "no", "type": "AuthError", "code": "unauthorized"},
                errors.ServerAuthError,
            ),
            (
                403,
                {"error": "x", "type": "PolicyDenied", "code": "missing_scope", "scope": "a:b"},
                errors.PolicyDeniedError,
            ),
            (
                403,
                {"error": "x", "type": "PolicyDenied", "code": "path_denied"},
                errors.FilePolicyDeniedError,
            ),
            (
                403,
                {"error": "x", "type": "PolicyDenied", "code": "read_only"},
                errors.FilePolicyDeniedError,
            ),
            (
                409,
                {"error": "x", "type": "FileExistsError", "code": "file_exists"},
                errors.FilePolicyDeniedError,
            ),
            (
                404,
                {
                    "error": "x",
                    "type": "ValueError",
                    "code": "endpoint_disabled",
                    "endpoint": "shell",
                },
                errors.EndpointNotAvailableError,
            ),
            (
                404,
                {"error": "Built-in route 'git_diff' is disabled", "type": "ValueError"},
                errors.EndpointNotAvailableError,
            ),
            (404, {"error": "nf", "type": "FileNotFoundError"}, errors.FileNotFoundError_),
            (
                413,
                {"error": "big", "type": "ValueError", "code": "payload_too_large", "limit": 5},
                errors.PayloadTooLargeError,
            ),
            (
                429,
                {"error": "slow", "type": "RateLimited", "code": "rate_limited", "retry_after": 2},
                errors.RateLimitedError,
            ),
            (500, {"error": "t", "type": "TimeoutError"}, errors.CommandTimeoutError),
            (400, {"error": "bad", "type": "ValueError"}, errors.ServerAPIError),
            (404, {"error": "Not found: /x", "type": "ValueError"}, errors.ServerAPIError),
            (
                429,
                {"error": "Process limit reached", "type": "ResourceError"},
                errors.ServerAPIError,
            ),
            (502, "<html>bad gateway</html>", errors.ServerAPIError),
        ],
    )
    def test_mapping(self, status: int, body: Any, expected: type[Exception]) -> None:
        err = error_from_response(status, body, endpoint="ep")
        assert type(err) is expected
        assert str(err)

    def test_attributes_are_populated(self) -> None:
        err = error_from_response(
            403,
            {
                "error": "m",
                "type": "PolicyDenied",
                "code": "missing_scope",
                "scope": "files:write",
                "endpoint": "upload",
            },
        )
        assert isinstance(err, errors.PolicyDeniedError)
        assert (err.status_code, err.error_type, err.error_code) == (
            403,
            "PolicyDenied",
            "missing_scope",
        )
        assert (err.endpoint, err.scope, err.code) == ("upload", "files:write", "E9002")

    def test_legacy_disabled_message_names_the_endpoint(self) -> None:
        err = error_from_response(404, {"error": "Built-in route 'git_diff' is disabled"})
        assert isinstance(err, errors.EndpointNotAvailableError)
        assert err.endpoint == "git_diff" and err.capability == "git_diff"

    def test_retry_after_from_header_fallback(self) -> None:
        err = error_from_response(
            429, {"error": "x", "type": "RateLimited"}, headers={"retry-after": "7"}
        )
        assert isinstance(err, errors.RateLimitedError) and err.retry_after == 7.0

    def test_hierarchy_keeps_existing_except_clauses_working(self) -> None:
        assert issubclass(errors.ServerAuthError, errors.AuthenticationError)
        assert issubclass(errors.FilePolicyDeniedError, errors.PermissionDeniedError)
        assert issubclass(errors.FilePolicyDeniedError, errors.FileOperationError)
        assert issubclass(errors.EndpointNotAvailableError, errors.CapabilityNotSupportedError)
        for cls in (
            errors.ServerAuthError,
            errors.PolicyDeniedError,
            errors.EndpointNotAvailableError,
            errors.PayloadTooLargeError,
            errors.RateLimitedError,
        ):
            assert issubclass(cls, errors.ServerAPIError) and issubclass(cls, errors.SandboxError)

    def test_codes_are_unique_and_in_e9xxx(self) -> None:
        codes = {
            errors.ServerAPIError.code,
            errors.ServerAuthError.code,
            errors.PolicyDeniedError.code,
            errors.EndpointNotAvailableError.code,
            errors.PayloadTooLargeError.code,
            errors.RateLimitedError.code,
        }
        assert len(codes) == 6 and all(c.startswith("E9") for c in codes)

    def test_to_dict_and_str(self) -> None:
        err = errors.RateLimitedError("slow down", retry_after=3, status_code=429)
        assert err.to_dict()["code"] == "E9005"
        assert "slow down" in str(err)


class TestModels:
    def test_unknown_fields_are_kept(self) -> None:
        entry = ServerFileEntry.model_validate({"name": "a", "type": "directory", "future": 1})
        assert entry.is_dir and entry.model_extra == {"future": 1}

    def test_transfer_result_alias(self) -> None:
        assert TransferResult.model_validate({"path": "p", "bytes": 4}).size == 4

    def test_process_output_helpers(self) -> None:
        out = ProcessOutput(
            pid=1,
            events=[
                ProcessOutputEvent(seq=0, stream="stdout", data="a"),
                ProcessOutputEvent(seq=1, stream="stderr", data="e"),
                ProcessOutputEvent(seq=2, stream="stdout", data="b"),
            ],
            next=3,
        )
        assert (out.stdout, out.stderr) == ("ab", "e")

    def test_watch_event_extends_the_envd_event(self) -> None:
        ev = ServerWatchEvent.model_validate({"type": "created", "path": "/x", "is_dir": True})
        assert ev.is_dir and ev.type.value == "created"


class TestServerCapabilities:
    DOC: dict[str, Any] = {
        "api_version": 2,
        "server_version": "0.3.0",
        "groups": {"file_ops": True, "process": False},
        "identity": {"id": "ci", "scopes": ["files:read"]},
        "policy": {"preset": "read-only", "revision": "abc", "configured": True},
        "warnings": ["w"],
        "endpoints": {
            "files_list": {
                "method": "GET",
                "path": "/files/list",
                "group": "file_ops",
                "enabled": True,
                "allowed": True,
                "scopes": ["files:read"],
                "limits": {"max_entries": 50},
                "paths": {"allow": ["/srv"], "read_only": True, "deny_count": 1},
            },
            "upload": {
                "enabled": True,
                "allowed": False,
                "reason": "missing_scope",
                "scopes": ["files:write"],
                "params": {"overwrite": False},
            },
            "shell": {"enabled": False, "allowed": False, "reason": "endpoint_disabled"},
        },
    }

    def test_queries(self) -> None:
        caps = ServerCapabilities(self.DOC)
        assert caps.legacy is False and caps.preset == "read-only" and caps.revision == "abc"
        assert caps.can("files_list") and not caps.can("upload") and not caps.can("shell")
        assert not caps.can("never_heard_of_it")
        assert caps.limit("files_list", "max_entries") == 50
        assert caps.limit("files_list", "nope", 7) == 7 and caps.limit("zzz", "x") is None
        assert caps.param("upload", "overwrite") is False
        assert caps.paths("files_list").read_only is True  # type: ignore[union-attr]
        assert caps.endpoints_for("files:read") == ["files_list"]
        assert caps.available() == ["files_list"]
        assert (
            caps.denial("upload") == "missing_scope" and caps.denial("shell") == "endpoint_disabled"
        )
        assert caps.warnings == ["w"] and caps.as_dict() == self.DOC
        assert "read-only" in repr(caps)

    def test_require(self) -> None:
        caps = ServerCapabilities(self.DOC)
        assert caps.require("files_list") is not None
        with pytest.raises(errors.PolicyDeniedError) as scope_err:
            caps.require("upload")
        assert scope_err.value.scope == "files:write"
        with pytest.raises(errors.EndpointNotAvailableError):
            caps.require("shell")
        with pytest.raises(errors.EndpointNotAvailableError):
            caps.require("brand_new_endpoint")

    def test_legacy_document_gates_by_group_only(self) -> None:
        caps = ServerCapabilities(
            {"groups": {"file_ops": True, "process": False, "dev_tools": False}}
        )
        assert caps.legacy is True
        assert caps.can("files_list") and caps.can("upload")
        assert not caps.can("shell") and not caps.can("process_start") and not caps.can("code_run")
        assert caps.can("something_unknown") is True
        assert caps.limit("files_list", "max_entries") is None
        assert caps.paths("files_list") is None and caps.available() == []
        assert "legacy=True" in repr(caps)
        with pytest.raises(errors.EndpointNotAvailableError):
            caps.require("shell")

    def test_empty_document_uses_default_groups(self) -> None:
        caps = ServerCapabilities({})
        assert caps.legacy and caps.can("files_list") and not caps.can("code_run")

    async def test_check_path_needs_a_discovering_server(self) -> None:
        caps = ServerCapabilities({"groups": {}})
        with pytest.raises(errors.EndpointNotAvailableError):
            await caps.check_path("files_list", "/x")
        unbound = ServerCapabilities(self.DOC)
        with pytest.raises(RuntimeError):
            await unbound.check_path("files_list", "/x")

    def test_endpoint_groups_cover_known_client_endpoints(self) -> None:
        assert set(ServerClient.ENDPOINT_METHODS) - set(ENDPOINT_GROUPS) == set()


class TestClientConfiguration:
    def test_pty_url_derivation(self) -> None:
        assert ServerClient("http://10.0.0.5:9000").pty_url == "ws://10.0.0.5:9001"
        assert (
            ServerClient("https://9000-sbx-abc.cn-hangzhou.e2b.fc.aliyuncs.com").pty_url
            == "wss://9001-sbx-abc.cn-hangzhou.e2b.fc.aliyuncs.com"
        )
        assert (
            ServerClient("http://h:9000", pty_url="https://pty.example/x/").pty_url
            == "wss://pty.example/x"
        )

    def test_auth_headers_merge_gateway_and_bearer(self) -> None:
        client = ServerClient("http://h:9000", token="t", headers={"X-Access-Token": "gw"})
        assert client.auth_headers() == {"X-Access-Token": "gw", "Authorization": "Bearer t"}
        assert ServerClient("http://h").auth_headers() == {}
        assert client.with_token(None).auth_headers() == {"X-Access-Token": "gw"}

    def test_repr_has_no_token(self) -> None:
        assert "secret" not in repr(ServerClient("http://h:9000", token="secret"))

    async def test_connection_failure_is_a_typed_connection_error(self) -> None:
        client = ServerClient("http://127.0.0.1:1", timeout=1)
        with pytest.raises(errors.ConnectionError_):
            await client.system.info()
        await client.aclose()

    async def test_non_json_body_is_a_protocol_error(self, plain_server: str) -> None:
        client = ServerClient(plain_server, timeout=5)
        with pytest.raises(errors.ServerAPIError) as exc:
            await client.system.info()
        assert exc.value.error_type == "ProtocolError"
        await client.aclose()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/capabilities":
            body = json.dumps(
                {"groups": {"core": True, "file_ops": True, "process": False, "dev_tools": False}}
            ).encode()
            ctype = "application/json"
        elif self.path == "/health":
            body, ctype = b'{"status": "ok"}', "application/json"
        else:
            body, ctype = b"<html>not the sandbox server</html>", "text/html"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        return


@pytest.fixture
def plain_server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


class TestLegacyServerStub:
    """A pre-policy server: ``/capabilities`` lists groups only."""

    async def test_discover_marks_legacy_and_gates_by_group(self, plain_server: str) -> None:
        client = ServerClient(plain_server, timeout=5)
        caps = await client.discover()
        assert caps.legacy and caps.can("files_list") and not caps.can("shell")
        with pytest.raises(errors.EndpointNotAvailableError):
            await client.process.shell("echo hi")
        assert await client.health() is True
        await client.aclose()
