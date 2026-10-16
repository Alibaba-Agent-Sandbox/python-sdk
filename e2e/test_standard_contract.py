"""Import-only migration scenarios against the actual Express backend."""

from __future__ import annotations

import os

import pytest

import e2e_helpers as H
from agent_sandbox import AsyncSandbox, CommandExitException, Sandbox, SandboxQuery
from agent_sandbox.code_interpreter import Sandbox as CodeSandbox


def test_standard_sync_lifecycle_files_processes_and_interpreter(tracker):
    sandbox = CodeSandbox.create(timeout=300, metadata=H.tag_metadata("standard-sync"))
    tracker.sandbox(sandbox.sandbox_id)
    try:
        assert sandbox.is_running()
        assert Sandbox.get_info(sandbox.sandbox_id).sandbox_id == sandbox.sandbox_id
        def indexed():
            paginator = Sandbox.list(query=SandboxQuery(metadata={"e2e": H.RUN_ID}), limit=100)
            return any(item.sandbox_id == sandbox.sandbox_id for item in paginator.next_items())
        # Metadata indexing is eventually consistent after create.
        assert H.eventually(indexed, timeout=30)
        sandbox.set_timeout(300)
        info = sandbox.files.write("/tmp/standard-contract.txt", "contract")
        assert info.name == "standard-contract.txt"
        assert sandbox.files.read(info.path) == "contract"
        assert sandbox.files.read(info.path, format="bytes") == b"contract"
        assert sandbox.files.exists(info.path)
        with pytest.raises(CommandExitException) as failure:
            sandbox.commands.run("printf output; printf error >&2; exit 7")
        assert (failure.value.exit_code, failure.value.stdout, failure.value.stderr) == (
            7, "output", "error"
        )
        process = sandbox.commands.run("read line; printf '%s' \"$line\"", background=True, stdin=True)
        sandbox.commands.send_stdin(process.pid, "standard-stdin\n")
        assert process.wait().stdout == "standard-stdin"
        assert isinstance(sandbox.get_host(8080), str)
        assert sandbox.download_url(info.path).startswith("https://")
        assert sandbox.upload_url(info.path).startswith("https://")
        outputs = []
        context = sandbox.create_code_context(language="python")
        try:
            assert any(item.id == context.id for item in sandbox.list_code_contexts())
            sandbox.run_code("value = 41", context=context)
            result = sandbox.run_code("print('stream'); value + 1", context=context, on_stdout=outputs.append)
            assert result.text == "42"
            assert any("stream" in output.line for output in outputs)
            assert result.error is None
            error = sandbox.run_code("1 / 0", context=context)
            assert error.error is not None
            assert error.error.value
            sandbox.restart_code_context(context)
            assert sandbox.run_code("value", context=context).error is not None
        finally:
            sandbox.remove_code_context(context)
    finally:
        assert sandbox.kill()
    assert not Sandbox.kill(sandbox.sandbox_id)


@pytest.mark.asyncio
async def test_standard_async_lifecycle_and_results(tracker):
    sandbox = await AsyncSandbox.create(
        template="code-interpreter-v1", timeout=300, metadata=H.tag_metadata("standard-async")
    )
    tracker.sandbox(sandbox.sandbox_id)
    try:
        connected = await AsyncSandbox.connect(sandbox.sandbox_id)
        assert await connected.is_running()
        info = await connected.files.write("/tmp/standard-async.txt", b"async")
        assert await connected.files.read(info.path) == "async"
        assert (await connected.commands.run("printf async")).stdout == "async"
        async def indexed():
            paginator = AsyncSandbox.list(query=SandboxQuery(metadata={"e2e": H.RUN_ID}))
            return any(item.sandbox_id == sandbox.sandbox_id for item in await paginator.next_items())
        # The cloud metadata index is eventually consistent after create.
        assert await H.eventually_async(indexed, timeout=30)
    finally:
        assert await sandbox.kill()


def test_standard_network_update_changes_egress(tracker):
    sandbox = Sandbox.create(timeout=300, metadata=H.tag_metadata("standard-network"))
    tracker.sandbox(sandbox.sandbox_id)
    probe = "curl -sS --connect-timeout 3 --max-time 6 -o /dev/null https://example.com"
    try:
        sandbox.commands.run(probe)
        sandbox.update_network({"deny_out": ["0.0.0.0/0"]})
        with pytest.raises(CommandExitException):
            sandbox.commands.run(probe)
        sandbox.update_network({"deny_out": [], "allow_out": ["0.0.0.0/0"]})
        sandbox.commands.run(probe)
    finally:
        sandbox.kill()


@pytest.mark.skipif(not os.environ.get("E2E_SNAPSHOT_TEMPLATE"), reason="requires a MicroVM template and snapshot allowlist")
def test_standard_snapshot_restore(tracker):
    sandbox = Sandbox.create(template=os.environ["E2E_SNAPSHOT_TEMPLATE"], timeout=600,
                             metadata=H.tag_metadata("standard-snapshot"))
    tracker.sandbox(sandbox.sandbox_id)
    snapshot = None
    restored = None
    try:
        sandbox.files.write("/tmp/snapshot-contract", "snapshot")
        snapshot = sandbox.create_snapshot(request_timeout=300)
        restored = Sandbox.create(template=snapshot.snapshot_id, timeout=300,
                                  metadata=H.tag_metadata("standard-restored"))
        tracker.sandbox(restored.sandbox_id)
        assert restored.files.read("/tmp/snapshot-contract") == "snapshot"
    finally:
        if restored is not None:
            restored.kill()
        sandbox.kill()
        if snapshot is not None:
            assert Sandbox.delete_snapshot(snapshot.snapshot_id)
