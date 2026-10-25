"""Real Express native IDs through the public template launcher."""

import json

import e2e_helpers
import pytest

from agent_sandbox import ProviderSandbox
from agent_sandbox.api import launch_template
from agent_sandbox.models.errors import SandboxNotFoundError
from agent_sandbox.providers.registry import builtin_provider
from conftest import wait_envd_ready


@pytest.mark.parametrize("as_object", [False, True])
@pytest.mark.parametrize("template", ["base", "code-interpreter-v1"])
def test_native_id_launch_exec_and_owned_cleanup(run, tracker, tmp_path, template, as_object):
    manifest = {
        "name": template,
        "provider": "alicloud-express",
        "spec_version": 5,
        "template_id": template,
        "provides": {},
    }

    journal = tmp_path / "template.jsonl"

    async def scenario():
        async with await launch_template(
            manifest,
            provider=builtin_provider() if as_object else "alicloud-express",
            reference=template,
            journal_path=journal,
            timeout=180,
        ) as session:
            sandbox = session.sandbox
            assert sandbox is not None
            tracker.sandbox(sandbox.id)
            await wait_envd_ready(sandbox)
            result = await sandbox.commands.run("printf managed-template-ok")
            assert result.exit_code == 0
            assert result.stdout == "managed-template-ok"
            sandbox_id = sandbox.id

        async def absent():
            try:
                await ProviderSandbox.get_info_by_id(sandbox_id, provider="alicloud-express")
            except SandboxNotFoundError:
                return True
            return False

        await e2e_helpers.eventually_async(
            absent, timeout=30, interval=1, what="owned sandbox deletion"
        )
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        assert events[-1]["event"] == "cleanup-complete"

    run(scenario())


def test_complete_template_starts_both_http_services(run, tracker, tmp_path):
    """Real startup stream, readiness command, port resolution and owned cleanup."""
    import shlex

    start = """
import http.server, threading
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
for port in (9101, 9102):
    server = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
threading.Event().wait()
"""
    ready = """
import time, urllib.request
for attempt in range(100):
    try:
        for port in (9101, 9102):
            url = f'http://127.0.0.1:{port}/health'
            assert urllib.request.urlopen(url, timeout=1).status == 200
        break
    except Exception:
        time.sleep(.1)
else:
    raise RuntimeError('template services not ready')
"""
    manifest = {
        "name": "two-http-services",
        "provider": "alicloud-express",
        "spec_version": 5,
        "template_id": "base",
        "start_cmd": "python3 -u -c " + shlex.quote(start),
        "ready_cmd": "python3 -c " + shlex.quote(ready),
        "provides": {
            name: {"protocol": "http", "version": 1, "port": port, "operations": []}
            for name, port in (("first", 9101), ("second", 9102))
        },
    }
    journal = tmp_path / "multi-service.jsonl"

    async def scenario():
        async with await launch_template(
            manifest,
            provider="alicloud-express",
            timeout=180,
            readiness_timeout=30,
            journal_path=journal,
        ) as session:
            sandbox = session.sandbox
            assert sandbox is not None
            tracker.sandbox(sandbox.id)
            assert set(session.services) == {"first", "second"}
            assert session.servers == {}
            # These test services explicitly implement /health. The launcher
            # itself does not invent this route for arbitrary HTTP protocols.
            assert await session.services["first"].health()
            assert await session.services["second"].health()
            sandbox_id = sandbox.id

        async def absent():
            try:
                await ProviderSandbox.get_info_by_id(sandbox_id, provider="alicloud-express")
            except SandboxNotFoundError:
                return True
            return False

        await e2e_helpers.eventually_async(
            absent, timeout=30, interval=1, what="multi-service owned deletion"
        )
        events = [json.loads(line) for line in journal.read_text().splitlines()]
        assert sum(event["event"] == "started" for event in events) == 1
        assert events[-1]["event"] == "cleanup-complete"

    run(scenario())
