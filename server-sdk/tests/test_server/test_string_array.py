"""Actual HTTP collection contract; no mocked request or transport."""

from __future__ import annotations

from typing import Any

import pytest

from agent_sandbox.server.registry import CommandArg, CommandRegistry


def test_native_json_array_roundtrip_keeps_elements_and_metadata(live_server: Any) -> None:
    registry = CommandRegistry()

    @registry.command("argv")
    def argv(args: list[str]) -> list[str]:
        return args

    server = live_server(registry=registry)
    value = ["-i", "literal file.wav", "λ中文", "$(literal-only)", "--flag"]
    status, body, _ = server.request("POST", "/commands/argv", {"args": value})
    assert status == 200 and body == {"result": value}
    status, listing, _ = server.request("GET", "/commands")
    assert status == 200
    metadata = next(item for item in listing["commands"] if item["name"] == "argv")
    assert metadata["args"][0]["type"] == "string_array"


@pytest.mark.parametrize("value", ["a", '["a"]', {"a": "b"}, [1], [True], None, [["a"]]])
def test_non_string_arrays_fail400_without_calling_function(live_server: Any, value: Any) -> None:
    registry = CommandRegistry()
    calls: list[list[str]] = []

    @registry.command("argv")
    def argv(args: list[str]) -> int:
        calls.append(args)
        return len(args)

    server = live_server(registry=registry)
    status, _, _ = server.request("POST", "/commands/argv", {"args": value})
    assert status == 400 and calls == []
    status, _, _ = server.request("POST", "/commands/argv", {})
    assert status == 400 and calls == []


def test_array_default_is_json_and_copied_for_each_request(live_server: Any) -> None:
    registry = CommandRegistry()

    @registry.command("defaults")
    def defaults(args: list[str] = ["seed"]) -> list[str]:  # noqa: B006
        args.append("new")
        return args

    server = live_server(registry=registry)
    for _ in range(2):
        status, body, _ = server.request("POST", "/commands/defaults", {})
        assert status == 200 and body == {"result": ["seed", "new"]}
    command = registry.get("defaults")
    assert command is not None and command.args[0].default == '["seed"]'


@pytest.mark.parametrize("default", ["not-json", "{}", "[1]", "[true]", "null"])
def test_invalid_declared_array_default_refused_at_registration(default: str) -> None:
    with pytest.raises(ValueError):
        CommandArg(name="args", type="string_array", default=default)


def test_annotated_array_none_default_is_invalid() -> None:
    registry = CommandRegistry()
    with pytest.raises(ValueError, match="string_array default"):

        @registry.command("invalid_default")
        def invalid_default(args: list[str] = None) -> list[str]:  # type: ignore[assignment]
            return args
