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
