import base64, os, sys, tempfile, pathlib, threading
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp import *
from ebxp.server import Server, REG
from ebxp.guards import resolve_path, open_verified

tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
(tmp / "pub").mkdir(); (tmp / "pub/a.txt").write_text("hello"); (tmp / "pub/.env").write_text("SECRET")
(tmp / "secret.txt").write_text("nope")
os.symlink(tmp / "secret.txt", tmp / "pub/link_out")             # symlink escaping the root
os.symlink(tmp / "pub/a.txt", tmp / "pub/link_in")               # symlink staying inside

scope = PathScope(roots=(str(tmp / "pub"),), deny=("**/.env",), symlinks="within")
pol = Policy().allow(ops.files.download, ops.files.stat, ops.files.list, paths=scope, name="dl")
srv = Server(pol, verbose=True)
R = lambda op, **a: srv.invoke(op, a)
res = {}
def check(name, cond): res[name] = bool(cond); print(("PASS " if cond else "FAIL ") + name)

check("download ok", R("files.download", path=str(tmp/"pub/a.txt"))[0] == 200)
check("relative path anchors at root", R("files.download", path="a.txt")[0] == 200)
check("dotdot escape denied", R("files.download", path=str(tmp/"pub/../secret.txt"))[0] == 403)
check("symlink escape denied (within)", R("files.download", path=str(tmp/"pub/link_out"))[0] == 403)
check("symlink inside allowed (within)", R("files.download", path=str(tmp/"pub/link_in"))[0] == 200)
check("deny glob .env", R("files.download", path=str(tmp/"pub/.env"))[1].get("code") == "policy.path_denied")
check("upload not mounted -> 404", R("files.upload", path=str(tmp/"pub/x"), content_base64="eA==")[0] == 404)
check("delete not mounted -> 404", R("files.delete", path=str(tmp/"pub/a.txt"))[0] == 404)
check("denied path 403 even if nonexistent (no oracle)", R("files.stat", path=str(tmp/"nonexistent/zzz"))[0] == 403)
check("inside, missing -> exists false", R("files.stat", path=str(tmp/"pub/missing"))[1].get("exists") is False)
lst = R("files.list", path=str(tmp/"pub"))[1]["entries"]
check("list hides denied+escaping entries", sorted(e["name"] for e in lst) == ["a.txt", "link_in"])
check("NUL byte rejected", R("files.stat", path="a\x00b")[0] == 403)
check("typo suggestion", "files.download" in R("files.dowload", path="x")[1]["error"])

# symlink mode deny
pol2 = Policy().allow(ops.files.download, paths=PathScope(roots=(str(tmp/"pub"),), symlinks="deny"))
s2 = Server(pol2)
check("symlinks=deny blocks inside link", s2.invoke("files.download", {"path": str(tmp/"pub/link_in")})[1].get("code") == "policy.symlink_denied")

# TOCTOU: resolve while path is a regular file, then swap to an escaping symlink before open
target = tmp / "pub/race.txt"; target.write_text("safe")
real = resolve_path(scope, str(target))
os.unlink(target); os.symlink(tmp / "secret.txt", target)
try:
    open_verified(scope, real, os.O_RDONLY); ok = False
except (Denied, OSError) as e:
    ok = True
check("TOCTOU symlink swap caught by open_verified", ok)

# readonly + upload
pol3 = Policy().allow(ops.files.upload, paths=PathScope(roots=(str(tmp/"pub"),), readonly=True))
check("readonly blocks write", Server(pol3).invoke("files.upload", {"path": "w.txt", "content_base64": "eA=="})[1].get("code") == "policy.read_only")

# deny overrides
pol4 = Policy().allow("files.*", paths=PathScope(roots=(str(tmp),))).deny(ops.files.delete, reason="no deletes")
s4 = Server(pol4)
check("deny overrides allow", s4.invoke("files.delete", {"path": str(tmp/"pub/a.txt")})[0] == 403)
check("allow still works for others", s4.invoke("files.stat", {"path": str(tmp/"pub/a.txt")})[0] == 200)

# per-principal
pol5 = Policy().allow("files.download", principals=["role:reader"], paths=PathScope(roots=(str(tmp/"pub"),))) \
               .allow("files.upload", principals=["role:writer"], paths=PathScope(roots=(str(tmp/"pub"),)))
s5 = Server(pol5)
rd, wr = Principal("r", ("reader",)), Principal("w", ("writer",))
check("reader may download", s5.invoke("files.download", {"path": "a.txt"}, rd)[0] == 200)
check("reader may not upload (404: not mounted FOR THIS principal, no oracle)", s5.invoke("files.upload", {"path": "n", "content_base64": "eA=="}, rd)[0] == 404)
check("writer may upload", s5.invoke("files.upload", {"path": "n.txt", "content_base64": "eA=="}, wr)[0] == 200)

# hooks
seen = []
pol6 = Policy().allow("files.download", paths=PathScope(roots=(str(tmp/"pub"),)))
@pol6.authorize
def only_small(ctx):
    seen.append(ctx.resolved)
    if os.path.getsize(ctx.resolved["path"]) > 3: return Deny("too big", code="custom.too_big")
s6 = Server(pol6)
st, body = s6.invoke("files.download", {"path": "a.txt"})
check("hook sees resolved path & can veto", st == 403 and body["code"] == "custom.too_big" and seen)
pol7 = Policy().allow("files.stat", paths=PathScope(roots=(str(tmp),)), authorize=lambda c: 1/0)
check("hook exception fails closed", Server(pol7).invoke("files.stat", {"path": str(tmp)})[1].get("code") == "policy.hook_error")

# audit
events = []
pol8 = Policy().allow("files.stat", paths=PathScope(roots=(str(tmp),))); pol8.audit(events.append)
Server(pol8).invoke("files.stat", {"path": str(tmp/"pub")}); Server(pol8).invoke("files.stat", {"path": "/etc/passwd"})
check("audit sees allow and deny", [e["allowed"] for e in events] == [True, False])

# commands
cs = CommandScope(allow=("pytest -q ...", "python3 /workspace/grade.py", "ls ..."), deny=("ls -R ...",),
                  exec_dirs=("/usr/bin", "/bin"), cwd=PathScope(roots=(str(tmp),)))
pol9 = Policy().allow("commands.run", commands=cs)
s9 = Server(pol9)
C = lambda **a: s9.invoke("commands.run", a)
check("allowed argv runs", C(command=f"ls {tmp}")[0] == 200)
check("deny pattern wins", C(command=f"ls -R {tmp}")[1].get("code") == "policy.command_denied")
check("unlisted command denied", C(command="cat /etc/passwd")[1].get("code") == "policy.command_not_allowed")
check("shell metachar not interpreted (args literal)", C(command=f"ls {tmp}; id")[0] in (200,) and "uid=" not in str(C(command=f"ls {tmp}; id")[1]))
check("shell=True denied", C(command="ls", shell=True)[1].get("code") == "policy.shell_not_allowed")
check("path-qualified exe outside exec_dirs denied", C(command="/tmp/evil ls")[1].get("code") in ("policy.executable_not_allowed", "policy.command_not_allowed"))
ev = tmp / "pub/ls"; ev.write_text("#!/bin/sh\necho pwned\n"); ev.chmod(0o755)
check("relative ./ls does not hijack", C(command="./ls")[1].get("code") in ("policy.executable_not_allowed", "policy.command_not_allowed", "policy.command_not_found"))
check("env LD_PRELOAD denied", C(command=f"ls {tmp}", env={"LD_PRELOAD": "/x.so"})[1].get("code") == "policy.env_var_denied")
check("python3 pinned script only", C(command="python3 -c 'print(1)'")[1].get("code") == "policy.command_not_allowed")
check("lint flags open interpreters", any("python3" in w for w in Policy().allow("commands.run", commands=CommandScope(allow=("python3 ...",))).lint()))
os.environ.setdefault("LANG", "C")
# argv[0] symlink trick: /usr/bin/python3 resolves to /usr/bin/python3.12 ; pattern on name still matches name
check("describe lists mounted flag", srv.describe()["files.download"]["mounted"] and not srv.describe()["files.upload"]["mounted"])
oa = srv.openapi()
check("openapi has operationId per op", all(v for p in oa["paths"].values() for v in p.values()))
print(sum(res.values()), "/", len(res))
sys.exit(0 if all(res.values()) else 1)
