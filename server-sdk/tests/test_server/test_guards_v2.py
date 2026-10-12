"""Unit tests for ``easy_sandbox.server.guards`` (path and command guards, engine bridge)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from easy_sandbox.server import guard as legacy_guard
from easy_sandbox.server.guards import (
    SYSTEM_DENY,
    CommandGuard,
    PathGuard,
    check_command,
    command_guard,
    command_guard_from_context,
    expand_short_flags,
    path_guard,
    path_guard_from_context,
)
from easy_sandbox.server.policy import Identity, PolicyDenied, ServerPolicy

if TYPE_CHECKING:
    from pathlib import Path


def code_of(fn: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(PolicyDenied) as exc:
        fn(*args, **kwargs)  # type: ignore[operator]
    return exc.value.code


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    root = tmp_path / "scope"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("a")
    (root / ".env").write_text("secret")
    (root / "sub" / "key.pem").write_text("pem")
    (tmp_path / "outside.txt").write_text("o")
    return root


class TestPathGuard:
    def test_allowed_path_under_tmp_is_accepted(self, tmp_path: Path) -> None:
        # Only meaningful when /tmp is a plain directory (not a symlink to elsewhere).
        target = tmp_path / "a.txt"
        target.write_text("x")
        guard = path_guard("/tmp")
        assert guard.resolve("/tmp/some-new-file.txt", "write") == os.path.realpath(
            "/tmp/some-new-file.txt"
        )
        assert guard.permits("/tmp")
        if str(tmp_path).startswith("/tmp/"):
            assert guard.resolve(str(target)) == os.path.realpath(str(target))

    def test_denied_path_is_rejected(self, tmp_root: Path) -> None:
        guard = path_guard(str(tmp_root), deny=["**/.env", "*.pem"])
        assert code_of(guard.resolve, str(tmp_root / ".env")) == "path_denied"
        assert code_of(guard.resolve, str(tmp_root / "sub" / "key.pem")) == "path_denied"
        assert guard.resolve(str(tmp_root / "a.txt")) == os.path.realpath(tmp_root / "a.txt")

    def test_directory_deny_covers_subtree(self, tmp_root: Path) -> None:
        guard = path_guard(str(tmp_root), deny=[str(tmp_root / "sub")])
        assert code_of(guard.resolve, str(tmp_root / "sub" / "deep" / "x")) == "path_denied"
        assert code_of(guard.resolve, str(tmp_root / "sub")) == "path_denied"

    def test_outside_root_and_traversal_are_rejected(self, tmp_root: Path) -> None:
        guard = path_guard(str(tmp_root))
        assert code_of(guard.resolve, str(tmp_root.parent / "outside.txt")) == "path_not_allowed"
        assert code_of(guard.resolve, str(tmp_root / ".." / "outside.txt")) == "path_not_allowed"
        assert code_of(guard.resolve, "../outside.txt") == "path_not_allowed"

    def test_symlink_escape_is_rejected(self, tmp_root: Path) -> None:
        (tmp_root / "link").symlink_to(tmp_root.parent / "outside.txt")
        assert code_of(path_guard(str(tmp_root)).resolve, str(tmp_root / "link")) == (
            "path_not_allowed"
        )

    def test_readonly_refuses_mutation_only(self, tmp_root: Path) -> None:
        guard = path_guard(str(tmp_root), readonly=True)
        target = str(tmp_root / "a.txt")
        assert guard.resolve(target, "read")
        assert code_of(guard.resolve, target, "write") == "read_only"
        assert code_of(guard.resolve, target, "delete") == "read_only"

    @pytest.mark.parametrize("bad", ["\x00", "", 5, None, "x" * 5000])
    def test_invalid_input(self, tmp_root: Path, bad: object) -> None:
        assert code_of(path_guard(str(tmp_root)).resolve, bad) == "invalid_path"

    @pytest.mark.parametrize("system", SYSTEM_DENY)
    def test_system_dirs_are_never_reachable(self, system: str) -> None:
        assert code_of(path_guard(system).resolve, system) == "path_denied"

    def test_proc_denied_even_under_broad_root(self, tmp_root: Path) -> None:
        guard = path_guard(str(tmp_root), deny=[])
        assert "/proc" in guard.deny

    @pytest.mark.parametrize("root", ["/", "relative/dir", "/tmp/*", "/tmp/a[b]"])
    def test_bad_roots_are_refused(self, root: str) -> None:
        with pytest.raises(ValueError):
            path_guard(root)

    def test_no_root_is_refused(self) -> None:
        with pytest.raises(ValueError):
            path_guard()

    def test_v1_names_are_reexported(self) -> None:
        assert PathGuard is legacy_guard.PathGuard
        assert legacy_guard.open_checked is not None


class TestCommandGuard:
    def test_denied_command_is_rejected(self) -> None:
        guard = CommandGuard(deny=["rm", "/usr/bin/dd"])
        assert code_of(guard.check, ["rm", "-rf", "x"]) == "command_denied"
        assert code_of(guard.check, ["/bin/rm", "x"]) == "command_denied"
        assert code_of(guard.check, ["/usr/bin/dd", "if=/dev/zero"]) == "command_denied"
        assert guard.check(["ls"]) == ["ls"]

    def test_legacy_codes_keep_v1_deny_code(self) -> None:
        guard = CommandGuard(deny=["rm"], legacy_codes=True)
        assert code_of(guard.check, ["rm"]) == "command_not_allowed"

    def test_allow_list_executable_only(self) -> None:
        guard = CommandGuard(allow=["ls", "cat"])
        assert guard.check(["ls", "-la", "/tmp"]) == ["ls", "-la", "/tmp"]
        assert guard.check(["/bin/cat", "f"]) == ["/bin/cat", "f"]
        assert code_of(guard.check, ["rm", "f"]) == "command_not_allowed"

    def test_deny_beats_allow(self) -> None:
        guard = CommandGuard(allow=["git *"], deny=["git push ..."])
        assert guard.permits(["git", "status"])
        assert not guard.permits(["git", "push", "origin"])

    def test_empty_allow_semantics(self) -> None:
        assert CommandGuard().check(["anything"]) == ["anything"]
        assert code_of(command_guard().check, ["anything"]) == "scope_required"

    def test_argv_pattern_pins_arguments(self) -> None:
        guard = CommandGuard(allow=["python3 /workspace/grade.py", "pytest -q {word}"])
        assert guard.permits(["python3", "/workspace/grade.py"])
        assert not guard.permits(["python3", "/workspace/grade.py", "--extra"])
        assert not guard.permits(["python3", "-c", "print(1)"])
        assert guard.permits(["pytest", "-q", "tests"])
        assert not guard.permits(["pytest", "-q", "../x"])

    def test_ellipsis_and_int(self) -> None:
        guard = CommandGuard(allow=["head -n {int} ..."])
        assert guard.permits(["head", "-n", "5", "a", "b"])
        assert not guard.permits(["head", "-n", "five", "a"])

    def test_glob_argument_never_crosses_slash_dotdot_or_dash(self) -> None:
        guard = CommandGuard(allow=["cat *.txt"])
        assert guard.permits(["cat", "a.txt"])
        assert not guard.permits(["cat", "/etc/x.txt"])
        assert not guard.permits(["cat", "../x.txt"])
        assert not guard.permits(["cat", "-x.txt"])

    def test_short_flag_alias_cannot_bypass_deny(self) -> None:
        assert expand_short_flags(["ls", "-lR", "--all", "-a"]) == ["ls", "-l", "-R", "--all", "-a"]
        guard = CommandGuard(allow=["ls ..."], deny=["ls ... -R ..."])
        assert not guard.permits(["ls", "-R"])
        assert not guard.permits(["ls", "-lR"])
        assert guard.permits(["ls", "-l"])

    def test_path_token_is_canonicalised_through_scope(self, tmp_root: Path) -> None:
        scope = path_guard(str(tmp_root), deny=["**/.env"])
        guard = CommandGuard(allow=["cat {path}"], path_guard=scope)
        assert guard.check(["cat", "a.txt"]) == ["cat", os.path.realpath(tmp_root / "a.txt")]
        assert code_of(guard.check, ["cat", "/etc/passwd"]) == "path_not_allowed"
        assert code_of(guard.check, ["cat", str(tmp_root / ".env")]) == "path_denied"
        assert not guard.permits(["cat", "-n"])

    def test_path_token_without_scope_never_matches(self) -> None:
        assert not CommandGuard(allow=["cat {path}"]).permits(["cat", "/tmp/a"])

    def test_shell_requires_grant(self) -> None:
        assert code_of(CommandGuard().check, ["sh", "-c", "id"], shell=True) == (
            "shell_not_allowed"
        )
        assert CommandGuard(shell=True).check(["sh", "-c", "id"], shell=True)

    def test_normalise_is_xor_and_validates(self) -> None:
        assert CommandGuard.normalise(command="ls -l 'a b'") == ["ls", "-l", "a b"]
        assert CommandGuard.normalise(argv=["ls", "x"]) == ["ls", "x"]
        for kwargs in (
            {},
            {"command": "ls", "argv": ["ls"]},
            {"command": "ls 'unterminated"},
            {"command": 5},
            {"argv": []},
            {"argv": ["ls", 1]},
            {"argv": ["ls\x00"]},
            {"argv": [""]},
        ):
            with pytest.raises(PolicyDenied) as exc:
                CommandGuard.normalise(**kwargs)  # type: ignore[arg-type]
            assert exc.value.code == "command_invalid"
            assert exc.value.status == 400

    def test_bad_patterns_are_refused(self) -> None:
        with pytest.raises(ValueError):
            CommandGuard(allow=[""])
        with pytest.raises(ValueError):
            CommandGuard(allow=["a ... b ... c ... d ... e"])

    def test_adversarial_ellipses_terminate(self) -> None:
        guard = CommandGuard(allow=["x ... a ... a ... a"])
        assert not guard.permits(["x", *["a"] * 2, *["b"] * 200])


class TestEngineBridge:
    @pytest.fixture
    def ctx(self, tmp_root: Path):  # type: ignore[no-untyped-def]
        policy = ServerPolicy.from_dict(
            {
                "endpoints": {
                    "shell": {
                        "paths": {"allow": [str(tmp_root)], "deny": ["**/.env"]},
                        "params": {"allow_commands": ["ls", "cat"], "deny_commands": ["cat"]},
                    }
                }
            }
        )
        engine = policy.bind()
        route = engine._routes["shell"]
        context, release = engine.admit(route, Identity("t", frozenset({"*"})))
        yield context
        release()

    def test_path_guard_from_engine_context(self, ctx, tmp_root: Path) -> None:  # type: ignore[no-untyped-def]
        guard = path_guard_from_context(ctx)
        assert guard.resolve(str(tmp_root / "a.txt"))
        assert code_of(guard.resolve, str(tmp_root / ".env")) == "path_denied"
        assert code_of(guard.resolve, "/etc/passwd") == "path_not_allowed"
        assert code_of(guard.resolve, "/proc/self/environ") == "path_not_allowed"

    def test_command_guard_from_engine_context(self, ctx) -> None:  # type: ignore[no-untyped-def]
        guard = command_guard_from_context(ctx)
        assert guard.check(["ls", "-la"]) == ["ls", "-la"]
        assert code_of(check_command, ctx, ["cat", "x"]) == "command_not_allowed"
        assert code_of(check_command, ctx, ["rm", "x"]) == "command_not_allowed"

    def test_matches_v1_check_command(self, ctx) -> None:  # type: ignore[no-untyped-def]
        from easy_sandbox.server.routes import _check_command

        for argv in (["ls"], ["cat", "x"], ["/bin/ls", "-l"], ["rm"], ["/usr/bin/cat"]):
            try:
                _check_command(ctx, argv)
                v1 = "ok"
            except PolicyDenied as exc:
                v1 = exc.code
            try:
                check_command(ctx, argv)
                v2 = "ok"
            except PolicyDenied as exc:
                v2 = exc.code
            assert v1 == v2, argv


def test_route_helpers_deny_and_allow_under_tmp() -> None:
    """Denied path and command fail through the route helpers; /tmp calls still succeed."""
    import tempfile
    from pathlib import Path

    from easy_sandbox.server.routes import enforce_exec_policy, handle_download

    with tempfile.TemporaryDirectory(prefix="ebx-guard-", dir="/tmp") as raw:
        work = Path(raw)
        note = work / "note.txt"
        note.write_text("hello")
        secret = work / ".env"
        secret.write_text("nope")
        policy = ServerPolicy.from_dict(
            {
                "endpoints": {
                    "download": {"paths": {"allow": ["/tmp"], "deny": ["**/.env"]}},
                    "shell": {
                        "paths": {"allow": ["/tmp"], "deny": ["**/.env"]},
                        "params": {
                            "allow_commands": ["true", "echo"],
                            "deny_commands": ["rm"],
                        },
                    },
                }
            }
        )
        engine = policy.bind()
        download_ctx, release_download = engine.admit(
            engine._routes["download"], Identity("t", frozenset({"*"}))
        )
        shell_ctx, release_shell = engine.admit(
            engine._routes["shell"], Identity("t", frozenset({"*"}))
        )
        try:
            status, body = handle_download(str(note), download_ctx)
            assert status == 200
            assert body["path"] == os.path.realpath(note)

            with pytest.raises(PolicyDenied) as denied_path:
                handle_download(str(secret), download_ctx)
            assert denied_path.value.code == "path_denied"
            assert denied_path.value.status == 403
            assert denied_path.value.message == "Path is denied by policy"

            cwd, _timeout, _env = enforce_exec_policy(shell_ctx, ["true"], {"cwd": str(work)})
            assert cwd == os.path.realpath(work)

            with pytest.raises(PolicyDenied) as denied_cmd:
                enforce_exec_policy(shell_ctx, ["rm", "-rf", str(work)], {})
            assert denied_cmd.value.code == "command_not_allowed"
            assert denied_cmd.value.status == 403
            assert denied_cmd.value.message == "Command 'rm' is denied by policy"
        finally:
            release_download()
            release_shell()
