"""Upload contracts through real HTTP requests and local filesystem effects."""

from __future__ import annotations

import base64
import http.client
import json
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from ._live import Live


def test_empty_upload_round_trip(live_server: Any, tmp_path: Path) -> None:
    live: Live = live_server()
    target = tmp_path / "empty.bin"
    status, body = live.post("/files/upload-stream", {"path": str(target), "content_base64": ""})
    assert status == 200
    assert body["bytes"] == 0
    assert target.read_bytes() == b""
    status, body = live.get(f"/files/download-stream?path={target}")
    assert status == 200
    assert body["content_base64"] == "" and body["bytes"] == 0


@pytest.mark.parametrize("content", [None, 0, {}, []])
def test_invalid_upload_content_keeps_existing_file(
    live_server: Any, tmp_path: Path, content: Any
) -> None:
    live: Live = live_server()
    target = tmp_path / "existing.bin"
    target.write_bytes(b"keep")
    status, _ = live.post("/files/upload-stream", {"path": str(target), "content_base64": content})
    assert status == 400
    assert target.read_bytes() == b"keep"


def test_missing_upload_content_keeps_existing_file(live_server: Any, tmp_path: Path) -> None:
    live: Live = live_server()
    target = tmp_path / "existing.bin"
    target.write_bytes(b"keep")
    status, _ = live.post("/files/upload-stream", {"path": str(target)})
    assert status == 400
    assert target.read_bytes() == b"keep"


def test_eight_mib_upload_round_trip(live_server: Any, tmp_path: Path) -> None:
    live: Live = live_server()
    target = tmp_path / "eight-mib.bin"
    content = bytes(range(256)) * (8 * 1024 * 1024 // 256)
    status, body = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(content).decode("ascii")},
    )
    assert status == 200
    assert body["bytes"] == len(content)
    assert target.read_bytes() == content
    status, body = live.get(f"/files/download-stream?path={target}")
    assert status == 200
    assert base64.b64decode(body["content_base64"], validate=True) == content


@pytest.mark.parametrize("size, expected", [(6, 200), (7, 200), (8, 413)])
def test_decoded_limit_at_base64_padding_boundary(
    live_server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, size: int, expected: int
) -> None:
    monkeypatch.setenv("ABX_MAX_UPLOAD_SIZE", "7")
    live: Live = live_server()
    target = tmp_path / "boundary.bin"
    content = b"x" * size
    status, body = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(content).decode("ascii")},
    )
    assert status == expected
    if expected == 200:
        assert target.read_bytes() == content
    else:
        assert body["code"] == "payload_too_large" and body["limit"] == 7
        assert not target.exists()


def test_oversized_encoding_is_rejected_before_decoding(
    live_server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_MAX_UPLOAD_SIZE", "4")
    live: Live = live_server()
    target = tmp_path / "oversized.bin"

    original_decode = base64.b64decode
    decoded = False

    def tracked_decode(*args: Any, **kwargs: Any) -> bytes:
        nonlocal decoded
        decoded = True
        return original_decode(*args, **kwargs)

    monkeypatch.setattr("agent_sandbox.server.routes_files.base64.b64decode", tracked_decode)
    status, body = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(b"x" * 10).decode("ascii")},
    )
    assert status == 413 and body["limit"] == 4
    assert not decoded
    assert not target.exists()


def test_explicit_request_limit_still_wins(live_server: Any, tmp_path: Path) -> None:
    live: Live = live_server(
        policy={"endpoints": {"files_upload_stream": {"limits": {"max_request_bytes": 200}}}}
    )
    target = tmp_path / "capped.bin"
    status, body = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(b"x" * 200).decode("ascii")},
    )
    assert status == 413 and body["limit"] == 200
    assert not target.exists()


def test_policy_decoded_limit_overrides_environment(
    live_server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_MAX_UPLOAD_SIZE", "4")
    live: Live = live_server(
        policy={"endpoints": {"files_upload_stream": {"limits": {"max_bytes": 8}}}}
    )
    target = tmp_path / "policy.bin"
    status, _ = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(b"12345678").decode("ascii")},
    )
    assert status == 200 and target.read_bytes() == b"12345678"


def test_other_routes_keep_ten_mib_body_limit(live_server: Any) -> None:
    live: Live = live_server()
    conn = http.client.HTTPConnection("127.0.0.1", live.port, timeout=10)
    try:
        conn.putrequest("POST", "/files/mkdir")
        conn.putheader("Content-Length", str(10 * 1024 * 1024 + 1))
        conn.endheaders()
        response = conn.getresponse()
        body = json.loads(response.read())
        assert response.status == 413 and body["limit"] == 10 * 1024 * 1024
    finally:
        conn.close()


def test_policy_upload_budget_uses_effective_limit(
    live_server: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ABX_MAX_UPLOAD_SIZE", "4")
    size = 8 * 1024 * 1024
    live: Live = live_server(
        policy={"endpoints": {"files_upload_stream": {"limits": {"max_bytes": size}}}}
    )
    target = tmp_path / "policy-budget.bin"
    content = b"p" * size
    status, body = live.post(
        "/files/upload-stream",
        {"path": str(target), "content_base64": base64.b64encode(content).decode("ascii")},
    )
    assert status == 200 and body["bytes"] == size
    assert target.read_bytes() == content
