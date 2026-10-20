"""Real remote sandbox acceptance of the external application loop, not FC/LLM."""

from __future__ import annotations

import json

import e2e_helpers as helpers
import pytest

from agent_sandbox import AsyncSandbox
from agent_sandbox.applications import (
    Application,
    ApplicationRuntime,
    ExternalAgentExecutor,
    Principal,
    Store,
)


class ScriptedProofModel:
    """Trusted deterministic model: real shell/files run only in the cloud sandbox."""

    def __init__(self):
        self.step = 0

    async def complete(self, messages, tools):
        self.step += 1
        if self.step == 1:
            name, args = "shell", {"command": "printf application-runtime-proof"}
        elif self.step == 2:
            assert "application-runtime-proof" in messages[-1]["content"]
            name, args = (
                "write_file",
                {"path": "application-proof.txt", "content": "cloud-file-proof"},
            )
        elif self.step == 3:
            name, args = "artifact", {"path": "application-proof.txt", "name": "proof.txt"}
        else:
            return {"role": "assistant", "content": "cloud-application-proof"}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"proof-{self.step}",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(args)},
                }
            ],
        }


@pytest.mark.asyncio
async def test_external_loop_real_remote_shell_files_and_verified_cleanup(tmp_path, tracker):
    owned = []

    async def create(context):
        metadata = {
            **helpers.tag_metadata("application-external"),
            "abxApplicationRun": context.run_id,
        }
        sandbox = await AsyncSandbox.create(timeout=180, metadata=metadata)
        tracker.sandbox(sandbox.sandbox_id)
        owned.append(sandbox)
        return sandbox

    store = Store("sqlite:///" + str(tmp_path / "application.db"), local=True)
    app = Application(
        "cloud-runtime-proof",
        "external",
        {"model": "scripted-proof", "template": "base"},
        max_run_seconds=120,
        max_tool_seconds=10,
    )
    runtime = ApplicationRuntime(
        store,
        {app.revision: app},
        lambda _: ExternalAgentExecutor(
            ScriptedProofModel(), create, workspace="/tmp", tool_seconds=10
        ),
        lambda _: None,
        lambda _: None,
        heartbeat_seconds=0.2,
    )
    principal = Principal("e2e-owner", frozenset({app.revision}))
    try:
        run = runtime.create(
            principal,
            "cloud-proof",
            {
                "applicationRevision": app.revision,
                "input": {"text": "Verify remote-only tools"},
            },
        )
        assert await runtime.work(run["id"])
        result = store.result(run["id"], principal.owner)
        assert result["status"] == "succeeded"
        assert result["outputText"] == "cloud-application-proof"
        assert (
            store.artifact(run["id"], principal.owner, result["artifacts"][0]["id"])[0]
            == b"cloud-file-proof"
        )
        assert len(owned) == 1
        assert not await AsyncSandbox.kill(owned[0].sandbox_id)
        assert not await runtime.work(run["id"])
    finally:
        for sandbox in owned:
            await AsyncSandbox.kill(sandbox.sandbox_id)
