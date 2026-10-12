"""PoCs: command scoping, environment and secrets (03 section 7, 04 section 7)."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

from _common import *  # noqa: F403
from _common import (CommandScope, Denied, PathScope, Policy, REG, SPIKES, check_command, filter_env, mktree, secure)


def is_c1_glob_token_in_argv_pattern_crosses_slash():
    """IS-C1: 07.1 lets a free glob token stand for any single argv element; fnmatch's `*` matches `/` and `..`."""
    cs = CommandScope(allow=("cat /srv/pub/*",), exec_dirs=("/usr/bin", "/bin"))
    try:
        argv, _, _ = check_command(cs, None, ["cat", "/srv/pub/../../etc/passwd"])
    except Denied:
        return
    secure(False, f"`cat /srv/pub/*` admitted argv {argv}: traversal through a glob token (F1.4 fixed only {{path}} tokens)")


def is_c2_system_wildcard_mounts_env_set():
    """IS-C2: allow('system.*') (a natural 'read-only system info' grant) also mounts system.env.set (admin+write)."""
    op = REG.get("system.env.set")
    secure(not Policy().allow("system.*").mounted(op), "system.* mounts system.env.set (not explicit-only: legacy ops keep group membership)")
    secure(not Policy().allow("group:system").mounted(op), "group:system mounts system.env.set")


def is_c2b_env_deny_default_misses_dangerous_names():
    """IS-C2: 03 7.2 says names in env_deny can never be set; the default list omits PATH, HOME, proxies, CA bundles, ..."""
    must_block = ["PATH", "HOME", "TMPDIR", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR",
                  "REQUESTS_CA_BUNDLE", "NODE_PATH", "npm_config_registry", "PIP_INDEX_URL", "JAVA_TOOL_OPTIONS",
                  "GCONV_PATH", "SHELLOPTS", "PS4", "PROMPT_COMMAND", "LESSOPEN", "XDG_CONFIG_HOME",
                  "EBX_SERVER_TOKEN", "EBX_TOOL_CODEX", "EBX_INSTALL_UNPINNED", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"]
    leaked = []
    for name in must_block:
        try:                                              # v2.1: refused at CONSTRUCTION time (ValueError) or at call time
            cs = CommandScope(allow=("true",), env_set=(name,))
            filter_env(cs, {name: "x"})
            leaked.append(name)
        except (Denied, ValueError):
            pass
    secure(not leaked, f"env_deny default lets an author-listed env_set pass these: {leaked}")


def is_c2c_env_pass_reads_the_live_server_environment():
    """IS-C2: env_pass is 'inherited from the server's own environment'; system.env.set mutates os.environ (v1 does)."""
    key = "EBX_ISEC_PROBE_PATH"
    cs = CommandScope(allow=("true",), env_pass=(key,))
    snapshot = filter_env(cs, None)                   # what a startup snapshot would contain
    os.environ[key] = "/tmp/attacker-bin"             # what POST /env does in v1 (routes_system.handle_env_set)
    try:
        after = filter_env(cs, None)
    finally:
        del os.environ[key]
    secure(after == snapshot, "a later system.env.set value flows into every scoped command via env_pass")


def is_c5_lint_misses_exec_equivalent_patterns():
    """IS-C5: the writable-script/escape lints do not flag test runners, network fetchers or copy tools."""
    root = mktree()
    pol = Policy().allow("files.*", paths=PathScope(str(root)))
    missed = []
    for pattern in ("pytest -q {path}", "npm run ...", "curl -o {path} ...", "cp ...", "tee ...", "go test ...", "make ..."):
        p = Policy(list(pol.rules)).allow("commands.run", commands=CommandScope(allow=(pattern,), cwd=PathScope(str(root))))
        if not p.lint():
            missed.append(pattern)
    secure(not missed, f"no lint finding for: {missed} (08 section 4.2 ships `pytest -q {{path}}` next to a writable workspace)")


def is_c7_readonly_cwd_scope_is_ineffective_for_commands():
    """IS-C7: {path} is always resolved with effect 'read', so cwd=PathScope(readonly=True) does not stop `rm {path}`."""
    root = mktree()
    cs = CommandScope(allow=("rm {path}",), cwd=PathScope(str(root), readonly=True), exec_dirs=("/usr/bin", "/bin"))
    try:
        check_command(cs, "rm victim", None)
    except Denied:
        return
    secure(False, "readonly=True cwd scope admitted `rm {path}`; command tokens carry no effect, so readonly is silently ignored")


def is_c6_exec_capable_principal_reads_server_secrets_from_proc():
    """IS-C6: children run with the server uid; /proc/<server>/environ holds every token_env secret.

    Asserts the mitigation through the SPIKE: `start_http()` must call `harden_process()` (PR_SET_DUMPABLE=0), so a
    scrubbed-env child of the process that started the server cannot read /proc/<server pid>/environ.
    """
    server_code = textwrap.dedent("""
        import os, subprocess, sys
        sys.path.insert(0, %r)
        import ebxp.api as api
        from ebxp import Policy, PathScope
        srv = api.SandboxServer(Policy().allow("core.health"))
        httpd = api.start_http(srv)                             # the real startup path
        env = {"PATH": os.environ["PATH"]}                      # scrubbed env, exactly as 03 7.2 prescribes
        child = "import os; print(open('/proc/%%d/environ' %% os.getppid(), 'rb').read().decode(errors='replace'))"
        r = subprocess.run([sys.executable, "-c", child], env=env, capture_output=True, text=True)
        print("LEAK" if "EBX_TOKEN_ADMIN=admin-secret" in r.stdout else "SAFE")
    """ % str(SPIKES))
    out = subprocess.run([sys.executable, "-c", server_code], env=dict(os.environ, EBX_TOKEN_ADMIN="admin-secret"),
                         capture_output=True, text=True, timeout=20)
    secure(out.stdout.strip() == "SAFE", "a scrubbed-env child of the server read EBX_TOKEN_ADMIN from /proc/<server pid>/environ "
                                         + out.stderr[-200:])


def is_c6b_dumpable_zero_is_an_effective_fix():
    """Companion to IS-C6: proves the proposed fix works on this kernel (HELD means the fix is valid)."""
    server_code = textwrap.dedent("""
        import ctypes, os, subprocess, sys
        ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)                  # PR_SET_DUMPABLE = 0
        env = {"PATH": os.environ["PATH"]}
        child = "import os; print(open('/proc/%d/environ' % os.getppid(), 'rb').read().decode(errors='replace'))"
        r = subprocess.run([sys.executable, "-c", child], env=env, capture_output=True, text=True)
        print("LEAK" if "EBX_TOKEN_ADMIN=admin-secret" in r.stdout else "SAFE")
    """)
    out = subprocess.run([sys.executable, "-c", server_code], env=dict(os.environ, EBX_TOKEN_ADMIN="admin-secret"),
                         capture_output=True, text=True, timeout=20)
    secure(out.stdout.strip() == "SAFE", "prctl(PR_SET_DUMPABLE, 0) did not block /proc/<ppid>/environ")


CHECKS = [
    ("IS-C1", is_c1_glob_token_in_argv_pattern_crosses_slash),
    ("IS-C2", is_c2_system_wildcard_mounts_env_set),
    ("IS-C2b", is_c2b_env_deny_default_misses_dangerous_names),
    ("IS-C2c", is_c2c_env_pass_reads_the_live_server_environment),
    ("IS-C5", is_c5_lint_misses_exec_equivalent_patterns),
    ("IS-C7", is_c7_readonly_cwd_scope_is_ineffective_for_commands),
    ("IS-C6", is_c6_exec_capable_principal_reads_server_secrets_from_proc),
    ("HELD-C6b", is_c6b_dumpable_zero_is_an_effective_fix),
]
