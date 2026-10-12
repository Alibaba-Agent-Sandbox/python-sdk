"""v2.1 semantics that are not covered by a PoC: scope-required, explicit-only, open-mode refusal, legacy compat, lint."""
import os, sys, tempfile, stat, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ebxp.api as api
from ebxp.api import (SandboxServer, Policy, Principal, PathScope, CommandScope, AgentScope, UrlScope, Limits, Narrow,
                      ConfigError, PolicyError, ops, presets, start_http, legacy_diff)
from ebxp.guards import check_url, Denied
from ebxp.server import Server, REG

R = []


def check(n, c, extra=""):
    R.append(bool(c)); print(("PASS " if c else "FAIL ") + n + ((" :: " + str(extra)) if (extra and not c) else ""))


root = pathlib.Path(tempfile.mkdtemp(prefix="ebx-v21-")).resolve()
(root / "a.txt").write_text("hi")
S = lambda pol, **k: SandboxServer(pol, strict=k.pop("strict", True), tokens={"t" * 20: Principal("t", ("admin",))}, **k)

# core.health, scope-required, typos
check("core.health is mounted by an otherwise empty policy", Server(Policy()).invoke("core.health", {})[0] == 200)
st, b = Server(Policy().allow("files.download")).invoke("files.download", {"path": "x"})
check("allow(files.download) without PathScope -> 403 policy.scope_required", st == 403 and b["code"] == "policy.scope_required", b)
st, b = Server(Policy().allow("commands.run")).invoke("commands.run", {"command": "id"})
check("allow(commands.run) without CommandScope -> 403 policy.scope_required", st == 403 and b["code"] == "policy.scope_required", b)
try:
    SandboxServer(Policy().allow("file.list"))
    check("typo'd selector raises PolicyError at construction", False)
except PolicyError as e:
    check("typo'd selector raises PolicyError with a did-you-mean", "did you mean 'files.list'" in str(e), e)
check("strict=False lets tests construct anyway", SandboxServer(Policy().allow("file.list"), strict=False) is not None)
try:
    PathScope("/")
    check("PathScope('/') refused", False)
except ValueError:
    check("PathScope('/') refused", True)
try:
    PathScope("/tmp/*")
    check("glob in allow root refused", False)
except ValueError:
    check("glob in allow root refused", True)
try:
    CommandScope.unrestricted()
    check("CommandScope.unrestricted() needs unsafe=True", False)
except ValueError:
    check("CommandScope.unrestricted() needs unsafe=True", True)
lint = Policy().allow("files.*", paths=PathScope.anywhere(unsafe=True)).lint()
check("anywhere(unsafe=True) is a lint error", any(m.startswith("error") for m in lint), lint)

# selectors
srv = S(Policy().allow("files.*", paths=PathScope(root)).allow("system.*").allow("group:system"))
check("ns.* is one level: system.* does not reach system.env.set", srv.policy.mounted(REG.get("system.env.get"), None)
      and not srv.policy.mounted(REG.get("system.env.set"), None))
check("ns.** is any depth", Policy().allow("agents.codex.**").mounted(REG.get("agents.codex.run"), None)
      and not Policy().allow("agents.codex.*").mounted(REG.get("agents.codex.sessions.send_event"), None))
check("effect:read never reaches an explicit-only op", not Policy().allow("effect:read").mounted(REG.get("core.reload"), None))

# env.set: explicit-only, overlay only, ENV_NEVER refused
pol = Policy().allow(ops.system.env.set)
s2 = Server(pol)
os.environ.pop("EBX_PROBE", None)
check("system.env.set named explicitly works but writes only the overlay",
      s2.invoke("system.env.set", {"name": "FOO_BAR", "value": "1"})[0] == 200 and s2.env_overlay == {"FOO_BAR": "1"} and "FOO_BAR" not in os.environ)
check("system.env.set refuses PATH and EBX_*", all(s2.invoke("system.env.set", {"name": n, "value": "x"})[0] == 403
                                                    for n in ("PATH", "LD_PRELOAD", "EBX_SERVER_TOKEN", "OPENAI_API_KEY")))

# deny reach
pol = Policy().allow(ops.core.reload, ops.process.signal).deny("effect:admin").deny("process.*")
check("deny(effect:admin) and deny(ns.*) reach explicit-only ops", all(
    Server(pol).invoke(i, {})[0] in (403, 404)
    for i in ("core.reload", "process.signal")))

# principals
pol = Policy().allow("files.stat", principals=["*"], paths=str(root))
check("principals=['*'] excludes the anonymous principal, includes authenticated ones",
      Server(pol).invoke("files.stat", {"path": "a.txt"}, Principal("anonymous"))[0] == 404
      and Server(pol).invoke("files.stat", {"path": "a.txt"}, Principal("bob"))[0] == 200)
check("id 'anonymous' is always unauthenticated", Principal("anonymous", ("admin",)).authenticated is False)

# effects default / OpRef verbs / frozen registry
reg_srv = None
from ebxp.core import Registry
r = Registry()


@r.op("custom.noeffects")
def noeffects(ctx): return {"ok": 1}


check("op without effects= defaults to admin (explicit-only) and lints", r.get("custom.noeffects").explicit
      and any("effects=" in m for m in r.lint()))
check("ops.custom.format is an OpRef, not str.format", str(ops.custom.format) == "custom.format" and str(ops.custom.split) == "custom.split")
try:
    api.op("custom.late", effects="read")(lambda ctx: {})
    srv = S(Policy().allow("custom.late"))
    srv.reg.op("custom.later", effects="read")(lambda ctx: {})
    check("registering after the server is built raises", False)
except RuntimeError as e:
    check("registering after the server is built raises a clear error", "register ops before constructing the server" in str(e))

# templated per-tenant scope, limit args, command/argv
(root / "alice").mkdir(); (root / "alice" / "f").write_text("A"); (root / "bob").mkdir(); (root / "bob" / "f").write_text("B")
pol = Policy().allow("files.download", paths=PathScope(str(root) + "/{principal.id}"))
sv = Server(pol)
check("PathScope('/data/{principal.id}') isolates tenants", sv.invoke("files.download", {"path": "f"}, Principal("alice"))[0] == 200
      and sv.invoke("files.download", {"path": str(root / "bob" / "f")}, Principal("alice"))[0] == 403
      and sv.invoke("files.download", {"path": "f"}, Principal("../x"))[0] == 403)
pol = Policy().allow("files.list", paths=str(root), limits=Limits(max_entries=1))
sv = Server(pol)
check("limit args must be ints >= 1 (400 args.type)", all(sv.invoke("files.list", {"path": ".", "max_entries": v})[0] == 400
                                                         for v in (0, -1, "5", True, 1.5)))
cs = CommandScope(allow=("echo ...", "pwd"), cwd=PathScope(str(root)), exec_dirs=("/usr/bin", "/bin"))
sv = Server(Policy().allow("commands.run", commands=cs))
check("command and argv together are rejected", sv.invoke("commands.run", {"command": "echo a", "argv": ["echo", "b"]})[1].get("code") == "args.invalid")
check("omitted cwd defaults to the scope root, never the server cwd",
      os.path.realpath(sv.invoke("commands.run", {"command": "pwd"})[1].get("stdout", "").strip()) == str(root))

# agents: AgentScope required, full needs unconfined_ok
bad = Policy().allow("agents.codex.run", agents=AgentScope(workdir=PathScope(str(root)), permissions="full"))
check("AgentScope(permissions='full') without unconfined_ok is a lint error", any("unconfined_ok" in m for m in bad.lint()))
try:
    AgentScope(permissions="yolo")
    check("AgentScope rejects unknown permissions", False)
except ValueError:
    check("AgentScope rejects unknown permissions", True)
check("AgentScope with permissions=None is refused at admission", Server(Policy().allow("agents.codex.run", agents=AgentScope(workdir=str(root)))
      ).invoke("agents.codex.run", {})[1].get("code") == "policy.scope_required")

# open mode
for pol, host, why in ((presets.commands_only(str(root), allow=["echo ..."]), "127.0.0.1", "exec preset without auth"),
                       (Policy().allow("core.health"), "0.0.0.0", "non-loopback bind without auth")):
    try:
        start_http(SandboxServer(pol), host=host)
        check(f"open mode refused: {why}", False)
    except ConfigError as e:
        check(f"open mode refused: {why}", e.code in ("config.open_exec", "config.open_non_loopback"), e)
h = start_http(SandboxServer(presets.commands_only(str(root), allow=["echo ..."])), allow_open=True)
check("allow_open=True is the explicit escape", h.server_address[1] > 0); h.shutdown()

# legacy compat
srv = SandboxServer(presets.legacy_compat())
check("legacy_compat mounts every legacy id except system.env.set", legacy_diff(srv) == ["system.env.set"], legacy_diff(srv))
os.environ["EBX_SERVER_LEGACY_ENV_SET"] = "1"
check("EBX_SERVER_LEGACY_ENV_SET=1 mounts it", legacy_diff(SandboxServer(presets.legacy_compat())) == [])
del os.environ["EBX_SERVER_LEGACY_ENV_SET"]
check("legacy_compat is a loud lint", sum(m.startswith("error") for m in srv.check()) >= 2)
check("a narrow policy reports what v1 served and v2 does not", len(legacy_diff(SandboxServer(presets.download_only(str(root))))) > 30)

# presets
for fn, kw in ((presets.readonly, {}), (presets.download_only, {}), (presets.workspace_jail, {}), (presets.ci_runner, {}), (presets.agent_host, {})):
    try:
        fn(**kw)
        check(f"{fn.__name__}() without a root raises", False)
    except ValueError as e:
        check(f"{fn.__name__}() without a root raises and names the aliases", "root=" in str(e))
check("presets accept root=, paths= and workspace= alike", all(
    presets.ci_runner(**{k: str(root)}, commands=["ls ..."]).rules for k in ("root", "paths", "workspace")))
ci = SandboxServer(presets.ci_runner(str(root), commands=["pytest -q ..."]), tokens={"t" * 20: Principal("t", ())})
check("ci_runner mounts no write ops by default", not any(ci.policy.mounted(REG.get(i), None) for i in ("files.upload", "files.delete", "files.move")))
check("files_readonly mounts exactly list/stat/download/download_stream",
      sorted(i for i in REG.all() if i.startswith("files.") and SandboxServer(presets.files_readonly(str(root))).policy.mounted(REG.get(i), None))
      == ["files.download", "files.download_stream", "files.list", "files.stat"])
for key in ("preset: download-only", "preset: download_only"):
    check(f"{key} (both spellings) load", api.from_config({"preset": key.split(": ")[1], "root": str(root)}) is not None)
try:
    api.from_config({"presett": "x"})
    check("unknown key in the server: block is an error", False)
except ConfigError as e:
    check("unknown key in the server: block is an error with a hint", "did you mean 'preset'" in str(e))
r = api.from_config({"preset": "agent-host", "root": str(root), "agents": ["codex", "qoder"],
                     "auth": {"tokens": [{"id": "x", "roles": ["dev"], "token_env": "PATH"}]}})
check("agent_host with qoder warns that it is experimental", any("qoder" in m and "experimental" in m for m in r.check()), r.check())

# state dir
check("default state dir is not under /tmp", not api.default_state_dir().startswith("/tmp"))
d = tempfile.mkdtemp(); os.chmod(d, 0o777)
try:
    api.prepare_state_dir(d)
    check("state dir that is group/world writable is refused", False)
except ConfigError:
    check("state dir that is group/world writable is refused", True)
check("a protected dir is unreachable even from an anywhere() scope", Server(Policy().allow("files.download", paths=PathScope.anywhere(unsafe=True))
      ).invoke("files.download", {"path": str(pathlib.Path(api.prepare_state_dir(tempfile.mkdtemp())) / "x")})[1].get("code") == "policy.path_denied")

# explain
e = SandboxServer(presets.download_only(str(root))).explain("files.upload", {"path": "x", "content_base64": ""})
check("explain() names the decision", e["allowed"] is False and e["code"] == "op.not_enabled")

# hooks: frozen view, exact returns
pol = Policy().allow("files.stat", paths=str(root))
seen = []


@pol.authorize
def peek(ctx):
    seen.append(type(ctx.paths).__name__)
    try:
        ctx.args["path"] = "/etc/passwd"
    except TypeError:
        seen.append("frozen")
Server(pol).invoke("files.stat", {"path": "a.txt"})
check("hooks get read-only views", seen == ["mappingproxy", "frozen"], seen)

# conflicting credentials and precedence
sv = SandboxServer(Policy().allow("core.health"), tokens={"a" * 20: Principal("a", ())})
try:
    sv.authenticate({"authorization": "Bearer " + "a" * 20, "x-access-token": "b" * 20}); ok = False
except api.AuthConflict:
    ok = True
check("Authorization + a different X-Access-Token is refused", ok)
check("equal credentials are accepted; either header alone works", sv.authenticate({"authorization": "Bearer " + "a" * 20, "x-access-token": "a" * 20}) is not None
      and sv.authenticate({"x-access-token": "a" * 20}) is not None and sv.authenticate({"authorization": "Bearer " + "a" * 20}) is not None)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
