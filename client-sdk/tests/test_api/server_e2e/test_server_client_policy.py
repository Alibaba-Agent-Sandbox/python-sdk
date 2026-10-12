"""Typed errors, discovery and fail-fast behaviour against a policy-configured real server."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import pytest

from easy_sandbox.api.server_client import ServerClient
from easy_sandbox.models.errors import (
    AuthenticationError,
    CapabilityNotSupportedError,
    EndpointNotAvailableError,
    FileNotFoundError_,
    FilePolicyDeniedError,
    PayloadTooLargeError,
    PermissionDeniedError,
    PolicyDeniedError,
    RateLimitedError,
    ServerAPIError,
    ServerAuthError,
)

if TYPE_CHECKING:
    from pathlib import Path


def sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


READER = "reader-token-123456"
WRITER = "writer-token-654321"
TOKENS = {
    "auth": {
        "tokens": [
            {"id": "reader", "token_sha256": sha(READER), "scopes": ["files:read"]},
            {"id": "writer", "token_sha256": sha(WRITER), "scopes": ["files:write", "files:read"]},
        ]
    }
}


class TestTransferOnly:
    """The headline scenario: expose only upload and download, limited to one directory."""

    @pytest.fixture
    def client(self, server_factory: Any, tree: Path) -> ServerClient:  # noqa: F811
        _live, client = server_factory(
            policy={
                "preset": "transfer-only",
                "endpoints": {
                    "upload": {"paths": {"allow": [str(tree / "out")]}},
                    "download": {"paths": {"allow": [str(tree / "out")]}},
                },
            }
        )
        return client

    async def test_discovery_lists_exactly_the_transfer_endpoints(
        self, client: ServerClient
    ) -> None:
        caps = await client.discover()
        assert caps.preset == "transfer-only"
        assert {"upload", "download"} <= set(caps.available())
        assert not caps.can("shell") and not caps.can("files_list")
        assert caps.paths("upload") is not None
        assert caps.paths("upload").allow  # type: ignore[union-attr]

    async def test_allowed_path_roundtrip_with_and_without_discovery(
        self, client: ServerClient, tree: Path
    ) -> None:
        target = str(tree / "out" / "t.bin")
        await client.files.upload_legacy(target, b"payload")
        assert await client.files.download_legacy(target) == b"payload"
        await client.discover()
        assert await client.files.download_legacy(target) == b"payload"

    async def test_disabled_endpoint_server_answer_is_typed(self, client: ServerClient) -> None:
        with pytest.raises(EndpointNotAvailableError) as exc:
            await client.process.shell("echo hi")
        err = exc.value
        assert isinstance(err, CapabilityNotSupportedError) and isinstance(err, ServerAPIError)
        assert err.endpoint == "shell" and err.status_code == 404
        assert err.error_code == "endpoint_disabled" and err.code == "E9003"

    async def test_disabled_endpoint_fails_fast_after_discovery(
        self, client: ServerClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await client.discover()
        calls: list[Any] = []

        async def boom(*a: Any, **k: Any) -> Any:
            calls.append(a)
            raise AssertionError("no network round trip expected")

        monkeypatch.setattr(
            client, "_client", lambda: type("C", (), {"request": boom, "stream": boom})()
        )
        with pytest.raises(EndpointNotAvailableError):
            await client.process.shell("echo hi")
        with pytest.raises(EndpointNotAvailableError):
            await client.files.list("/")
        assert calls == []

    async def test_path_outside_allow_list_is_file_policy_denied(
        self, client: ServerClient, tree: Path
    ) -> None:
        with pytest.raises(FilePolicyDeniedError) as exc:
            await client.files.download_legacy(str(tree / "secret" / "s.txt"))
        err = exc.value
        assert isinstance(err, PermissionDeniedError) and isinstance(err, PolicyDeniedError)
        assert err.status_code == 403 and err.error_code == "path_not_allowed"
        assert err.endpoint == "download"

    async def test_traversal_and_outside_paths_are_denied(
        self, client: ServerClient, tree: Path
    ) -> None:
        for path in (
            str(tree / "out" / ".." / "secret" / "s.txt"),
            str(tree.parent / "outside.txt"),
            "/etc/passwd",
            str(tree / "out" / "%2e%2e" / "secret" / "s.txt"),
        ):
            with pytest.raises((FilePolicyDeniedError, FileNotFoundError_)):
                await client.files.download_legacy(path)

    async def test_server_check_matches_actual_decision(
        self, client: ServerClient, tree: Path
    ) -> None:
        caps = await client.discover()
        allowed = await caps.check_path("download", str(tree / "out" / "a.txt"), "read")
        denied = await caps.check_path("download", str(tree / "secret" / "s.txt"), "read")
        assert allowed.allowed is True
        assert denied.allowed is False and denied.code == "path_not_allowed"


class TestLimitsAndLimitsPrecheck:
    async def test_server_enforces_max_bytes_and_client_prechecks(
        self, server_factory: Any, tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _live, client = server_factory(
            policy={"endpoints": {"files_upload_stream": {"limits": {"max_bytes": 100}}}}
        )
        target = str(tree / "out" / "big.bin")
        with pytest.raises(PayloadTooLargeError) as server_side:
            await client.files.upload(target, b"x" * 500)
        assert server_side.value.status_code == 413 and server_side.value.limit == 100
        assert not (tree / "out" / "big.bin").exists()

        caps = await client.discover()
        assert caps.limit("files_upload_stream", "max_bytes") == 100
        with pytest.raises(PayloadTooLargeError) as precheck:
            await client.files.upload(target, b"x" * 500)
        assert precheck.value.status_code == 0 and precheck.value.limit == 100
        assert (await client.files.upload(target, b"x" * 50)).size == 50

    async def test_overwrite_false_surfaces_as_policy_denied(
        self, server_factory: Any, tree: Path
    ) -> None:
        _live, client = server_factory(
            policy={"endpoints": {"files_upload_stream": {"params": {"overwrite": False}}}}
        )
        target = str(tree / "out" / "a.txt")
        with pytest.raises(FilePolicyDeniedError) as exc:
            await client.files.upload(target, b"new")
        assert exc.value.error_code == "file_exists" and exc.value.status_code == 409
        assert (tree / "out" / "a.txt").read_text() == "alpha"


class TestIdentities:
    async def test_missing_and_wrong_token_is_server_auth_error(self, server_factory: Any) -> None:
        live, client = server_factory(policy=TOKENS)
        with pytest.raises(ServerAuthError) as exc:
            await client.system.info()
        assert isinstance(exc.value, AuthenticationError) and exc.value.status_code == 401
        wrong = client.with_token("not-a-token-000000")
        with pytest.raises(ServerAuthError):
            await wrong.system.info()
        assert await client.health() is True

    async def test_scope_denial_exposes_the_scope(self, server_factory: Any, tree: Path) -> None:
        live, client = server_factory(policy=TOKENS)
        reader = client.with_token(READER)
        with pytest.raises(PolicyDeniedError) as exc:
            await reader.files.upload(str(tree / "out" / "x"), b"1")
        assert exc.value.scope == "files:write" and exc.value.error_code == "missing_scope"
        assert not isinstance(exc.value, PermissionDeniedError)
        assert await reader.files.list(str(tree / "out"))

    async def test_discovery_reflects_the_identity(self, server_factory: Any) -> None:
        live, client = server_factory(policy=TOKENS)
        reader_caps = await client.with_token(READER).discover()
        writer_caps = await client.with_token(WRITER).discover()
        assert reader_caps.identity_id == "reader" and writer_caps.identity_id == "writer"
        assert reader_caps.can("files_list") and not reader_caps.can("files_upload_stream")
        assert writer_caps.can("files_upload_stream")
        assert "files_list" in reader_caps.endpoints_for("files:read")

    async def test_scope_precheck_raises_without_a_round_trip(
        self, server_factory: Any, tree: Path
    ) -> None:
        live, client = server_factory(policy=TOKENS)
        reader = client.with_token(READER)
        await reader.discover()
        live.close()
        with pytest.raises(PolicyDeniedError) as exc:
            await reader.files.upload(str(tree / "out" / "x"), b"1")
        assert exc.value.scope == "files:write"

    async def test_bearer_and_gateway_headers_coexist(self, server_factory: Any) -> None:
        live, _ = server_factory(policy=TOKENS)
        client = ServerClient(live.url, token=READER, headers={"X-Access-Token": "gateway-token"})
        assert (await client.discover()).identity_id == "reader"


class TestRateLimit:
    async def test_rate_limited_error_carries_retry_after(self, server_factory: Any) -> None:
        _live, client = server_factory(
            policy={"endpoints": {"system_info": {"limits": {"rate_per_minute": 2}}}}
        )
        await client.system.info()
        await client.system.info()
        with pytest.raises(RateLimitedError) as exc:
            await client.system.info()
        assert exc.value.status_code == 429
        assert exc.value.retry_after is not None and exc.value.retry_after > 0


class TestProcessRules:
    async def test_command_allow_list_and_stream_denial(self, server_factory: Any) -> None:
        _live, client = server_factory(
            policy={"endpoints": {"shell": {"params": {"allow_commands": ["echo"]}}}}
        )
        assert (await client.process.shell("echo ok")).stdout == "ok\n"
        with pytest.raises(PolicyDeniedError) as exc:
            await client.process.shell("cat /etc/hostname")
        assert exc.value.error_code == "command_not_allowed"

    async def test_signal_allow_list(self, server_factory: Any) -> None:
        _live, client = server_factory(
            policy={"endpoints": {"process_signal": {"params": {"allowed_signals": [15]}}}}
        )
        proc = await client.process.start("sleep 30")
        with pytest.raises(PolicyDeniedError):
            await client.process.kill(proc.pid)
        await client.process.terminate(proc.pid)
        assert await client.process.wait(proc.pid, timeout=5) != 0

    async def test_pty_requires_scope_for_websocket(self, server_factory: Any) -> None:
        policy = {
            "auth": {
                "tokens": [
                    {"id": "t", "token_sha256": sha("term-token-123456"), "scopes": ["terminal:*"]},
                    {
                        "id": "n",
                        "token_sha256": sha("noterm-token-123456"),
                        "scopes": ["files:read"],
                    },
                ]
            }
        }
        _live, client = server_factory(policy=policy)
        allowed = client.with_token("term-token-123456")
        created = await allowed.pty.create("/bin/sh")
        try:
            async with allowed.pty.connect(created.session_id) as term:
                first = await term.recv(timeout=5)
                assert first is not None and first.event == "started"
            denied = client.with_token("noterm-token-123456")
            with pytest.raises(PolicyDeniedError):
                await denied.pty.create("/bin/sh")
        finally:
            await allowed.pty.delete(created.session_id)
