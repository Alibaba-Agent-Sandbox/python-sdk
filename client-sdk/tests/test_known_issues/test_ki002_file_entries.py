"""KI-002: ``files.list`` / ``files.get_info`` must understand envd's ``EntryInfo``.

Shapes below were captured from a real envd 0.5.2 sandbox::

    ListDir -> {"entries": [{"name": "sub", "path": "/tmp/pr/sub", "type": 2, "size": 4096, ...}]}
    Stat    -> {"entry": {"name": "f.txt", "path": "/tmp/pr/f.txt", "type": 1, "size": 6, ...}}

``type`` is the protobuf enum ``FILE_TYPE_FILE = 1`` / ``FILE_TYPE_DIRECTORY = 2``; ``Stat`` nests
the entry under ``entry``.
"""

from __future__ import annotations

from typing import Any

import pytest

from easy_sandbox.api.files import FilesModule
from easy_sandbox.models.filesystem import FileType
from easy_sandbox.protocol.filesystem import FilesystemProtocol, _parse_file_info, _unwrap_entry
from tests.test_known_issues.helpers import ENVD, make_http, token

LIST_URL = f"{ENVD}/filesystem.Filesystem/ListDir"
STAT_URL = f"{ENVD}/filesystem.Filesystem/Stat"


def _entry(name: str, type_: Any, size: Any, base: str = "/tmp/pr") -> dict[str, Any]:
    return {
        "group": "1000",
        "mode": 420,
        "modifiedTime": "2026-10-12T12:01:49Z",
        "name": name,
        "owner": "1000",
        "path": f"{base}/{name}",
        "permissions": "-rw-r--r--",
        "size": size,
        "type": type_,
    }


def _files() -> FilesModule:
    return FilesModule(ENVD, token(), FilesystemProtocol(make_http()))


async def test_list_reports_directories_and_files_from_numeric_type(httpx_mock) -> None:
    httpx_mock.add_response(
        url=LIST_URL,
        method="POST",
        json={
            "entries": [
                _entry("f.txt", 1, 6),
                _entry("ln", 1, 13),
                _entry("sub", 2, 4096),
            ]
        },
    )
    entries = {e.name: e for e in await _files().list("/tmp/pr")}
    assert entries["sub"].type is FileType.DIRECTORY
    assert entries["f.txt"].type is FileType.FILE
    assert entries["ln"].type is FileType.FILE
    assert entries["f.txt"].path == "/tmp/pr/f.txt"
    assert entries["f.txt"].size == 6


async def test_get_info_unwraps_entry_object_for_a_file(httpx_mock) -> None:
    httpx_mock.add_response(url=STAT_URL, method="POST", json={"entry": _entry("f.txt", 1, 6)})
    info = await _files().get_info("/tmp/pr/f.txt")
    assert (info.name, info.path, info.size, info.type) == (
        "f.txt",
        "/tmp/pr/f.txt",
        6,
        FileType.FILE,
    )


async def test_get_info_reports_a_directory(httpx_mock) -> None:
    httpx_mock.add_response(url=STAT_URL, method="POST", json={"entry": _entry("sub", 2, 4096)})
    info = await _files().get_info("/tmp/pr/sub")
    assert info.type is FileType.DIRECTORY
    assert info.name == "sub"


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        (2, FileType.DIRECTORY),
        ("2", FileType.DIRECTORY),
        ("FILE_TYPE_DIRECTORY", FileType.DIRECTORY),
        ("directory", FileType.DIRECTORY),
        (1, FileType.FILE),
        ("FILE_TYPE_FILE", FileType.FILE),
        ("file", FileType.FILE),
        (0, FileType.FILE),
        (None, FileType.FILE),
    ],
)
def test_entry_type_spellings(raw_type: Any, expected: FileType) -> None:
    data = _entry("x", raw_type, 1)
    if raw_type is None:
        del data["type"]
    assert _parse_file_info(data).type is expected


def test_protobuf_json_int64_size_arrives_as_a_string() -> None:
    assert _parse_file_info(_entry("x", 1, "5")).size == 5


def test_name_falls_back_to_the_path_when_the_entry_has_none() -> None:
    data = _entry("x", 1, 1)
    del data["name"]
    assert _parse_file_info(data).name == "x"


def test_flat_legacy_shapes_still_parse() -> None:
    info = _parse_file_info({"name": "d", "path": "/d", "isDir": True, "size": 0})
    assert info.type is FileType.DIRECTORY
    wrapped = {"result": {"entry": _entry("y", 2, 0)}}
    assert _parse_file_info(_unwrap_entry(wrapped)).type is FileType.DIRECTORY
    assert _unwrap_entry({"name": "flat"}) == {"name": "flat"}
