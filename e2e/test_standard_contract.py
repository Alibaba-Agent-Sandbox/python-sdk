"""Import-only migration scenarios against the actual Express backend."""

from __future__ import annotations

import os
import shlex
import time

import pytest

import e2e_helpers as H
from agent_sandbox import AsyncSandbox, CommandExitException, Sandbox, SandboxQuery, SandboxState, SandboxException
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


def _kill_settled(sandbox_id):
    """Delete only owned resources; known transition conflicts are temporary."""
    deadline = time.monotonic() + 120
    while True:
        try:
            return Sandbox.kill(sandbox_id)
        except SandboxException as exc:
            if not str(exc).startswith("409:") or time.monotonic() >= deadline:
                raise
            time.sleep(2)


def _snapshot_ids(sandbox_id):
    pages = Sandbox.list_snapshots(sandbox_id=sandbox_id)
    found = set()
    while pages.has_next:
        found.update(item.snapshot_id for item in pages.next_items())
    return found


def _start_memory_probe(sandbox):
    """Observe a value generated only in process memory, not reconstructible from files."""
    program = (
        "import http.server,uuid; token=uuid.uuid4().hex; "
        "Handler=type('Handler',(http.server.BaseHTTPRequestHandler,),{"
        "'do_GET':lambda self:(self.send_response(200),self.end_headers(),"
        "self.wfile.write(token.encode())),"
        "'log_message':lambda *args:None}); "
        "http.server.HTTPServer(('127.0.0.1',8765),Handler).serve_forever()"
    )
    sandbox.commands.run("python3 -u -c " + shlex.quote(program), background=True)
    probe = "python3 -c " + shlex.quote(
        "import urllib.request; print(urllib.request.urlopen("
        "'http://127.0.0.1:8765',timeout=3).read().decode())"
    )

    def ready():
        try:
            return sandbox.commands.run(probe).stdout.strip()
        except CommandExitException:
            return False

    assert H.eventually(ready, timeout=30), "in-memory probe did not become ready"
    token = sandbox.commands.run(probe).stdout.strip()
    assert len(token) == 32
    return probe, token


PAUSE_TEMPLATE = os.environ.get("E2E_PAUSE_TEMPLATE") or os.environ.get("E2E_SNAPSHOT_TEMPLATE")


@pytest.mark.skipif(not PAUSE_TEMPLATE, reason="requires an enabled pause template (MicroVM preferred)")
def test_standard_pause_resume_preserves_memory_and_files(tracker):
    sandbox = Sandbox.create(template=PAUSE_TEMPLATE, timeout=900,
                             metadata=H.tag_metadata("standard-pause"))
    tracker.sandbox(sandbox.sandbox_id)
    try:
        sandbox.files.write("/tmp/pause-contract", "before-pause")
        probe, token = _start_memory_probe(sandbox)
        assert sandbox.pause()

        def paused():
            pages = Sandbox.list(query=SandboxQuery(
                state=[SandboxState.PAUSED], metadata={"e2e": H.RUN_ID}), limit=100)
            while pages.has_next:
                if any(item.sandbox_id == sandbox.sandbox_id for item in pages.next_items()):
                    return True
            return False

        assert H.eventually(paused, timeout=120), "sandbox never reached paused state"
        resumed = Sandbox.connect(sandbox.sandbox_id, timeout=300)
        assert resumed.is_running()
        assert resumed.files.read("/tmp/pause-contract") == "before-pause"
        assert resumed.commands.run(probe).stdout.strip() == token
    finally:
        _kill_settled(sandbox.sandbox_id)


@pytest.mark.skipif(not os.environ.get("E2E_SNAPSHOT_TEMPLATE"), reason="requires a MicroVM template and snapshot allowlist")
def test_standard_snapshot_restore(tracker):
    sandbox = Sandbox.create(template=os.environ["E2E_SNAPSHOT_TEMPLATE"], timeout=900,
                             metadata=H.tag_metadata("standard-snapshot"))
    tracker.sandbox(sandbox.sandbox_id)
    snapshot = None
    restored = None
    try:
        # Keep overwrite assertions inside an owned non-sticky directory.
        # Some envd images reject rewriting user files directly under sticky /tmp
        # even before snapshot creation; that is a separate file-service behavior.
        sandbox.files.write("/tmp/standard-snapshot-contract/state", "snapshot")
        probe, token = _start_memory_probe(sandbox)
        snapshot = sandbox.create_snapshot(request_timeout=300)
        # Creation and list indexing are separate, eventually consistent operations.
        assert H.eventually(lambda: snapshot.snapshot_id in _snapshot_ids(sandbox.sandbox_id),
                            timeout=120)
        restored = Sandbox.create(template=snapshot.snapshot_id, timeout=300,
                                  metadata=H.tag_metadata("standard-restored"))
        tracker.sandbox(restored.sandbox_id)
        assert restored.files.read("/tmp/standard-snapshot-contract/state") == "snapshot"
        assert restored.commands.run(probe).stdout.strip() == token
        restored.files.write("/tmp/standard-snapshot-contract/state", "restored-only")
        assert sandbox.files.read("/tmp/standard-snapshot-contract/state") == "snapshot"
    finally:
        if restored is not None:
            _kill_settled(restored.sandbox_id)
        # A timed-out create may have committed. Reconcile by the uniquely owned
        # source sandbox, never blindly issue another snapshot create.
        owned = {snapshot.snapshot_id} if snapshot is not None else set()
        try:
            owned.update(_snapshot_ids(sandbox.sandbox_id))
        finally:
            try:
                _kill_settled(sandbox.sandbox_id)
            finally:
                for snapshot_id in owned:
                    assert Sandbox.delete_snapshot(snapshot_id)
                    assert H.eventually(lambda: snapshot_id not in _snapshot_ids(sandbox.sandbox_id),
                                        timeout=120)
                    # This backend returns204 on repeated deletion too; verify
                    # absence instead of assuming a second call returns False.
                    assert isinstance(Sandbox.delete_snapshot(snapshot_id), bool)
