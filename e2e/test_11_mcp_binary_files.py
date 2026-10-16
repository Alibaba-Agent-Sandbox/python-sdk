"""Real Express binary file transfers through Python MCP shared handlers."""

from __future__ import annotations

import base64
import hashlib
import shlex
import uuid

import e2e_helpers as helpers


def test_mcp_binary_file_transfer_and_reconnect(run, tracker):  # type: ignore[no-untyped-def]
    from agent_sandbox import Sandbox
    from agent_sandbox.agent.mcp import SandboxManager
    from agent_sandbox.agent.tools import dispatch_tool

    async def scenario() -> None:
        owner = SandboxManager(template=helpers.OFFICIAL_BASE)
        observer = SandboxManager()
        fresh = SandboxManager()
        sid = None
        try:
            created = await dispatch_tool("create_sandbox", {"timeout": 300}, owner)
            assert "error" not in created
            sid = created["sandbox_id"]
            tracker.sandbox(sid)
            data = bytes(range(256)) * 4096  # Exact advertised limit; includes NUL/non-UTF8.
            path = "/tmp/mcp-binary-" + uuid.uuid4().hex
            uploaded = await dispatch_tool(
                "upload_file",
                {"path": path, "content_base64": base64.b64encode(data).decode()},
                owner,
            )
            assert "error" not in uploaded
            expected = hashlib.sha256(data).hexdigest()
            assert uploaded["sha256"] == expected and uploaded["bytes_written"] == len(data)
            sandbox = await owner.get_sandbox(sid)
            independently = await sandbox.commands.run("sha256sum " + shlex.quote(path), timeout=30)
            assert independently.exit_code == 0 and independently.stdout.split()[0] == expected
            owned_download = await dispatch_tool("download_file", {"path": path}, owner)
            assert owned_download["sha256"] == expected
            empty_path = path + "-empty"
            empty_upload = await dispatch_tool(
                "upload_file", {"path": empty_path, "content_base64": ""}, owner
            )
            assert empty_upload["bytes_written"] == 0
            empty_download = await dispatch_tool("download_file", {"path": empty_path}, owner)
            assert empty_download["content_base64"] == "" and empty_download["bytes_read"] == 0
            downloaded = await dispatch_tool(
                "download_file", {"path": path, "sandbox_id": sid}, observer
            )
            assert downloaded["sha256"] == expected
            assert base64.b64decode(downloaded["content_base64"], validate=True) == data
            # A new manager reads existing remote bytes; binary tools do not opt
            # into background task retention or change default cleanup ownership.
            again = await dispatch_tool("download_file", {"path": path, "sandbox_id": sid}, fresh)
            assert again["sha256"] == expected
            invalid = await dispatch_tool(
                "upload_file", {"path": path, "content_base64": "@invalid"}, observer
            )
            assert invalid["error_category"] == "invalid_input"
            missing = await dispatch_tool(
                "download_file", {"path": path + "-missing", "sandbox_id": sid}, observer
            )
            assert missing["error_category"] == "not_found"
            too_big = await sandbox.commands.run(
                "truncate -s 1048577 " + shlex.quote(path), timeout=30
            )
            assert too_big.exit_code == 0
            oversized = await dispatch_tool(
                "download_file", {"path": path, "sandbox_id": sid}, observer
            )
            assert oversized["error_category"] == "size_limit" and "content_base64" not in oversized
        finally:
            if sid:
                await Sandbox.kill_by_id(sid)
            await owner.shutdown()
            await observer.shutdown()
            await fresh.shutdown()

    run(scenario())
