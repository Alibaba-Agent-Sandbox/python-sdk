"""Unit tests of the operation model: ID grammar, ``ops`` tree, registry rules (design 02)."""

from __future__ import annotations

from typing import Any

import pytest

from easy_sandbox.server.core import OpRef, OpTree, Registry, RegistryFrozen, ops
from easy_sandbox.server.core.ids import is_valid_id, mangle_custom_name, validate_id


class TestIdGrammar:
    @pytest.mark.parametrize(
        "op_id",
        [
            "files.list",
            "system.env.get",
            "agents.codex.sessions.create",
            "agents.sessions.subagents.turns.list",
            "custom.a_1",
        ],
    )
    def test_valid(self, op_id: str) -> None:
        assert is_valid_id(op_id)
        assert validate_id(op_id) == op_id

    @pytest.mark.parametrize(
        "op_id",
        [
            "files",
            "Files.list",
            "files.List",
            "files.list-all",
            "files..list",
            ".files.list",
            "files.list.",
            "1files.list",
            "a.b.c.d.e.f",
            "files list",
            "",
            None,
        ],
    )
    def test_invalid(self, op_id: Any) -> None:
        assert not is_valid_id(op_id)
        with pytest.raises(ValueError, match="invalid operation id"):
            validate_id(op_id)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Hello-World.v2", "custom.hello_world_v2"),
            ("greet", "custom.greet"),
            ("a--b", "custom.a_b"),
            ("2fast", "custom.c_2fast"),
            ("_x", "custom.c__x"),
            ("---", "custom.c__"),
        ],
    )
    def test_custom_name_mangling(self, name: str, expected: str) -> None:
        assert mangle_custom_name(name) == expected
        assert is_valid_id(expected)


class TestOpRefTree:
    def test_attribute_and_item_access(self) -> None:
        assert str(ops.files.list) == "files.list"
        assert str(ops.agents.codex.sessions.create) == "agents.codex.sessions.create"
        assert str(ops.custom["format"]) == "custom.format"
        assert repr(ops.files.list) == "ops.files.list"

    def test_str_methods_do_not_shadow_verbs(self) -> None:
        for verb in ("format", "split", "index", "replace", "count"):
            node = getattr(ops.custom, verb)
            assert isinstance(node, OpRef)
            assert str(node) == f"custom.{verb}"

    def test_equality_and_hash_with_strings(self) -> None:
        assert ops.files.list == "files.list"
        assert ops.files.list == ops.files.list
        assert ops.files.list != ops.files.stat
        assert hash(ops.files.list) == hash("files.list")
        assert {ops.files.list: 1}["files.list"] == 1

    def test_not_a_str_and_immutable(self) -> None:
        assert not isinstance(ops.files.list, str)
        assert isinstance(ops, OpTree)
        with pytest.raises(AttributeError):
            ops.files.list.x = 1  # type: ignore[attr-defined]
        with pytest.raises(AttributeError):
            _ = ops._private


class TestRegistryRules:
    def test_prefix_rule_both_directions(self) -> None:
        reg = Registry()
        reg.op("system.env.get", effects="read")(lambda: None)
        with pytest.raises(ValueError, match="prefix"):
            reg.op("system.env", effects="read")(lambda: None)
        reg.op("files.list", effects="read")(lambda: None)
        with pytest.raises(ValueError, match="prefix"):
            reg.op("files.list.more", effects="read")(lambda: None)

    def test_duplicate_id(self) -> None:
        reg = Registry()
        reg.op("files.list", effects="read")(lambda: None)
        with pytest.raises(ValueError, match="duplicate"):
            reg.op("files.list", effects="read")(lambda: None)

    def test_freeze_blocks_registration(self) -> None:
        reg = Registry()
        reg.freeze()
        with pytest.raises(RegistryFrozen, match="register ops before constructing the server"):
            reg.op("files.list", effects="read")(lambda: None)

    def test_omitted_effects_default_to_explicit_only_admin(self) -> None:
        reg = Registry()

        @reg.op("custom.grade")
        def grade(ctx: Any, submission: str) -> dict[str, str]:
            return {"s": submission}

        operation = reg.get("custom.grade")
        assert operation is not None
        assert operation.effects == frozenset({"admin"})
        assert operation.explicit
        assert any("custom.grade" in line for line in reg.lint())

    def test_declared_effects_are_validated(self) -> None:
        with pytest.raises(ValueError, match="unknown effects"):
            Registry().op("custom.x", effects="telepathy")

    def test_schema_from_annotations(self) -> None:
        reg = Registry()

        @reg.op("custom.shape", effects="read")
        def shape(
            ctx: Any, name: str, count: int = 3, flag: bool = False, tags: list[str] | None = None
        ) -> None:
            return None

        operation = reg.get("custom.shape")
        assert operation is not None and operation.wants_ctx
        schema = {p.name: (p.type, p.required) for p in operation.params}
        assert schema == {
            "name": ("string", True),
            "count": ("integer", False),
            "flag": ("boolean", False),
            "tags": ("array", False),
        }

    def test_declared_paths_must_be_parameters(self) -> None:
        reg = Registry()
        with pytest.raises(ValueError, match="unknown parameter"):
            reg.op("custom.p", effects="read", paths=("nope",))(lambda ctx, path="x": None)

    def test_aliases_resolve_but_are_never_ids(self) -> None:
        reg = Registry()
        reg.op("files.list", effects="read", aliases=("files_list",))(lambda: None)
        assert reg.resolve("files_list") is reg.get("files.list")
        assert reg.get("files_list") is None
        assert "files_list" in reg
        with pytest.raises(ValueError, match="already taken"):
            reg.op("files.stat", effects="read", aliases=("files_list",))(lambda: None)

    def test_child_registry_is_independent(self) -> None:
        parent = Registry()
        parent.op("files.list", effects="read")(lambda: None)
        child = parent.child()
        child.op("files.stat", effects="read")(lambda: None)
        assert "files.stat" in child and "files.stat" not in parent
        parent.freeze()
        child.op("files.mkdir", effects="write")(lambda: None)

    def test_describe_selectors(self) -> None:
        reg = Registry()
        for op_id in ("files.list", "files.stat", "agents.sessions.create", "agents.codex.run"):
            reg.op(op_id, effects="read")(lambda: None)
        ids = lambda *s: [e["id"] for e in reg.describe(*s)]  # noqa: E731
        assert ids() == ["agents.codex.run", "agents.sessions.create", "files.list", "files.stat"]
        assert ids("files.*") == ["files.list", "files.stat"]
        assert ids("agents.*") == []
        assert ids("agents.**") == ["agents.codex.run", "agents.sessions.create"]
        assert ids(ops.files.list) == ["files.list"]
        assert ids("*") == ids()

    def test_namespaces_and_catalog(self) -> None:
        reg = Registry()
        reg.op("files.list", effects="read")(lambda: None)
        reg.op("system.env.get", effects="read")(lambda: None)
        assert reg.namespaces() == {"files": ["files.list"], "system.env": ["system.env.get"]}
        catalog = reg.catalog()
        assert catalog["catalog_version"] == 1 and catalog["api"] == "easy-sandbox/2"
        assert [e["id"] for e in catalog["ops"]] == ["files.list", "system.env.get"]
        assert catalog["ops"][0]["rpc"] == "/ops/files.list"
