"""KI-008 (gateway throughput, not an SDK bug): the SDK must *report* it clearly.

A large envd upload/download that exceeds the HTTP timeout used to leak a bare
``httpx.WriteTimeout`` / ``ReadTimeout``. The timeout itself is unchanged; the error now names
the operation, the size and the knob to turn.
"""

from __future__ import annotations

import httpx
import pytest

from agent_sandbox.api.files import FilesModule
from agent_sandbox.models.errors import FileOperationError
from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
from tests.test_known_issues.helpers import ENVD, make_http, token


def _files() -> FilesModule:
    return FilesModule(ENVD, token(), FilesystemProtocol(make_http()))


async def test_upload_timeout_is_a_clear_file_operation_error(httpx_mock) -> None:
    httpx_mock.add_exception(httpx.WriteTimeout("timed out"), method="POST")
    with pytest.raises(FileOperationError) as err:
        await _files().write("/tmp/big.bin", b"x" * 1_000_000)
    text = str(err.value)
    assert "timed out" in text.lower()
    assert "/tmp/big.bin" in text
    assert "1000000" in text
    assert "ABX_HTTP_TIMEOUT" in text
    assert not isinstance(err.value, httpx.HTTPError)


async def test_download_timeout_is_a_clear_file_operation_error(httpx_mock) -> None:
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"), method="GET")
    with pytest.raises(FileOperationError) as err:
        await _files().read_bytes("/tmp/big.bin")
    assert "timed out" in str(err.value).lower()
    assert "ABX_HTTP_TIMEOUT" in str(err.value)
