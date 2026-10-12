"""PoCs: path scoping and file operations (03 section 6, 04 section 4)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading

from _common import *  # noqa: F403
from _common import Denied, PathScope, Policy, Principal, REG, SPIKES, Server, mktree, secure
from ebxp.server import Ctx


def is_p1c_bare_files_allow_has_no_defined_jail():
    """IS-P1: allow(files.download) with no paths= must be refused/jailed; it must not mean '/' or crash."""
    pol = Policy().allow("files.download")
    try:
        st, _ = Server(pol).invoke("files.download", {"path": "/etc/hostname"})
    except Exception as exc:  # KeyError in the reference: semantics are simply undefined
        secure(False, f"allow(files.download) without paths= is undefined behaviour ({type(exc).__name__}); "
                      "an implementation that 'fixes' the crash by passing the path through is a full-filesystem read")
    secure(st == 403, f"allow(files.download) without paths= answered HTTP {st}")


def is_f1_readonly_preset_default_root_exposes_proc_environ():
    """IS-F1: no preset may default to '/', and even an explicit whole-filesystem scope must not reach /proc."""
    import ebxp.api as api
    try:
        api.presets.readonly()
    except (TypeError, ValueError):
        pass
    else:
        secure(False, "presets.readonly() with no root is accepted (the old default was '/')")
    try:
        PathScope("/")
    except ValueError:
        pass
    else:
        secure(False, "PathScope('/') is accepted")
    pol = api.presets.readonly(PathScope.anywhere(unsafe=True))      # the loudest possible opt-in
    st, body = Server(pol).invoke("files.download", {"path": "/proc/self/environ"})
    secure(st == 403 and "content_base64" not in body,
           "role with a whole-filesystem readonly scope read /proc/self/environ (contains every token_env secret)")
    st, _ = Server(pol).invoke("files.download", {"path": "/proc/1/../self/environ"})
    secure(st == 403, "dot-dot route into /proc/self/environ was served")


def is_f2_delete_follows_a_parent_swapped_after_admission():
    """IS-F2: handlers for delete/move/mkdir/list use path-based syscalls on the canonical string (no *at())."""
    root, outside = mktree(), mktree()
    (outside / "victim").write_text("keep me")
    (root / "d").mkdir()
    (root / "d" / "victim").write_text("mine")
    pol = Policy().allow("files.delete", paths=PathScope(str(root)))
    op = REG.get("files.delete")
    target = str(root / "d" / "victim")
    decision = pol.decide(op, {"path": target}, Principal())
    secure(decision.allowed, "baseline admission")
    shutil.rmtree(root / "d")                  # the racing actor: swap the admitted parent for a symlink
    os.symlink(outside, root / "d")
    try:
        op.handler(Ctx(decision, None, op), path=target)
    except Denied:
        pass                                                      # spike: *at() walk with O_NOFOLLOW refuses the swapped parent
    secure((outside / "victim").exists(), "files.delete unlinked a file OUTSIDE the root: admission was by string, use by path")


def is_f4_reading_a_fifo_blocks_a_request_thread_forever():
    """IS-F4: non-regular files are only refused for writes; a read open() of a FIFO never returns."""
    root = mktree()
    fifo = root / "pipe"
    os.mkfifo(fifo)
    srv = Server(Policy().allow("files.download", paths=PathScope(str(root))))
    box = {}
    t = threading.Thread(target=lambda: box.setdefault("r", srv.invoke("files.download", {"path": str(fifo)})), daemon=True)
    t.start()
    t.join(2.0)
    blocked = t.is_alive()
    if blocked:
        try:
            fd = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
            os.close(fd)
        except OSError:
            pass
        t.join(2.0)
    secure(not blocked, "files.download of a FIFO inside the scope held a server thread indefinitely (64 of these = outage)")


def is_f5_hardlink_defeats_deny_globs():
    """IS-F5 (documented limit, mitigation proposed): hardlink to a denied file readable under another name."""
    root = mktree()
    (root / ".env").write_text("SECRET")
    os.link(root / ".env", root / "notes.txt")
    srv = Server(Policy().allow("files.download", paths=PathScope(str(root), deny=("**/.env",))))
    st, body = srv.invoke("files.download", {"path": "notes.txt"})
    secure(st == 403, "hardlink `notes.txt` -> `.env` is served although `**/.env` is denied (st_nlink>1 is never checked)")


CHECKS = [
    ("IS-P1c", is_p1c_bare_files_allow_has_no_defined_jail),
    ("IS-F1", is_f1_readonly_preset_default_root_exposes_proc_environ),
    ("IS-F2", is_f2_delete_follows_a_parent_swapped_after_admission),
    ("IS-F4", is_f4_reading_a_fifo_blocks_a_request_thread_forever),
    ("IS-F5", is_f5_hardlink_defeats_deny_globs),
]
