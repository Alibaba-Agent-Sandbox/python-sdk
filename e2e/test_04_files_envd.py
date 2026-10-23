"""Filesystem through envd (Connect filesystem RPC + HTTP /files)."""

from __future__ import annotations

import os

import pytest

import e2e_helpers as H


def test_write_read_roundtrip_text_and_unicode(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    text = "hello\nunicode: 你好 — ✓\n"
    run(base_sandbox.files.write(f"{d}/a.txt", text))
    assert run(base_sandbox.files.read(f"{d}/a.txt")) == text


def test_binary_roundtrip(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    blob = bytes(range(256)) * 64
    run(base_sandbox.files.write(f"{d}/blob.bin", blob))
    assert run(base_sandbox.files.read_bytes(f"{d}/blob.bin")) == blob


def test_write_creates_parent_directories(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/x/y/z.txt", "nested"))
    assert run(base_sandbox.files.read(f"{d}/x/y/z.txt")) == "nested"


def test_exists(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/here.txt", "1"))
    assert run(base_sandbox.files.exists(f"{d}/here.txt")) is True
    assert run(base_sandbox.files.exists(f"{d}/missing.txt")) is False


def test_make_dir_and_list_names_and_sizes(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.make_dir(f"{d}/sub"))
    run(base_sandbox.files.write(f"{d}/f1.txt", "12345"))
    entries = run(base_sandbox.files.list(d))
    by_name = {e.name: e for e in entries}
    assert {"sub", "f1.txt"} <= set(by_name)
    assert by_name["f1.txt"].size == 5


def test_list_and_stat_report_directory_type(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.make_dir(f"{d}/sub"))
    run(base_sandbox.files.write(f"{d}/f1.txt", "12345"))
    by_name = {e.name: e for e in run(base_sandbox.files.list(d))}
    assert by_name["sub"].type.value == "directory"
    assert by_name["f1.txt"].type.value == "file"
    info = run(base_sandbox.files.get_info(f"{d}/f1.txt"))
    assert info.name == "f1.txt" and info.size == 5 and info.type.value == "file"
    dinfo = run(base_sandbox.files.get_info(f"{d}/sub"))
    assert dinfo.type.value == "directory"


def test_stat_via_shell_matches_written_size(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    """Independent oracle for stat: ``stat -c`` inside the sandbox."""
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/s.txt", "abcdefg"))
    out = run(base_sandbox.commands.run(f"stat -c '%s %F' {d}/s.txt")).stdout.strip()
    assert out == "7 regular file"


def test_rename_and_move(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/old.txt", "content"))
    run(base_sandbox.files.move(f"{d}/old.txt", f"{d}/new.txt"))
    assert run(base_sandbox.files.exists(f"{d}/old.txt")) is False
    run(base_sandbox.files.make_dir(f"{d}/dest"))
    run(base_sandbox.files.move(f"{d}/new.txt", f"{d}/dest/moved.txt"))
    assert run(base_sandbox.files.read(f"{d}/dest/moved.txt")) == "content"


def test_remove_file_and_directory(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    run(base_sandbox.files.write(f"{d}/tree/a.txt", "a"))
    run(base_sandbox.files.remove(f"{d}/tree/a.txt"))
    assert run(base_sandbox.files.exists(f"{d}/tree/a.txt")) is False
    run(base_sandbox.files.remove(f"{d}/tree"))
    assert run(base_sandbox.files.exists(f"{d}/tree")) is False


def test_read_missing_file_fails(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    with pytest.raises(Exception) as err:  # noqa: PT011
        run(base_sandbox.files.read(f"{d}/does-not-exist.txt"))
    assert "404" in str(err.value) or "not found" in str(err.value).lower()


def test_read_missing_file_raises_sdk_file_error(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import FileNotFoundError_

    d = workdir(base_sandbox)
    with pytest.raises(FileNotFoundError_):
        run(base_sandbox.files.read(f"{d}/does-not-exist.txt"))


def test_list_missing_directory_raises(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    from agent_sandbox.models.errors import FileNotFoundError_

    d = workdir(base_sandbox)
    with pytest.raises(FileNotFoundError_):
        run(base_sandbox.files.list(f"{d}/no-such-dir"))


def test_upload_and_download_local_files(run, base_sandbox, workdir, local_tmp):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    src = local_tmp / "up.bin"
    payload = os.urandom(300_000)
    src.write_bytes(payload)
    run(base_sandbox.files.upload(str(src), f"{d}/up.bin"))
    out = local_tmp / "down.bin"
    run(base_sandbox.files.download(f"{d}/up.bin", str(out)))
    assert out.read_bytes() == payload


def test_medium_file_roundtrip_matches_remote_checksum(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    import hashlib

    d = workdir(base_sandbox)
    blob = os.urandom(400_000)
    run(base_sandbox.files.write(f"{d}/big.bin", blob))
    remote = run(base_sandbox.commands.run(f"sha256sum {d}/big.bin")).stdout.split()[0]
    assert remote == hashlib.sha256(blob).hexdigest()


def test_file_urls_point_at_envd_files_endpoint(run, base_sandbox):  # type: ignore[no-untyped-def]
    url = run(base_sandbox.files.upload_url("/tmp/x.txt"))
    assert url.startswith(base_sandbox.url + "/files?path=/tmp/x.txt")


def _assert_token_not_in_url(url: str, token: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if token and (token in parsed.query or token in parsed.path or token in parsed.netloc):
        raise AssertionError("envd access token appeared in the file URL")


def _e2b_v1_signature(raw: bytes) -> str:
    import base64
    import hashlib

    digest = hashlib.sha256(raw).digest()
    return "v1_" + base64.b64encode(digest).rstrip(b"=").decode()


def test_signature_only_file_url_is_rejected(run, base_sandbox):  # type: ignore[no-untyped-def]
    """E2B's signed /files URL is not usable on this data plane.

    A browser-style POST or GET, with or without the E2B v1 signature, is
    denied unless ``X-Access-Token`` is set. The same request with that header
    uploads and downloads the bytes.
    """
    from urllib.parse import quote, urlencode, urlparse

    import httpx

    from agent_sandbox.models.errors import FileNotFoundError_, FileOperationError

    path = "/tmp/abx-e2e-file-url.txt"
    body = b"header-upload-ok"
    for method in (
        base_sandbox.upload_url(path),
        base_sandbox.download_url(path),
        base_sandbox.get_upload_url(path),
        base_sandbox.get_download_url(path),
    ):
        with pytest.raises(FileOperationError, match="X-Access-Token"):
            run(method)

    unsigned = run(base_sandbox.files.upload_url(path))
    token = base_sandbox._envd_token.token or ""
    assert token
    parsed = urlparse(unsigned)
    assert parsed.path == "/files"
    assert "signature" not in parsed.query
    _assert_token_not_in_url(unsigned, token)

    denied = httpx.post(
        unsigned,
        files={"file": ("payload.txt", body, "text/plain")},
        timeout=30.0,
        follow_redirects=False,
    )
    assert denied.status_code == 403
    assert "X-Access-Token header is required" in denied.text
    with pytest.raises(FileNotFoundError_):
        run(base_sandbox.files.read(path))

    uploaded = httpx.post(
        unsigned,
        files={"file": ("payload.txt", body, "text/plain")},
        headers={"X-Access-Token": token},
        timeout=30.0,
        follow_redirects=False,
    )
    assert uploaded.status_code == 201
    assert run(base_sandbox.files.read(path)) == body.decode()

    signed_path = "/tmp/abx-e2e-signed-upload.txt"
    write_raw = f"{signed_path}:write::{token}".encode()
    write_signature = _e2b_v1_signature(write_raw)
    signed_upload = (
        f"{base_sandbox.url.rstrip('/')}/files?"
        + urlencode({"path": signed_path, "signature": write_signature}, quote_via=quote)
    )
    _assert_token_not_in_url(signed_upload, token)
    signed_post = httpx.post(
        signed_upload,
        files={"file": ("payload.txt", b"signed-upload", "text/plain")},
        timeout=30.0,
        follow_redirects=False,
    )
    assert signed_post.status_code == 403
    assert "X-Access-Token header is required" in signed_post.text
    with pytest.raises(FileNotFoundError_):
        run(base_sandbox.files.read(signed_path))

    raw = f"{path}:read::{token}".encode()
    signature = _e2b_v1_signature(raw)
    signed = (
        f"{base_sandbox.url.rstrip('/')}/files?"
        + urlencode({"path": path, "signature": signature}, quote_via=quote)
    )
    _assert_token_not_in_url(signed, token)
    signed_get = httpx.get(signed, timeout=30.0, follow_redirects=False)
    assert signed_get.status_code == 403
    assert "X-Access-Token header is required" in signed_get.text

    download = run(base_sandbox.files.download_url(path))
    fetched = httpx.get(
        download,
        headers={"X-Access-Token": token},
        timeout=30.0,
        follow_redirects=False,
    )
    assert fetched.status_code == 200
    assert fetched.content == body
    assert httpx.get(download, timeout=30.0, follow_redirects=False).status_code == 403


@pytest.mark.e2e_slow
@pytest.mark.known_issue
@pytest.mark.xfail(
    strict=False,
    reason="KI-008 (platform/gateway): a >=1 MB envd upload exceeds the default 30 s HTTP timeout "
    "from the test VM; not strict because it depends on network throughput",
)
def test_one_megabyte_upload_within_default_timeout(run, base_sandbox, workdir):  # type: ignore[no-untyped-def]
    d = workdir(base_sandbox)
    blob = os.urandom(1_000_000)
    run(base_sandbox.files.write(f"{d}/1mb.bin", blob))
    assert run(base_sandbox.files.read_bytes(f"{d}/1mb.bin")) == blob
