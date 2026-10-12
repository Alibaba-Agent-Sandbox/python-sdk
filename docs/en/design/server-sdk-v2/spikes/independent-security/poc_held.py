"""Attacks that were tried against the design/spike and HELD.  They must keep passing (run_all.py fails otherwise)."""
from __future__ import annotations

import http.client
import os
import shutil

from _common import *  # noqa: F403
from _common import (CommandScope, Denied, PathScope, Policy, Principal, REG, Server, check_command, filter_env,
                     mktree, open_beneath, ops, resolve_path, secure)
import ebxp.api as api


def held_path_variants():
    root = mktree()
    (root / "pub").mkdir()
    (root / "pub" / "a.txt").write_text("a")
    (root / "secret").write_text("s")
    scope = PathScope(str(root / "pub"))
    ok = resolve_path(scope, str(root / "pub") + "//./a.txt")
    secure(ok == str(root / "pub" / "a.txt"), "double slash / dot canonicalise")
    for evil in (str(root / "pub" / ".." / "secret"), "../secret", "a.txt/../../secret", "a\x00.txt", "x" * 5000,
                 str(root / "pub") + "/../pub/../secret"):
        try:
            resolve_path(scope, evil)
        except Denied:
            continue
        secure(False, f"path variant {evil[:30]!r} escaped")


def held_symlink_chain_and_dir_symlink():
    root, outside = mktree(), mktree()
    (outside / "k").write_text("K")
    os.symlink(outside, root / "d")                         # directory symlink out
    os.symlink(root / "d" / "k", root / "chain2")           # chain: chain2 -> d/k -> outside
    os.symlink(root / "chain2", root / "chain1")
    scope = PathScope(str(root))
    for p in ("d/k", "chain1", "chain2"):
        try:
            resolve_path(scope, p)
        except Denied:
            continue
        secure(False, f"symlink route {p} escaped")


def held_read_race_swap_is_caught_by_open_beneath():
    root, outside = mktree(), mktree()
    (outside / "k").write_text("K")
    (root / "d").mkdir()
    (root / "d" / "k").write_text("mine")
    scope = PathScope(str(root))
    real = resolve_path(scope, "d/k")
    shutil.rmtree(root / "d")
    os.symlink(outside, root / "d")
    try:
        fd = open_beneath(scope, real, os.O_RDONLY)
        os.close(fd)
    except Denied:
        return
    secure(False, "open_beneath followed a swapped directory symlink")


def held_write_swap_never_truncates_victim():
    root, outside = mktree(), mktree()
    victim = outside / "victim"
    victim.write_text("keep")
    (root / "f").write_text("x")
    scope = PathScope(str(root))
    real = resolve_path(scope, "f")
    os.unlink(root / "f")
    os.symlink(victim, root / "f")
    try:
        os.close(open_beneath(scope, real, os.O_WRONLY | os.O_CREAT | os.O_TRUNC))
    except Denied:
        pass
    secure(victim.read_text() == "keep", "victim was truncated through a swapped final symlink")


def held_typed_path_token_blocks_dash_traversal_and_symlinks():
    root, outside = mktree(), mktree()
    os.symlink(outside, root / "out")
    cs = CommandScope(allow=("ls {path}",), cwd=PathScope(str(root)), exec_dirs=("/usr/bin", "/bin"))
    for argv in (["ls", "--help"], ["ls", "-R"], ["ls", "../.."], ["ls", "out"], ["ls", "/etc"], ["ls", "a", "b"], ["ls"]):
        try:
            check_command(cs, None, argv)
        except Denied:
            continue
        secure(False, f"typed {{path}} admitted {argv}")


def held_exec_dir_tricks():
    cs = CommandScope(allow=("ls ...",), exec_dirs=("/usr/bin", "/bin"))
    for argv in (["/usr/bin/../../tmp/x"], ["./ls"], ["../ls"], ["/tmp/ls"], ["ls/../../tmp/x"]):
        try:
            check_command(cs, None, argv)
        except Denied:
            continue
        secure(False, f"executable trick {argv} admitted")


def held_env_and_shell_basics():
    cs = CommandScope(allow=("true",), env_set=("CI",))
    for k in ("LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS", "BASH_ENV", "GIT_SSH_COMMAND", "IFS", "FOO"):
        try:
            filter_env(cs, {k: "x"})
        except Denied:
            continue
        secure(False, f"env {k} accepted")
    try:
        check_command(cs, "true", None, shell=True)
    except Denied as exc:
        secure(exc.code == "policy.shell_not_allowed", "wrong code")
    else:
        secure(False, "shell=True admitted")


def held_allow_side_explicit_only_and_deny_precedence():
    for sel in ("agents.*", "agents.**", "group:agents", "effect:admin", "*", "core.*", "effect:net"):
        pol = Policy().allow(sel)
        for opid in ("agents.codex.install", "core.reload"):
            secure(not pol.mounted(REG.get(opid)), f"{sel} mounted explicit-only {opid}")
    root = mktree()
    pol = Policy().allow("files.stat", principals=["role:a"], paths=str(root)).deny("files.stat", principals=["id:bob"])
    st, _ = Server(pol).invoke("files.stat", {"path": str(root)}, Principal("bob", ("a",)))
    secure(st == 403, "deny with principals did not override")


def held_auth_before_404_and_size_cap_before_read():
    srv = api.SandboxServer(Policy().allow("core.health"), tokens={"tok": Principal("t", ("admin",))})
    httpd = api.start_http(srv)
    try:
        port = httpd.server_address[1]
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", "/definitely/not/a/route")
        secure(c.getresponse().status == 401, "unauthenticated unknown route did not answer 401")
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.putrequest("POST", "/ops/core.health")
        c.putheader("X-Access-Token", "tok")
        c.putheader("Content-Length", str(10 ** 12))
        c.endheaders()
        secure(c.getresponse().status == 413, "oversized Content-Length was not rejected before reading")
    finally:
        httpd.shutdown()


def held_hook_exception_fails_closed_and_narrow_only_tightens():
    root = mktree()
    (root / "a").write_text("x")
    pol = Policy().allow("files.stat", paths=str(root), authorize=lambda c: 1 / 0)
    secure(Server(pol).invoke("files.stat", {"path": "a"})[1].get("code") == "policy.hook_error", "hook exception allowed")
    from ebxp.policy import Limits, Narrow
    base = Limits(max_bytes=10)
    secure(base.narrowed(Limits(max_bytes=1000)).max_bytes == 10, "Narrow widened a limit")


CHECKS = [
    ("HELD-paths", held_path_variants),
    ("HELD-symlinks", held_symlink_chain_and_dir_symlink),
    ("HELD-read-race", held_read_race_swap_is_caught_by_open_beneath),
    ("HELD-write-race", held_write_swap_never_truncates_victim),
    ("HELD-typed-path", held_typed_path_token_blocks_dash_traversal_and_symlinks),
    ("HELD-exec-dir", held_exec_dir_tricks),
    ("HELD-env-shell", held_env_and_shell_basics),
    ("HELD-explicit-deny", held_allow_side_explicit_only_and_deny_precedence),
    ("HELD-auth-size", held_auth_before_404_and_size_cap_before_read),
    ("HELD-hook-limits", held_hook_exception_fails_closed_and_narrow_only_tightens),
]
