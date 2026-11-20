"""Native harness records and command construction; no model/backend acceptance claim."""

from __future__ import annotations

import json
import os
import shlex
import time
from pathlib import Path

import pytest

from agent_sandbox.server.agents.adapters import AdapterRegistry, TurnContext
from agent_sandbox.server.agents.adapters.deepseek_harness import DeepSeekHarnessParser
from agent_sandbox.server.agents.adapters.opencode import OpenCodeParser
from agent_sandbox.server.agents.adapters.qoder import QoderParser
from agent_sandbox.server.agents.config import AgentSpec, ProviderSpec
from agent_sandbox.server.managed import ManagedBridge


def context(runtime: str, tmp_path, *, resume: str | None = None) -> TurnContext:
    return TurnContext(
        spec=AgentSpec(
            name="test",
            runtime=runtime,
            model="test-model",
            provider=ProviderSpec(
                api_key="placeholder-model-secret",
                base_url=None if runtime == "qoder" else "https://model.example/v1",
            ),
            permissions="full_access",
        ),
        prompt="Inspect this project",
        workdir=str(tmp_path),
        turn_dir=str(tmp_path),
        native_session_id=resume,
    )


@pytest.mark.parametrize(
    "name,alias,binary",
    [
        ("qoder", "qodercli", "qoder"),
        ("opencode", "open-code", "opencode"),
        ("deepseek-harness", "dsh", "dsh"),
    ],
)
def test_native_registry_and_invocation(name, alias, binary, tmp_path):
    registry = AdapterRegistry()
    adapter = registry.get(alias)
    assert adapter is not None and adapter.name == name
    ctx = context(name, tmp_path, resume="native-session")
    assert adapter.validate(ctx.spec) == []
    invocation = adapter.build_invocation(ctx)
    assert invocation.argv[0] == binary
    assert "native-session" in invocation.argv
    assert "placeholder-model-secret" not in " ".join(invocation.argv)
    assert "placeholder-model-secret" in invocation.env.values()
    assert all(b"placeholder-model-secret" not in f.content for f in invocation.files)
    assert not adapter.capabilities.partial_deltas


def test_qoder_has_native_pat_and_no_fake_endpoint(tmp_path):
    adapter = AdapterRegistry().get("qoder")
    assert adapter is not None
    ctx = context("qoder", tmp_path)
    invocation = adapter.build_invocation(ctx)
    assert invocation.env == {"QODER_PERSONAL_ACCESS_TOKEN": "placeholder-model-secret"}
    assert "OPENAI_API_KEY" not in invocation.env
    ctx.spec.provider.base_url = "https://model.example/v1"
    assert adapter.validate(ctx.spec)


def test_dsh_preserves_native_home_across_turns(tmp_path):
    adapter = AdapterRegistry().get("deepseek-harness")
    assert adapter is not None
    first = adapter.build_invocation(context("deepseek-harness", tmp_path))
    second = adapter.build_invocation(context("deepseek-harness", tmp_path, resume="session-exact"))
    assert first.env["DSH_HOME"] == second.env["DSH_HOME"]
    assert "--session-id" not in first.argv
    assert second.argv[second.argv.index("--session-id") + 1] == "session-exact"
    assert json.loads(first.files[0].content)[0]["config"]["model"] == "test-model"


def test_dsh_committed_events_and_final_reason():
    parser = DeepSeekHarnessParser()
    records = [
        {"type": "session", "sessionId": "session-exact"},
        {"type": "text", "text": "Committed answer"},
        {"type": "tool_call", "callId": "call-one", "tool": "run_shell", "input": {"cmd": "true"}},
        {"type": "tool_result", "callId": "call-one", "status": "completed", "result": "ok"},
        {
            "type": "final",
            "sessionId": "session-exact",
            "reason": {"kind": "completed"},
            "text": "Committed answer",
        },
    ]
    events = [event for record in records for event in parser.feed(json.dumps(record))]
    assert [e.kind for e in events] == ["session", "message", "tool_start", "tool_end", "result"]
    assert events[-1].data["ok"] is True
    assert parser.finish(0) == []


@pytest.mark.parametrize("reason", [None, {"kind": "aborted"}, {"kind": "error"}])
def test_dsh_final_without_completed_reason_fails(reason):
    events = DeepSeekHarnessParser().feed(json.dumps({"type": "final", "reason": reason}))
    assert events[-1].data["ok"] is False


@pytest.mark.parametrize("parser", [DeepSeekHarnessParser, OpenCodeParser, QoderParser])
def test_zero_exit_without_native_terminal_is_not_success(parser):
    assert parser().finish(0)[-1].data["ok"] is False


@pytest.mark.parametrize(
    ("adapter", "binary"), [("codex", "codex"), ("qwen-code", "qwen"), ("claude-code", "claude")]
)
@pytest.mark.parametrize("terminal", [True, False], ids=["complete-stream", "truncated-stream"])
def test_managed_bridge_requires_native_terminal_result(
    adapter, binary, terminal, tmp_path, monkeypatch
):
    text = "The work produced an intermediate message."
    if adapter == "codex":
        message = {
            "type": "item.completed",
            "item": {"id": "m1", "type": "agent_message", "text": text},
        }
        result = {"type": "turn.completed"}
    else:
        message = {
            "type": "assistant",
            "message": {"id": "m1", "content": [{"type": "text", "text": text}]},
        }
        result = {"type": "result", "subtype": "success", "is_error": False}
    records = [message, result] if terminal else [message]

    executable = tmp_path / binary
    lines = "\n".join(f"printf '%s\\n' {shlex.quote(json.dumps(record))}" for record in records)
    executable.write_text(f"#!/bin/sh\n{lines}\nexit 0\n")
    executable.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("HOME", str(tmp_path))

    bridge = ManagedBridge(str(tmp_path / "journal"), str(tmp_path / "workspace"))
    session = bridge.create_session(
        {"nonce": "native-result", "agent": {"adapter": adapter, "model": "test-model"}}
    )
    receipt = bridge.submit(
        {
            "submission_id": "native-result",
            "session_id": session["session_id"],
            "input": "Create a test report.",
            "files": [],
            "deadline": time.time() + 10,
        }
    )
    _, turn = bridge.runtime.find_turn(receipt["turn_id"])
    assert turn.done.wait(timeout=5)
    receipt = bridge.get("native-result")
    expected = "completed" if terminal else "failed"
    assert receipt["status"] == receipt["turn"]["status"] == expected
    if not terminal:
        assert "native terminal result" in receipt["turn"]["error"]["message"]


def test_opencode_native_session_text_tool_and_terminal():
    parser = OpenCodeParser()
    records = [
        {"type": "step_start", "sessionID": "ses-exact", "part": {"id": "start"}},
        {
            "type": "tool_use",
            "sessionID": "ses-exact",
            "part": {
                "id": "tool-one",
                "tool": "bash",
                "state": {"status": "completed", "input": {"command": "true"}, "output": "ok"},
            },
        },
        {"type": "text", "sessionID": "ses-exact", "part": {"id": "text-one", "text": "Done"}},
        {
            "type": "step_finish",
            "sessionID": "ses-exact",
            "part": {"id": "end", "reason": "stop", "tokens": {"input": 3, "output": 2}},
        },
    ]
    events = [event for record in records for event in parser.feed(json.dumps(record))]
    assert [e.kind for e in events] == [
        "session",
        "tool_complete",
        "message",
        "usage",
        "result",
    ]
    assert events[-1].data["ok"] is True
    assert parser.finish(0) == []


def test_opencode_tool_call_step_is_not_terminal():
    parser = OpenCodeParser()
    parser.feed(json.dumps({"type": "step_finish", "part": {"reason": "tool-calls"}}))
    assert parser.finish(0)[-1].data["ok"] is False


def test_opencode_native_error_fails():
    parser = OpenCodeParser()
    events = parser.feed(
        json.dumps({"type": "error", "error": {"name": "APIError", "data": {"message": "Denied"}}})
    )
    assert events[0].data["fatal"] is True
    assert events[-1].data["ok"] is False


def test_opencode_config_uses_env_references(tmp_path):
    adapter = AdapterRegistry().get("opencode")
    assert adapter is not None
    invocation = adapter.build_invocation(context("opencode", tmp_path))
    config = json.loads(invocation.env["OPENCODE_CONFIG_CONTENT"])
    assert config["provider"]["abx"]["options"]["apiKey"] == "{env:OPENAI_API_KEY}"
    assert "placeholder-model-secret" not in invocation.env["OPENCODE_CONFIG_CONTENT"]
    assert invocation.stdin == b"Inspect this project"


def test_opencode_never_silently_widens_workspace_write(tmp_path):
    adapter = AdapterRegistry().get("opencode")
    assert adapter is not None
    ctx = context("opencode", tmp_path)
    ctx.spec.permissions = "workspace_write"
    assert adapter.validate(ctx.spec)
    with pytest.raises(ValueError, match="workspace_write"):
        adapter.build_invocation(ctx)


@pytest.mark.parametrize("name", ["opencode", "deepseek-harness"])
def test_installed_native_cli_captures(name, tmp_path):
    adapter = AdapterRegistry().get(name)
    assert adapter is not None
    parser = adapter.new_parser(context(name, tmp_path))
    capture = Path(__file__).parents[1] / "fixtures" / "native-harnesses" / (name + ".jsonl")
    events = [event for line in capture.read_text().splitlines() for event in parser.feed(line)]
    assert any(event.kind == "session" for event in events)
    assert any(event.kind == "message" and event.text == "Native probe answer" for event in events)
    assert events[-1].kind == "result" and events[-1].data["ok"] is True
    assert parser.finish(0) == []


def test_qoder_stream_terminal_and_error_mapping():
    parser = QoderParser()
    # The installed Qoder 1.1.90 bundle defines this exact native result envelope.
    events = parser.feed(
        json.dumps(
            {
                "type": "result",
                "subtype": "error_during_execution",
                "is_error": True,
                "result": "Denied",
                "session_id": "native-session",
                "uuid": "fixture",
            }
        )
    )
    assert events[-1].kind == "result" and events[-1].data["ok"] is False
    assert parser.finish(1) == []


def test_completed_only_tool_never_publishes_a_running_item():
    from agent_sandbox.server.agents.redact import Redactor
    from agent_sandbox.server.agents.runtime import Session, Turn, _TurnBuilder

    session = Session("session", "test", 0)
    turn = Turn("turn", "session", "test", "probe")
    builder = _TurnBuilder(session, turn, Redactor(), "opencode")
    events = OpenCodeParser().feed(
        json.dumps(
            {
                "type": "tool_use",
                "part": {
                    "id": "tool",
                    "tool": "bash",
                    "state": {
                        "status": "completed",
                        "input": {"command": "true"},
                        "output": "done",
                        "time": {"start": 1000, "end": 1250},
                    },
                },
            }
        )
    )
    assert len(events) == 1 and events[0].kind == "tool_complete"
    builder.handle(events[0])
    emitted = session.events_after(0)
    assert [event.type for event in emitted] == ["item.added", "item.done"]
    assert all(event.data["item"]["status"] == "completed" for event in emitted)
    assert turn.items[0].data["duration_ms"] == 250
    assert turn.items[0].data["observation"] == "completed_only"
    assert builder._started_at == {}
