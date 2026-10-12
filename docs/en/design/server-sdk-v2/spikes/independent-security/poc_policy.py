"""PoCs: policy engine semantics (03 sections 2-3, 8-9, 11)."""
from __future__ import annotations

import subprocess
import sys

from _common import *  # noqa: F403
from _common import (CommandScope, PathScope, Policy, Principal, REG, SPIKES, Server, mktree, ops, secure, Denied)
from ebxp.policy import Deny, Limits
import os


def is_p1_bare_allow_is_unconstrained():
    """IS-P1: allow(commands.run) / allow(files.*) with no scope must fail closed, not mean 'unrestricted'."""
    pol = Policy().allow("commands.run")
    d = pol.decide(REG.get("commands.run"), {"command": "id"}, Principal("anyone", ("viewer",)))
    secure(not d.allowed, "allow(commands.run) without CommandScope admits `id` (no argv/env/cwd constraint at all)")
    secure(pol.lint() != [], "check-config style lint says nothing about an unscoped exec grant")


def is_p1b_omitted_cwd_runs_in_server_cwd():
    """IS-P1: with a cwd PathScope, an omitted cwd must default to the scope root, not the server's own cwd."""
    jail = mktree()
    cs = CommandScope(allow=("pwd",), cwd=PathScope(str(jail)), exec_dirs=("/usr/bin", "/bin"))
    srv = Server(Policy().allow("commands.run", commands=cs))
    st, body = srv.invoke("commands.run", {"command": "pwd"})
    secure(st == 200 and os.path.realpath(body["stdout"].strip()) == str(jail),
           f"`pwd` ran in the server cwd ({body.get('stdout', '').strip()!r}), outside the cwd scope {jail}")


def is_p2_deny_rule_uses_a_different_anchor():
    """IS-P2: a separate deny(paths=[absolute glob]) is evaluated with root '/', the allow scope anchors at its root."""
    root = mktree()
    (root / "x" / "secret").mkdir(parents=True)
    (root / "x" / "secret" / "k").write_text("S")
    pol = (Policy().allow("files.download", paths=str(root / "x"))
           .deny("files.download", paths=[str(root / "x" / "secret") + "/**", str(root / "x" / "secret")]))
    srv = Server(pol)
    st_abs, _ = srv.invoke("files.download", {"path": str(root / "x" / "secret" / "k")})
    st_rel, _ = srv.invoke("files.download", {"path": "secret/k"})
    secure(st_abs == 403, "baseline: absolute path is denied")
    secure(st_rel == 403, "RELATIVE path `secret/k` bypasses the deny rule (deny anchored at '/', allow anchored at its root)")


def is_p2b_deny_pass_reads_command_but_allow_pass_reads_argv():
    """IS-P2: commands.run accepts `command` and `argv`; the deny pass looks only at `command`."""
    root = mktree()
    victim = root / "victim.txt"
    victim.write_text("data")
    cs = CommandScope(allow=("echo ...", "rm ..."), cwd=PathScope(str(root)), exec_dirs=("/usr/bin", "/bin"))
    pol = Policy().allow("commands.run", commands=cs).deny("commands.run", commands=["rm ..."])
    srv = Server(pol)
    srv.invoke("commands.run", {"command": "echo hi", "argv": ["rm", "-f", str(victim)]})
    secure(victim.exists(), "deny(commands=['rm ...']) bypassed: `command` was benign, `argv` carried `rm` and was executed")


def is_p3_deny_glob_matches_only_the_named_entry_not_descendants():
    """IS-P3: deny `**/.ssh` (or a directory) must cover everything beneath it."""
    root = mktree()
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text("PRIVATE")
    scope = PathScope(str(root), deny=("**/.ssh", str(root / "secrets")))
    (root / "secrets").mkdir()
    (root / "secrets" / "k").write_text("K")
    for p in (root / ".ssh" / "id_rsa", root / "secrets" / "k"):
        try:
            resolve_path(scope, str(p))
        except Denied:
            continue
        secure(False, f"deny glob covers the directory entry only; {p.relative_to(root)} is readable")


def is_p4_deny_wildcards_do_not_match_explicit_only_ops():
    """IS-P4: an operator's deny("agents.**") / deny("group:agents") must also kill explicit-only ops."""
    pol = Policy().allow(ops.agents.codex.install).deny("group:agents").deny("agents.**")
    st, body = Server(pol).invoke("agents.codex.install", {})
    secure(st in (403, 404), f"explicit allow of agents.codex.install survives deny(group:agents)/deny(agents.**): HTTP {st}")


def is_p5_hook_can_rewrite_admitted_paths():
    """IS-P5: hooks are 'veto only' but receive the live mutable dict that the handler later uses."""
    root = mktree()
    (root / "a.txt").write_text("public")
    (root / ".env").write_text("SECRET")
    pol = Policy().allow("files.download", paths=PathScope(str(root), deny=("**/.env",)))

    @pol.authorize
    def innocent_looking_hook(ctx):
        ctx.paths["path"] = str(root / ".env")   # e.g. a 'normalise the path' helper written by an AI assistant
    st, body = Server(pol).invoke("files.download", {"path": "a.txt"})
    secure(not (st == 200 and "content_base64" in body and body["path"].endswith(".env")),
           "a hook that mutates ctx.paths changed the admitted path to a deny-listed file; the read succeeded")


def is_p5b_hook_unknown_return_types_must_deny():
    """IS-P5: 03 section 3 step 4 says an unknown return type denies; the reference code allows."""
    root = mktree()
    (root / "a.txt").write_text("x")
    for bad in ("denied", 0, {"allowed": False}, Deny):   # string, falsy int, dict, the Deny CLASS (not an instance)
        pol = Policy().allow("files.download", paths=PathScope(str(root)))
        pol.authorize(lambda ctx, bad=bad: bad)
        st, _ = Server(pol).invoke("files.download", {"path": "a.txt"})
        secure(st == 403, f"hook returning {bad!r} was treated as 'no objection' (HTTP {st})")


def is_p8_negative_limit_arguments_defeat_policy_limits():
    """IS-P8: caller-supplied numeric arguments are not range-checked; max_entries=-1 turns into slice [:-1]."""
    root = mktree()
    for i in range(6):
        (root / f"f{i}").write_text("x")
    pol = Policy().allow("files.list", paths=str(root), limits=Limits(max_entries=2))
    st, body = Server(pol).invoke("files.list", {"path": str(root), "max_entries": -1})
    secure(st != 200 or len(body["entries"]) <= 2,
           f"policy max_entries=2 returned {len(body.get('entries', []))} entries for max_entries=-1")


def is_p9_deny_glob_redos_freezes_the_server():
    """IS-P9: deny globs compile to backtracking regexes; three `**` plus a 4 KiB path pins the GIL for >10 s."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import os, tempfile\n"
        "from ebxp.guards import PathScope, resolve_path, Denied\n"
        "root = os.path.realpath(tempfile.mkdtemp())\n"
        "scope = PathScope(root, deny=('**/a/**/a/**/b',))\n"
        "p = 'a/' * 1900 + 'c'\n"
        "try: resolve_path(scope, p)\n"
        "except Denied: pass\n" % str(SPIKES)
    )
    try:
        subprocess.run([sys.executable, "-c", code], timeout=4, check=False)
    except subprocess.TimeoutExpired:
        secure(False, "one 3.8 KB path request spent >4 s inside a deny-glob match (regex backtracking, GIL held)")


def is_a5_unknown_and_unmounted_ops_are_distinguishable():
    """IS-A5: D4 promises 'byte-identical to unknown'; the spike (and 03 section 11) use different codes and suggestions."""
    root = mktree()
    srv = Server(Policy().allow("files.stat", paths=str(root)))
    st_u, body_u = srv.invoke("zzz.nothing", {})
    st_m, body_m = srv.invoke("files.delete", {"path": "x"})
    secure((st_u, body_u.get("code")) == (st_m, body_m.get("code")),
           f"unknown -> {body_u.get('code')!r}, existing-but-unmounted -> {body_m.get('code')!r}: existence oracle")
    _, body_t = srv.invoke("files.dowload", {})
    secure("files.download" not in str(body_t), "typo suggestion names an op that is not mounted for this caller")


def is_a7_star_principal_matches_anonymous():
    """IS-A7: `*` is documented as 'any authenticated'; the reference _pmatch lets anonymous through."""
    root = mktree()
    pol = Policy().allow("files.stat", principals=["*"], paths=str(root))
    st, _ = Server(pol).invoke("files.stat", {"path": str(root)}, Principal("anonymous", ()))
    secure(st == 404, "principals=['*'] ('any authenticated') admitted the anonymous principal")


CHECKS = [
    ("IS-P1", is_p1_bare_allow_is_unconstrained),
    ("IS-P1b", is_p1b_omitted_cwd_runs_in_server_cwd),
    ("IS-P2", is_p2_deny_rule_uses_a_different_anchor),
    ("IS-P2b", is_p2b_deny_pass_reads_command_but_allow_pass_reads_argv),
    ("IS-P3", is_p3_deny_glob_matches_only_the_named_entry_not_descendants),
    ("IS-P4", is_p4_deny_wildcards_do_not_match_explicit_only_ops),
    ("IS-P5", is_p5_hook_can_rewrite_admitted_paths),
    ("IS-P5b", is_p5b_hook_unknown_return_types_must_deny),
    ("IS-P8", is_p8_negative_limit_arguments_defeat_policy_limits),
    ("IS-P9", is_p9_deny_glob_redos_freezes_the_server),
    ("IS-A5", is_a5_unknown_and_unmounted_ops_are_distinguishable),
    ("IS-A7", is_a7_star_principal_matches_anonymous),
]
