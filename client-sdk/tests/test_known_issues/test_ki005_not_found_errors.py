"""KI-005: not-found conditions raise SDK errors, not raw ``httpx.HTTPStatusError``."""

from __future__ import annotations

import httpx
import pytest

from agent_sandbox.api.files import FilesModule
from agent_sandbox.models.errors import (
    FileNotFoundError_,
    FileOperationError,
    PermissionDeniedError,
    SandboxError,
    SandboxNotFoundError,
)
from agent_sandbox.providers.shared.e2b.filesystem import FilesystemProtocol
from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol
from tests.test_known_issues.helpers import API, ENVD, make_http, token

FILES_URL = f"{ENVD}/files?path=%2Ftmp%2Fnope.txt&username=user"


def _files() -> FilesModule:
    return FilesModule(ENVD, token(), FilesystemProtocol(make_http()))


# --- files ---------------------------------------------------------------------------------


async def test_read_missing_file_raises_file_not_found(httpx_mock) -> None:
    httpx_mock.add_response(url=FILES_URL, method="GET", status_code=404, json={"message": "no"})
    with pytest.raises(FileNotFoundError_) as err:
        await _files().read("/tmp/nope.txt")
    assert "/tmp/nope.txt" in str(err.value)
    assert not isinstance(err.value, httpx.HTTPError)


async def test_read_bytes_and_download_map_the_same_way(httpx_mock, tmp_path) -> None:
    for _ in range(2):
        httpx_mock.add_response(url=FILES_URL, method="GET", status_code=404, content=b"")
    with pytest.raises(FileNotFoundError_):
        await _files().read_bytes("/tmp/nope.txt")
    with pytest.raises(FileNotFoundError_):
        await _files().download("/tmp/nope.txt", str(tmp_path / "out"))
    assert not (tmp_path / "out").exists()


async def test_forbidden_file_raises_permission_denied(httpx_mock) -> None:
    httpx_mock.add_response(url=FILES_URL, method="GET", status_code=403, content=b"")
    with pytest.raises(PermissionDeniedError):
        await _files().read("/tmp/nope.txt")


async def test_other_file_http_errors_raise_file_operation_error(httpx_mock) -> None:
    httpx_mock.add_response(url=FILES_URL, method="GET", status_code=500, content=b"boom")
    with pytest.raises(FileOperationError) as err:
        await _files().read("/tmp/nope.txt")
    assert "500" in str(err.value)
    assert not isinstance(err.value, FileNotFoundError_)


async def test_upload_failure_raises_file_operation_error(httpx_mock) -> None:
    httpx_mock.add_response(method="POST", status_code=507, content=b"disk full")
    with pytest.raises(FileOperationError) as err:
        await _files().write("/tmp/x.bin", b"data")
    assert "507" in str(err.value)


@pytest.mark.parametrize("op", ["stat", "remove", "move", "make_dir"])
async def test_connect_rpc_file_operations_map_404(httpx_mock, op: str) -> None:
    httpx_mock.add_response(method="POST", status_code=404, content=b"")
    files = _files()
    with pytest.raises(FileNotFoundError_):
        if op == "stat":
            await files.get_info("/x")
        elif op == "remove":
            await files.remove("/x")
        elif op == "move":
            await files.move("/x", "/y")
        else:
            await files.make_dir("/x")


async def test_exists_is_false_for_a_missing_path(httpx_mock) -> None:
    httpx_mock.add_response(method="POST", status_code=404, content=b"")
    assert await _files().exists("/x") is False


# --- sandboxes -----------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["connect", "get_info"])
async def test_missing_sandbox_raises_sandbox_not_found(httpx_mock, method: str) -> None:
    httpx_mock.add_response(
        url=f"{API}/sandboxes/sbx-0000", method="GET", status_code=404, json={"message": "nope"}
    )
    proto = SandboxProtocol(make_http())
    with pytest.raises(SandboxNotFoundError) as err:
        await getattr(proto, method)("sbx-0000")
    assert isinstance(err.value, SandboxError)
    assert "sbx-0000" in str(err.value)
    assert not isinstance(err.value, httpx.HTTPError)


@pytest.mark.parametrize("method", ["set_timeout", "pause", "resume"])
async def test_missing_sandbox_on_mutating_calls(httpx_mock, method: str) -> None:
    httpx_mock.add_response(method="POST", status_code=404, json={"message": "nope"})
    proto = SandboxProtocol(make_http())
    args = (60,) if method == "set_timeout" else ()
    with pytest.raises(SandboxNotFoundError):
        await getattr(proto, method)("sbx-0000", *args)


async def test_kill_of_a_missing_sandbox_stays_idempotent(httpx_mock) -> None:
    httpx_mock.add_response(method="DELETE", status_code=404, json={})
    await SandboxProtocol(make_http()).kill("sbx-0000")


async def test_is_running_is_false_for_a_missing_sandbox(httpx_mock) -> None:
    httpx_mock.add_response(method="GET", status_code=404, json={})
    assert await SandboxProtocol(make_http()).is_running("sbx-0000") is False


async def test_sandbox_connect_on_a_missing_sandbox(httpx_mock, monkeypatch) -> None:
    from agent_sandbox.api.sandbox import Sandbox

    monkeypatch.setenv("ABX_PROVIDER", "alicloud-express")
    httpx_mock.add_response(method="GET", status_code=404, json={"message": "nope"})
    with pytest.raises(SandboxNotFoundError):
        await Sandbox.connect("sbx-00000000", sandbox_api_key="k", sandbox_base_url=API)


# --- the new error class ---------------------------------------------------------------------


def test_sandbox_not_found_error_contract() -> None:
    import agent_sandbox.models as models
    from agent_sandbox.models import errors
    from agent_sandbox.providers.epp import exit_code_for

    assert models.SandboxNotFoundError is SandboxNotFoundError
    assert "SandboxNotFoundError" in errors.__all__
    assert SandboxNotFoundError.code == "E2009"
    assert SandboxNotFoundError.suggestion
    others = {getattr(errors, n).code for n in errors.__all__ if n != "SandboxNotFoundError"}
    assert "E2009" not in others
    assert exit_code_for(SandboxNotFoundError("x")) == 4
