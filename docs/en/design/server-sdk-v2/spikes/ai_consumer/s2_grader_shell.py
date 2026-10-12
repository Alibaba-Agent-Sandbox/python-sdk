# S2: restricted shell for grading code: only `python3 /workspace/grade.py` and `cat <file under workspace>`, 60 s, grader only.
from h import *
from ebxp.api import SandboxServer, Policy, ops, presets, CommandScope, Principal
import pathlib
ws = pathlib.Path("/tmp/s2ws"); ws.mkdir(exist_ok=True)
(ws / "grade.py").write_text("print('graded ok')")
(ws / "sub.txt").write_text("answer")

policy = presets.minimal() + Policy().allow(
    ops.commands.run, principals=["role:grader"],
    commands=CommandScope(allow=[f"python3 {ws}/grade.py", "cat {path}"], cwd=str(ws), timeout=60, max_output_bytes="1MB"))
grader, anon = Principal("g1", ("grader",)), Principal("x", ())
srv = SandboxServer(policy)
call = lambda pr, **a: srv.call("commands.run", principal=pr, **a)
c, b = call(grader, command=f"python3 {ws}/grade.py")
check("grader can run grade.py", c == 200 and b["exit_code"] == 0 and "graded ok" in b["stdout"], b)
check("cat inside workspace ok", call(grader, command=f"cat {ws}/sub.txt")[0] == 200)
check("cat /etc/passwd denied", call(grader, command="cat /etc/passwd")[0] == 403)
check("cat ../ escape denied", call(grader, command=f"cat {ws}/../s1/a.txt")[0] == 403)
check("python3 -c denied", call(grader, command="python3 -c 'print(1)'")[1].get("code") == "policy.command_not_allowed")
check("sh -c denied", call(grader, command="sh -c id")[0] == 403)
check("shell=True denied", call(grader, command=f"python3 {ws}/grade.py", shell=True)[1].get("code") == "policy.shell_not_allowed")
check("chained command via ; is not a shell here", call(grader, command=f"cat {ws}/sub.txt; id")[0] == 403)
check("LD_PRELOAD env denied", call(grader, command=f"python3 {ws}/grade.py", env={"LD_PRELOAD": "/x.so"})[1].get("code") == "policy.env_var_denied")
check("non-grader sees 404", call(anon, command=f"cat {ws}/sub.txt")[0] == 404)
# the card says: never allow "python3 ..." - does the lint catch it if a consumer does it anyway?
bad = SandboxServer(Policy().allow(ops.commands.run, commands=CommandScope(allow=["python3 ..."], cwd=str(ws))))
check("lint flags 'python3 ...'", any("python3" in m for m in bad.check()), bad.check())
done("S2")
