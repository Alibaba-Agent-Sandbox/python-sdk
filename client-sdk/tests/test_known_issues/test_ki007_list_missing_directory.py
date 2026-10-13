"""KI-007: ``files.list`` of a missing directory raises instead of returning ``[]``.

Real envd answers ``ListDir`` of a missing path with HTTP 200 ``{"entries": []}`` (observed), but
``Stat`` of the same path with HTTP 404 -- so an empty answer is disambiguated with ``Stat``.
"""

from __future__ import annotations

import pytest

from agent_sandbox.api.files import FilesModule
from agent_sandbox.models.errors import FileNotFoundError_
from agent_sandbox.protocol.filesystem import FilesystemProtocol
from tests.test_known_issues.helpers import ENVD, make_http, token

LIST_URL = f"{ENVD}/filesystem.Filesystem/ListDir"
STAT_URL = f"{ENVD}/filesystem.Filesystem/Stat"


def _files() -> FilesModule:
    return FilesModule(ENVD, token(), FilesystemProtocol(make_http()))


async def test_empty_answer_for_a_missing_directory_raises_not_found(httpx_mock) -> None:
    httpx_mock.add_response(url=LIST_URL, method="POST", json={"entries": []})
    httpx_mock.add_response(url=STAT_URL, method="POST", status_code=404, content=b"")
    with pytest.raises(FileNotFoundError_) as err:
        await _files().list("/tmp/pr/nope")
    assert "/tmp/pr/nope" in str(err.value)


async def test_missing_key_answer_is_also_disambiguated(httpx_mock) -> None:
    httpx_mock.add_response(url=LIST_URL, method="POST", json={})
    httpx_mock.add_response(url=STAT_URL, method="POST", status_code=404, content=b"")
    with pytest.raises(FileNotFoundError_):
        await _files().list("/nope")


async def test_existing_empty_directory_still_lists_as_empty(httpx_mock) -> None:
    httpx_mock.add_response(url=LIST_URL, method="POST", json={"entries": []})
    httpx_mock.add_response(
        url=STAT_URL,
        method="POST",
        json={"entry": {"name": "empty", "path": "/tmp/empty", "type": 2, "size": 4096}},
    )
    assert await _files().list("/tmp/empty") == []


async def test_non_empty_listing_costs_no_extra_stat(httpx_mock) -> None:
    httpx_mock.add_response(
        url=LIST_URL,
        method="POST",
        json={"entries": [{"name": "a", "path": "/d/a", "type": 1, "size": 1}]},
    )
    entries = await _files().list("/d")
    assert [e.name for e in entries] == ["a"]
    assert len(httpx_mock.get_requests()) == 1


async def test_listdir_404_also_maps_to_not_found(httpx_mock) -> None:
    httpx_mock.add_response(url=LIST_URL, method="POST", status_code=404, content=b"not found\n")
    with pytest.raises(FileNotFoundError_):
        await _files().list("/gone")
