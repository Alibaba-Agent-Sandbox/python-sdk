"""Unit tests for :class:`PathGuard` and :func:`open_checked` (bypass matrix, path part)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from agent_sandbox.server.guard import PathGuard, open_checked
from agent_sandbox.server.policy import PolicyDenied

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "out" / "sub").mkdir(parents=True)
    (root / "outsider").mkdir()
    (root / "out" / "a.txt").write_text("a")
    (root / "out" / ".env").write_text("secret")
    (root / "out" / "sub" / "key.pem").write_text("pem")
    (tmp_path / "outside.txt").write_text("o")
    (tmp_path / "outside_dir").mkdir()
    (tmp_path / "outside_dir" / "x.txt").write_text("x")
    return root


def guard(tree: Path, **kw: object) -> PathGuard:
    kw.setdefault("allow", [str(tree / "out")])
    return PathGuard(str(tree), **kw)  # type: ignore[arg-type]


def code_of(g: PathGuard, raw: object, op: str = "read") -> str:
    with pytest.raises(PolicyDenied) as exc:
        g.resolve(raw, op)
    return exc.value.code


class TestBoundary:
    def test_allows_inside(self, tree: Path) -> None:
        assert guard(tree).resolve(str(tree / "out" / "a.txt")) == str(tree / "out" / "a.txt")

    def test_allow_root_itself(self, tree: Path) -> None:
        assert guard(tree).resolve(str(tree / "out")) == str(tree / "out")

    def test_base_dir_used_when_no_allow(self, tree: Path) -> None:
        g = PathGuard(str(tree))
        assert g.resolve(str(tree / "outsider")) == str(tree / "outsider")
        assert code_of(g, str(tree.parent / "outside.txt")) == "path_not_allowed"

    def test_allow_replaces_base_dir(self, tree: Path) -> None:
        g = guard(tree)
        assert code_of(g, str(tree / "outsider")) == "path_not_allowed"

    @pytest.mark.parametrize(
        "suffix",
        ["../outsider", "sub/../../outsider", "./../outsider", "sub/../../../outside.txt"],
    )
    def test_dotdot_traversal(self, tree: Path, suffix: str) -> None:
        assert code_of(guard(tree), str(tree / "out" / suffix)) == "path_not_allowed"

    def test_sibling_prefix_is_not_inside(self, tree: Path) -> None:
        # /root/outsider starts with /root/out but is a different directory.
        assert code_of(guard(tree), str(tree / "outsider" / "x")) == "path_not_allowed"

    def test_double_slashes_and_trailing(self, tree: Path) -> None:
        g = guard(tree)
        assert g.resolve(f"{tree}//out///a.txt/") == str(tree / "out" / "a.txt")
        assert code_of(g, f"{tree}//out//..//outsider") == "path_not_allowed"

    def test_percent_encoding_is_literal(self, tree: Path) -> None:
        # The guard never URL-decodes: "%2e%2e" is a literal (non-existent) directory name.
        resolved = guard(tree).resolve(str(tree / "out" / "%2e%2e" / "x"))
        assert resolved == str(tree / "out" / "%2e%2e" / "x")

    def test_unicode_lookalike_is_a_different_file(self, tree: Path) -> None:
        g = guard(tree, deny=[".env"])
        lookalike = str(tree / "out" / ".\u0435nv")  # Cyrillic e
        assert g.resolve(lookalike) == lookalike

    @pytest.mark.parametrize("raw", [None, "", 5, b"/x", ["a"]])
    def test_invalid_input(self, tree: Path, raw: object) -> None:
        assert code_of(guard(tree), raw) == "invalid_path"

    def test_nul_byte(self, tree: Path) -> None:
        assert code_of(guard(tree), str(tree / "out") + "\x00/../x") == "invalid_path"

    def test_too_long(self, tree: Path) -> None:
        assert code_of(guard(tree), str(tree / "out") + "/" + "a" * 5000) == "invalid_path"

    def test_relative_resolves_against_first_allow_root(self, tree: Path) -> None:
        g = guard(tree, relative_to_root=True)
        assert g.resolve("a.txt") == str(tree / "out" / "a.txt")
        assert code_of(g, "../outsider") == "path_not_allowed"

    def test_relative_legacy_uses_cwd(self, tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tree / "out")
        g = PathGuard(str(tree), relative_to_root=False)
        assert g.resolve("a.txt") == str(tree / "out" / "a.txt")

    def test_multiple_allow_roots(self, tree: Path) -> None:
        g = PathGuard(str(tree), allow=[str(tree / "out"), str(tree / "outsider")])
        assert g.permits(str(tree / "outsider"))
        assert g.permits(str(tree / "out" / "a.txt"))
        assert not g.permits(str(tree.parent / "outside.txt"))


class TestSymlinks:
    def test_symlink_escape_to_outside_file(self, tree: Path) -> None:
        os.symlink(tree.parent / "outside.txt", tree / "out" / "link")
        assert code_of(guard(tree), str(tree / "out" / "link")) == "path_not_allowed"

    def test_symlink_escape_to_outside_dir(self, tree: Path) -> None:
        os.symlink(tree.parent / "outside_dir", tree / "out" / "dirlink")
        assert code_of(guard(tree), str(tree / "out" / "dirlink" / "x.txt")) == "path_not_allowed"

    def test_symlink_inside_boundary_allowed_by_default(self, tree: Path) -> None:
        os.symlink(tree / "out" / "a.txt", tree / "out" / "alias")
        assert guard(tree).resolve(str(tree / "out" / "alias")) == str(tree / "out" / "a.txt")

    def test_symlink_never_rejects_inside_alias(self, tree: Path) -> None:
        os.symlink(tree / "out" / "a.txt", tree / "out" / "alias")
        g = guard(tree, symlinks="never")
        assert code_of(g, str(tree / "out" / "alias")) == "symlink_denied"
        assert g.resolve(str(tree / "out" / "a.txt")) == str(tree / "out" / "a.txt")

    def test_symlink_never_rejects_dir_component(self, tree: Path) -> None:
        os.symlink(tree / "out" / "sub", tree / "out" / "subalias")
        g = guard(tree, symlinks="never")
        assert code_of(g, str(tree / "out" / "subalias" / "key.pem")) == "symlink_denied"

    def test_symlink_never_works_when_root_path_contains_symlink(self, tree: Path) -> None:
        alias_root = tree.parent / "rootalias"
        os.symlink(tree, alias_root)
        g = PathGuard(str(alias_root), allow=[str(alias_root / "out")], symlinks="never")
        assert g.resolve(str(alias_root / "out" / "a.txt")).endswith("out/a.txt")

    def test_symlink_to_denied_target(self, tree: Path) -> None:
        os.symlink(tree / "out" / ".env", tree / "out" / "innocent")
        g = guard(tree, deny=["**/.env"])
        assert code_of(g, str(tree / "out" / "innocent")) == "path_denied"


class TestDeny:
    @pytest.mark.parametrize(
        ("pattern", "path", "denied"),
        [
            (".env", "out/.env", True),
            (".env", "out/a.txt", False),
            ("*.pem", "out/sub/key.pem", True),
            ("*.pem", "out/sub/key.pem.bak", False),
            ("**/.env", "out/.env", True),
            ("**/.env*", "out/.env", True),
            ("sub", "out/sub/key.pem", True),
            ("out/sub", "out/sub/key.pem", True),
            ("**/sub", "out/sub/key.pem", True),
            ("sub/*.pem", "out/sub/key.pem", True),
            ("SUB", "out/sub/key.pem", False),
            (".ENV", "out/.env", False),
            ("a.tx", "out/a.txt", False),
        ],
    )
    def test_relative_patterns(self, tree: Path, pattern: str, path: str, denied: bool) -> None:
        g = guard(tree, deny=[pattern])
        assert g.permits(str(tree / path)) is not denied

    def test_absolute_directory_prefix(self, tree: Path) -> None:
        g = guard(tree, deny=[str(tree / "out" / "sub")])
        assert not g.permits(str(tree / "out" / "sub"))
        assert not g.permits(str(tree / "out" / "sub" / "key.pem"))
        assert g.permits(str(tree / "out" / "a.txt"))

    def test_absolute_prefix_is_not_substring(self, tree: Path) -> None:
        (tree / "out" / "subx").mkdir()
        g = guard(tree, deny=[str(tree / "out" / "sub")])
        assert g.permits(str(tree / "out" / "subx"))

    def test_deny_wins_over_allow(self, tree: Path) -> None:
        g = guard(tree, deny=["*.txt"])
        assert code_of(g, str(tree / "out" / "a.txt")) == "path_denied"

    def test_dotdot_cannot_hide_denied_file(self, tree: Path) -> None:
        g = guard(tree, deny=[".env"])
        assert code_of(g, str(tree / "out" / "sub" / ".." / ".env")) == "path_denied"

    def test_deny_is_checked_on_directories_for_children(self, tree: Path) -> None:
        g = guard(tree, deny=["sub"])
        assert code_of(g, str(tree / "out" / "sub" / "deeper" / "x")) == "path_denied"


class TestReadOnly:
    def test_read_only_blocks_mutations_only(self, tree: Path) -> None:
        g = guard(tree, read_only=True)
        p = str(tree / "out" / "a.txt")
        assert g.resolve(p, "read") == p
        assert g.resolve(p, "exec") == p
        assert code_of(g, p, "write") == "read_only"
        assert code_of(g, p, "delete") == "read_only"

    def test_policy_check_precedes_existence(self, tree: Path) -> None:
        g = guard(tree)
        outside_missing = str(tree.parent / "no-such-file")
        outside_present = str(tree.parent / "outside.txt")
        assert code_of(g, outside_missing) == code_of(g, outside_present) == "path_not_allowed"


class TestOpenChecked:
    def test_opens_regular_file(self, tree: Path) -> None:
        g = guard(tree)
        p = g.resolve(str(tree / "out" / "a.txt"))
        fd = open_checked(g, p, os.O_RDONLY, "read")
        try:
            assert os.read(fd, 10) == b"a"
        finally:
            os.close(fd)

    def test_final_component_swapped_to_symlink_is_refused(self, tree: Path) -> None:
        g = guard(tree)
        p = g.resolve(str(tree / "out" / "a.txt"))
        os.remove(p)
        os.symlink(tree.parent / "outside.txt", p)
        with pytest.raises(PolicyDenied) as exc:
            open_checked(g, p, os.O_RDONLY, "read")
        assert exc.value.code == "symlink_denied"

    def test_exclusive_create_reports_exists(self, tree: Path) -> None:
        g = guard(tree)
        p = g.resolve(str(tree / "out" / "a.txt"))
        with pytest.raises(FileExistsError):
            open_checked(g, p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, "write")

    def test_creates_new_file(self, tree: Path) -> None:
        g = guard(tree)
        p = g.resolve(str(tree / "out" / "new.txt"))
        fd = open_checked(g, p, os.O_WRONLY | os.O_CREAT, "write")
        os.close(fd)
        assert (tree / "out" / "new.txt").exists()
