"""Matching client collection defaults and scalar compatibility contracts."""

from __future__ import annotations

from typing import List  # noqa: UP035

import pytest

from agent_sandbox.declarative.decorator import _annotation_to_type_str, _CommandArg
from agent_sandbox.utils.coerce import coerce_kwargs, parse_scalar


def test_typed_string_arrays_preserve_values_and_copy_callers() -> None:
    value = ["literal file.wav", "λ中文", "$(literal-only)"]
    converted = parse_scalar(value, "string_array")
    assert converted == value and converted is not value
    converted.append("new")
    assert len(value) == 3
    assert _annotation_to_type_str(list[str]) == "string_array"
    assert _annotation_to_type_str(List[str]) == "string_array"  # noqa: UP006


def test_array_default_json_is_decoded_per_call() -> None:
    args = [_CommandArg(name="args", type="string_array", default='["λ"]')]
    first = coerce_kwargs(args, {})
    first["args"].append("new")
    assert coerce_kwargs(args, {}) == {"args": ["λ"]}


@pytest.mark.parametrize("value", ["a", '["a"]', {"a": "b"}, [1], [True], None, [["a"]]])
def test_non_string_array_values_are_refused(value: object) -> None:
    with pytest.raises(ValueError):
        parse_scalar(value, "string_array")


def test_invalid_array_default_cannot_fall_back_to_a_scalar() -> None:
    args = [_CommandArg(name="args", type="string_array", default="not-json")]
    with pytest.raises(TypeError, match="string_array default"):
        coerce_kwargs(args, {})


def test_declarative_registration_keeps_array_annotation_and_json_default() -> None:
    from agent_sandbox.declarative.decorator import _SandboxFactory

    factory = _SandboxFactory()

    @factory.register
    def echo(args: list[str] = ["λ"]) -> list[str]:  # noqa: B006
        return args

    metadata = factory.list_registered()[0]["args"][0]
    assert metadata["type"] == "string_array"
    assert metadata["default"] == '["\\u03bb"]'
    assert coerce_kwargs(factory._registry["echo"].args, {}) == {"args": ["λ"]}


def test_declarative_none_array_default_is_rejected_on_all_python_versions() -> None:
    from agent_sandbox.declarative.decorator import _SandboxFactory

    factory = _SandboxFactory()
    with pytest.raises(ValueError, match="string_array default"):

        @factory.register
        def invalid(args: list[str] = None) -> list[str]:  # type: ignore[assignment]
            return args
