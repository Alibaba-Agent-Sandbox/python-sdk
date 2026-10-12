import os, sys, tempfile, pathlib
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp import *
from ebxp.server import Server
from ebxp.guards import resolve_path, open_verified
tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
(tmp/"pub").mkdir(); (tmp/"outside").mkdir(); (tmp/"outside/victim.txt").write_text("PRECIOUS")
scope = PathScope(roots=(str(tmp/"pub"),))
(tmp/"pub/d").mkdir(); (tmp/"pub/d/victim.txt").write_text("x")
real = resolve_path(scope, str(tmp/"pub/d/victim.txt"), "write")
os.rename(tmp/"pub/d", tmp/"pub/d_old"); os.symlink(tmp/"outside", tmp/"pub/d")
try:
    open_verified(scope, real, os.O_WRONLY | os.O_TRUNC); r = "opened!?"
except Exception as e:
    r = f"denied: {getattr(e,'code',e)}"
print("(1) racing O_TRUNC ->", r, "| victim:", repr((tmp/"outside/victim.txt").read_text()))
# O_CREAT race: create new file through swapped dir
os.unlink(tmp/"pub/d"); os.rename(tmp/"pub/d_old", tmp/"pub/d")
real = resolve_path(scope, str(tmp/"pub/d/new.txt"), "write")
os.rename(tmp/"pub/d", tmp/"pub/d_old"); os.symlink(tmp/"outside", tmp/"pub/d")
try: open_verified(scope, real, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
except Exception as e: pass
print("(1b) O_CREAT race: outside/new.txt exists?", (tmp/"outside/new.txt").exists())
# normal write path works
os.unlink(tmp/"pub/d"); os.rename(tmp/"pub/d_old", tmp/"pub/d")
fd = open_verified(scope, resolve_path(scope, str(tmp/"pub/d/ok.txt"), "write"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
os.write(fd, b"hi"); os.close(fd); print("(1c) normal write ok:", (tmp/"pub/d/ok.txt").read_text())
cs = CommandScope(allow=("ls {path}", "cat {path}"), cwd=PathScope(roots=(str(tmp/"pub"),)), exec_dirs=("/bin","/usr/bin"))
s = Server(Policy().allow("commands.run", commands=cs))
print("(2) ls pub/../outside ->", s.invoke("commands.run", {"command": f"ls {tmp}/pub/../outside"})[1].get("code"))
print("(2b) ls pub (ok) ->", s.invoke("commands.run", {"command": f"ls {tmp}/pub"})[0])
print("(2c) ls -R pub (flag as path) ->", s.invoke("commands.run", {"command": f"ls -R {tmp}/pub"})[1].get("code"))
print("(2d) symlink in pub -> outside:")
os.symlink(tmp/"outside", tmp/"pub/esc")
print("     ls pub/esc ->", s.invoke("commands.run", {"command": f"ls {tmp}/pub/esc"})[1].get("code"))
cs = CommandScope(allow=("ls ...",), deny=("ls -R ...",), exec_dirs=("/bin","/usr/bin"))
s = Server(Policy().allow("commands.run", commands=cs))
print("(3) ls -lR ->", s.invoke("commands.run", {"command": f"ls -lR {tmp}"})[1].get("code"))
print("(3b) ls --recursive (long flag alias) ->", s.invoke("commands.run", {"command": f"ls --recursive {tmp}"})[0], "(200 => deny-list inherently incomplete; docs must say allowlist-first)")
