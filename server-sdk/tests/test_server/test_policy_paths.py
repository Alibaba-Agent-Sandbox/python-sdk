"""Path scoping, limits and parameters enforced end-to-end (real server, real filesystem)."""

from __future__ import annotations

import base64
import io
import os
import tarfile
import zipfile
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from ._live import Live


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def q(path: Path | str) -> str:
    return quote(str(path), safe="")


@pytest.fixture
def transfer(live_server: Any, sandbox_tree: Path) -> Live:
    """The headline scenario: only upload+download, download only from ``out/``."""
    return live_server(
        policy={
            "preset": "transfer-only",
            "endpoints": {
                "download": {"paths": {"allow": [str(sandbox_tree / "out")], "deny": ["**/.env"]}},
                "files_download_stream": {
                    "paths": {"allow": [str(sandbox_tree / "out")], "deny": ["**/.env"]},
                    "limits": {"max_bytes": 100},
                },
                "files_upload_stream": {
                    "paths": {"allow": [str(sandbox_tree / "uploads")]},
                    "params": {"overwrite": False, "deny_extensions": [".sh", ".SO"]},
                    "limits": {"max_bytes": 64},
                },
                "upload": {"paths": {"allow": [str(sandbox_tree / "uploads")]}},
            },
        }
    )


class TestTransferOnlyScenario:
    def test_only_transfer_endpoints_exist(self, transfer: Live, sandbox_tree: Path) -> None:
        for method, path, body in [
            ("GET", f"/files/list?path={q(sandbox_tree)}", None),
            ("GET", f"/files/stat?path={q(sandbox_tree)}", None),
            ("POST", "/files/mkdir", {"path": str(sandbox_tree / "x")}),
            ("DELETE", f"/files?path={q(sandbox_tree / 'out' / 'a.txt')}", None),
            ("POST", "/shell", {"command": "true"}),
            ("POST", "/process/start", {"command": "true"}),
            ("GET", "/system/info", None),
            ("GET", "/env", None),
            ("POST", "/files/archive", {"paths": [str(sandbox_tree / "out")]}),
        ]:
            status, resp, _ = transfer.request(method, path, body)
            assert status == 404, (method, path, status, resp)
            assert resp["code"] == "endpoint_disabled"
        assert (sandbox_tree / "out" / "a.txt").exists()

    def test_download_inside_allowed_dir(self, transfer: Live, sandbox_tree: Path) -> None:
        status, body = transfer.get(
            f"/files/download-stream?path={q(sandbox_tree / 'out' / 'a.txt')}"
        )
        assert status == 200 and base64.b64decode(body["content_base64"]) == b"alpha"
        status, body = transfer.get(f"/download?path={q(sandbox_tree / 'out' / 'a.txt')}")
        assert status == 200 and base64.b64decode(body["content_base64"]) == b"alpha"

    @pytest.mark.parametrize("route", ["/files/download-stream", "/download"])
    def test_download_outside_allowed_dir_denied(
        self, transfer: Live, sandbox_tree: Path, route: str
    ) -> None:
        for target in (sandbox_tree / "secret" / "s.txt", sandbox_tree.parent / "outside.txt"):
            status, body = transfer.get(f"{route}?path={q(target)}")
            assert status == 403 and body["code"] == "path_not_allowed", (route, target)
            assert "top-secret" not in str(body) and "outside-data" not in str(body)

    @pytest.mark.parametrize("route", ["/files/download-stream", "/download"])
    def test_download_denied_pattern(self, transfer: Live, sandbox_tree: Path, route: str) -> None:
        status, body = transfer.get(f"{route}?path={q(sandbox_tree / 'out' / '.env')}")
        assert status == 403 and body["code"] == "path_denied"

    def test_traversal_variants_denied(self, transfer: Live, sandbox_tree: Path) -> None:
        base = f"{sandbox_tree}/out"
        for raw in (
            f"{base}/../secret/s.txt",
            f"{base}/sub/../../secret/s.txt",
            f"{base}//..//secret/s.txt",
            f"{base}/./../secret/s.txt",
        ):
            status, body = transfer.get(f"/files/download-stream?path={raw}")
            assert status == 403 and body["code"] == "path_not_allowed", raw
        # Percent-encoded dots are decoded exactly once by the query parser and then
        # resolved like any other traversal; double-encoding stays a literal file name.
        status, body = transfer.get(f"/files/download-stream?path={base}/%2e%2e/secret/s.txt")
        assert status == 403
        status, body = transfer.get(f"/files/download-stream?path={base}/%252e%252e/secret/s.txt")
        assert status == 404

    def test_symlink_escape_denied(self, transfer: Live, sandbox_tree: Path) -> None:
        os.symlink(sandbox_tree.parent / "outside.txt", sandbox_tree / "out" / "evil")
        os.symlink(sandbox_tree / "secret", sandbox_tree / "out" / "evildir")
        for target in ("evil", "evildir/s.txt"):
            status, body = transfer.get(
                f"/files/download-stream?path={q(sandbox_tree / 'out' / target)}"
            )
            assert status == 403 and body["code"] == "path_not_allowed", target

    def test_download_size_limit(self, transfer: Live, sandbox_tree: Path) -> None:
        (sandbox_tree / "out" / "big.bin").write_bytes(b"x" * 101)
        (sandbox_tree / "out" / "ok.bin").write_bytes(b"x" * 100)
        status, body = transfer.get(
            f"/files/download-stream?path={q(sandbox_tree / 'out' / 'big.bin')}"
        )
        assert status == 413 and body["code"] == "payload_too_large" and body["limit"] == 100
        assert (
            transfer.get(f"/files/download-stream?path={q(sandbox_tree / 'out' / 'ok.bin')}")[0]
            == 200
        )

    def test_upload_into_allowed_dir_only(self, transfer: Live, sandbox_tree: Path) -> None:
        good = {"path": str(sandbox_tree / "uploads" / "n.txt"), "content_base64": b64(b"hello")}
        status, body = transfer.post("/files/upload-stream", good)
        assert status == 200 and (sandbox_tree / "uploads" / "n.txt").read_bytes() == b"hello"
        bad = {"path": str(sandbox_tree / "out" / "n.txt"), "content_base64": b64(b"hello")}
        status, body = transfer.post("/files/upload-stream", bad)
        assert status == 403 and body["code"] == "path_not_allowed"
        assert not (sandbox_tree / "out" / "n.txt").exists()

    def test_upload_overwrite_false_returns_409(self, transfer: Live, sandbox_tree: Path) -> None:
        body = {"path": str(sandbox_tree / "uploads" / "dup.txt"), "content_base64": b64(b"one")}
        assert transfer.post("/files/upload-stream", body)[0] == 200
        body["content_base64"] = b64(b"two")
        status, resp = transfer.post("/files/upload-stream", body)
        assert status == 409 and resp["code"] == "file_exists"
        assert (sandbox_tree / "uploads" / "dup.txt").read_bytes() == b"one"

    def test_upload_extension_rules_case_insensitive(
        self, transfer: Live, sandbox_tree: Path
    ) -> None:
        for name in ("x.sh", "x.SH", "y.so", "y.SO"):
            body = {"path": str(sandbox_tree / "uploads" / name), "content_base64": b64(b"#!")}
            status, resp = transfer.post("/files/upload-stream", body)
            assert status == 403 and resp["code"] == "extension_not_allowed", name
        assert not list((sandbox_tree / "uploads").glob("*")) or all(
            p.suffix.lower() not in {".sh", ".so"} for p in (sandbox_tree / "uploads").glob("*")
        )

    def test_upload_size_limit(self, transfer: Live, sandbox_tree: Path) -> None:
        body = {"path": str(sandbox_tree / "uploads" / "big"), "content_base64": b64(b"x" * 65)}
        status, resp = transfer.post("/files/upload-stream", body)
        assert status == 413 and resp["code"] == "payload_too_large"
        assert not (sandbox_tree / "uploads" / "big").exists()

    def test_legacy_upload_download_are_scoped_too(
        self, transfer: Live, sandbox_tree: Path
    ) -> None:
        status, _ = transfer.post(
            "/upload",
            {"path": str(sandbox_tree / "uploads" / "l.txt"), "content_base64": b64(b"1")},
        )
        assert status == 200
        status, body = transfer.post(
            "/upload", {"path": str(sandbox_tree / "out" / "l.txt"), "content_base64": b64(b"1")}
        )
        assert status == 403 and body["code"] == "path_not_allowed"


class TestNoExistenceOracle:
    def test_same_response_for_missing_and_present_outside_paths(
        self, transfer: Live, sandbox_tree: Path
    ) -> None:
        present = transfer.get(
            f"/files/download-stream?path={q(sandbox_tree.parent / 'outside.txt')}"
        )
        missing = transfer.get(f"/files/download-stream?path={q(sandbox_tree.parent / 'nope.txt')}")
        assert present[0] == missing[0] == 403
        assert present[1] == missing[1]

    def test_missing_inside_allowed_is_404(self, transfer: Live, sandbox_tree: Path) -> None:
        status, _ = transfer.get(
            f"/files/download-stream?path={q(sandbox_tree / 'out' / 'missing')}"
        )
        assert status == 404


@pytest.fixture
def explorer(live_server: Any, sandbox_tree: Path) -> Live:
    (sandbox_tree / "out" / "sub").mkdir()
    (sandbox_tree / "out" / "sub" / "n.txt").write_text("nested")
    (sandbox_tree / "out" / "sub" / "k.pem").write_text("pem")
    (sandbox_tree / "out" / "priv").mkdir()
    (sandbox_tree / "out" / "priv" / "hidden.txt").write_text("hidden")
    os.symlink(sandbox_tree.parent / "outside.txt", sandbox_tree / "out" / "escape")
    os.symlink(sandbox_tree / "out" / "a.txt", sandbox_tree / "out" / "inside_alias")
    return live_server(
        policy={
            "groups": {"process": False, "terminal": False},
            "endpoints": {
                "files_*": {
                    "paths": {
                        "allow": [str(sandbox_tree / "out")],
                        "deny": ["*.pem", "**/.env", str(sandbox_tree / "out" / "priv")],
                    }
                },
            },
        }
    )


class TestDirectoryExpandingEndpoints:
    def test_list_omits_denied_and_escaping_entries(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        status, body = explorer.get(f"/files/list?path={q(sandbox_tree / 'out')}&recursive=true")
        assert status == 200
        names = {e["name"] for e in body["entries"]}
        assert {"a.txt", "sub", "n.txt", "inside_alias"} <= names
        assert not names & {".env", "k.pem", "priv", "hidden.txt", "escape"}

    def test_list_outside_denied(self, explorer: Live, sandbox_tree: Path) -> None:
        status, body = explorer.get(f"/files/list?path={q(sandbox_tree)}")
        assert status == 403 and body["code"] == "path_not_allowed"

    def test_search_never_returns_denied(self, explorer: Live, sandbox_tree: Path) -> None:
        status, body = explorer.post(
            "/files/search", {"path": str(sandbox_tree / "out"), "pattern": "*"}
        )
        assert status == 200
        paths = {r["path"] for r in body["results"]}
        assert str(sandbox_tree / "out" / "a.txt") in paths
        assert str(sandbox_tree / "out" / "sub" / "n.txt") in paths
        assert not [p for p in paths if p.endswith((".env", ".pem", "hidden.txt", "escape"))]

    def test_archive_excludes_denied_in_both_formats(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        for fmt in ("zip", "tar.gz"):
            status, body = explorer.post(
                "/files/archive", {"paths": [str(sandbox_tree / "out")], "format": fmt}
            )
            assert status == 200, body
            raw = base64.b64decode(body["content_base64"])
            if fmt == "zip":
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    names = zf.namelist()
            else:
                with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
                    names = tf.getnames()
            joined = " ".join(names)
            assert "a.txt" in joined and "n.txt" in joined
            for forbidden in (".env", ".pem", "hidden.txt", "escape"):
                assert forbidden not in joined, (fmt, names)

    def test_archive_of_denied_path_is_403(self, explorer: Live, sandbox_tree: Path) -> None:
        status, body = explorer.post(
            "/files/archive", {"paths": [str(sandbox_tree / "out" / "priv")]}
        )
        assert status == 403 and body["code"] == "path_denied"
        status, body = explorer.post(
            "/files/archive", {"paths": [str(sandbox_tree / "out"), str(sandbox_tree / "secret")]}
        )
        assert status == 403

    def test_stat_of_denied_is_403_not_exists_false(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        status, body = explorer.get(f"/files/stat?path={q(sandbox_tree / 'out' / '.env')}")
        assert status == 403 and body["code"] == "path_denied"

    def test_delete_directory_containing_denied_entries_refused(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        status, body, _ = explorer.request(
            "DELETE", f"/files?path={q(sandbox_tree / 'out' / 'sub')}"
        )
        assert status == 403 and body["code"] == "path_denied"
        assert (sandbox_tree / "out" / "sub" / "k.pem").exists()

    def test_allow_root_cannot_be_deleted_or_moved(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        status, body, _ = explorer.request("DELETE", f"/files?path={q(sandbox_tree / 'out')}")
        assert status == 403
        status, body = explorer.post(
            "/files/move",
            {"source": str(sandbox_tree / "out"), "destination": str(sandbox_tree / "out" / "x")},
        )
        assert status == 403
        assert (sandbox_tree / "out" / "a.txt").exists()

    def test_move_out_of_scope_denied_both_directions(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        a = str(sandbox_tree / "out" / "a.txt")
        outside = str(sandbox_tree / "secret" / "a.txt")
        status, body = explorer.post("/files/move", {"source": a, "destination": outside})
        assert status == 403 and "destination" in body["error"]
        status, body = explorer.post(
            "/files/move",
            {"source": str(sandbox_tree / "secret" / "s.txt"), "destination": a + "2"},
        )
        assert status == 403 and "source" in body["error"]
        assert (sandbox_tree / "secret" / "s.txt").read_text() == "top-secret"

    def test_move_inside_scope_works(self, explorer: Live, sandbox_tree: Path) -> None:
        status, _ = explorer.post(
            "/files/move",
            {
                "source": str(sandbox_tree / "out" / "a.txt"),
                "destination": str(sandbox_tree / "out" / "moved.txt"),
            },
        )
        assert status == 200 and (sandbox_tree / "out" / "moved.txt").exists()

    def test_relative_paths_resolve_against_allow_root(
        self, explorer: Live, sandbox_tree: Path
    ) -> None:
        status, body = explorer.get("/files/stat?path=a.txt")
        assert status == 200 and body["exists"] is True
        status, body = explorer.get("/files/stat?path=../secret/s.txt")
        assert status == 403

    def test_list_limits(self, live_server: Any, sandbox_tree: Path) -> None:
        for i in range(10):
            (sandbox_tree / "out" / f"f{i}").write_text("x")
        live: Live = live_server(
            policy={"endpoints": {"files_list": {"limits": {"max_entries": 3}}}}
        )
        _, body = live.get(f"/files/list?path={q(sandbox_tree / 'out')}&max_entries=100")
        assert len(body["entries"]) == 3


class TestReadOnlyAndSymlinkNever:
    def test_read_only_blocks_writes_but_not_reads(
        self, live_server: Any, sandbox_tree: Path
    ) -> None:
        live: Live = live_server(
            policy={
                "endpoints": {
                    "files_*": {"paths": {"read_only": True}},
                    "upload": {"paths": {"read_only": True}},
                }
            }
        )
        p = str(sandbox_tree / "out" / "a.txt")
        assert live.get(f"/files/stat?path={q(p)}")[0] == 200
        for route, body in [
            ("/files/mkdir", {"path": str(sandbox_tree / "n")}),
            ("/files/upload-stream", {"path": p, "content_base64": b64(b"z")}),
            ("/files/move", {"source": p, "destination": p + "2"}),
            ("/upload", {"path": p, "content_base64": b64(b"z")}),
        ]:
            status, resp = live.post(route, body)
            assert status == 403 and resp["code"] == "read_only", route
        status, resp, _ = live.request("DELETE", f"/files?path={q(p)}")
        assert status == 403 and resp["code"] == "read_only"
        assert (sandbox_tree / "out" / "a.txt").read_text() == "alpha"

    def test_symlinks_never(self, live_server: Any, sandbox_tree: Path) -> None:
        os.symlink(sandbox_tree / "out" / "a.txt", sandbox_tree / "out" / "alias")
        live: Live = live_server(
            policy={"endpoints": {"files_*": {"paths": {"symlinks": "never"}}}}
        )
        status, body = live.get(f"/files/download-stream?path={q(sandbox_tree / 'out' / 'alias')}")
        assert status == 403 and body["code"] == "symlink_denied"
        assert (
            live.get(f"/files/download-stream?path={q(sandbox_tree / 'out' / 'a.txt')}")[0] == 200
        )


class TestArchiveSymlinkLeakFix:
    """Pre-existing leak: zip archived the *content* of file symlinks pointing outside."""

    @pytest.mark.parametrize("fmt", ["zip", "tar.gz"])
    def test_unconfigured_server_does_not_leak_symlink_target(
        self, live_server: Any, sandbox_tree: Path, fmt: str
    ) -> None:
        os.symlink(sandbox_tree.parent / "outside.txt", sandbox_tree / "out" / "leak")
        live: Live = live_server()
        status, body = live.post(
            "/files/archive", {"paths": [str(sandbox_tree / "out")], "format": fmt}
        )
        assert status == 200
        raw = base64.b64decode(body["content_base64"])
        assert b"outside-data" not in raw
        if fmt == "zip":
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                assert all(zf.read(n) != b"outside-data" for n in zf.namelist())
                assert not any(n.endswith("leak") for n in zf.namelist())
        else:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if member.isfile():
                        extracted = tf.extractfile(member)
                        assert extracted is not None and extracted.read() != b"outside-data"

    def test_symlink_inside_base_still_archived_in_legacy_zip(
        self, live_server: Any, sandbox_tree: Path
    ) -> None:
        os.symlink(sandbox_tree / "out" / "a.txt", sandbox_tree / "out" / "alias")
        live: Live = live_server()
        _, body = live.post(
            "/files/archive", {"paths": [str(sandbox_tree / "out")], "format": "zip"}
        )
        zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(body["content_base64"])))
        assert any(n.endswith("alias") for n in zf.namelist())
