# Round-3 security lens: second wave of attacks against the spike.
import sys, os, pathlib, tempfile
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp.api import *
tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
ws = tmp / "ws"; ws.mkdir(); (ws / "grade.py").write_text("import os; print(os.environ.get('PATH'))")
(ws / ".env").write_text("S=1"); os.symlink(ws / ".env", ws / "innocent.txt")
# (1) env PATH override by caller
pol = Policy().allow(ops.commands.run, commands=CommandScope(allow=[f"python3 {ws}/grade.py"], cwd=str(ws)))
srv = SandboxServer(pol)
c, b = srv.call("commands.run", command=f"python3 {ws}/grade.py", env={"PATH": "/tmp/evil"})
print("(1) caller PATH override ->", c, b.get("code"))
# (2) symlink alias to a denied file
pol2 = Policy().allow(ops.files.download, paths=PathScope(str(ws), deny=("**/.env",)))
print("(2) symlink alias of .env ->", SandboxServer(pol2).call("files.download", path=str(ws / "innocent.txt"))[1].get("code"))
# (3) writable script: upload + run
pol3 = Policy().allow(ops.files.upload, paths=str(ws)).allow(ops.commands.run, commands=CommandScope(allow=[f"python3 {ws}/grade.py"], cwd=str(ws)))
print("(3) lint ->", SandboxServer(pol3).check())
# (4) hook exception fails closed
p4 = Policy().allow(ops.files.stat, paths=str(ws))
@p4.authorize
def boom(ctx): raise RuntimeError("bug")
print("(4) hook crash ->", SandboxServer(p4).call("files.stat", path=str(ws))[1].get("code"))
# (5) path param type confusion
print("(5) list-valued path ->", SandboxServer(pol2).call("files.download", path=[str(ws)])[0:2])
# (6) very long / NUL / newline path
print("(6) newline in path ->", SandboxServer(pol2).call("files.stat", path=str(ws) + "/a\nb")[0])
# (7) deny rule must override a broader allow even for a more specific allow
p7 = Policy().allow(ops.files.download, paths=str(ws)).deny("files.*", reason="frozen")
print("(7) deny beats specific allow ->", SandboxServer(p7).call("files.download", path=str(ws / "grade.py"))[1].get("code"))
