"""T2: commands scoped to git and pytest in a read-only workspace (template.yaml `server:` flavour via PyYAML)."""
from _t import *
import yaml
from ebxp.api import from_config, start_http, Principal

ws = workspace(**{"hello.txt": "x"})
os.system(f"cd {ws} && git init -q . 2>/dev/null")
doc = yaml.safe_load(f"""
server:
  preset: ci_runner
  root: {ws}
  commands: ["git status", "git diff ...", "pytest -q ..."]
  auth:
    tokens: [{{id: ci, roles: [ci], token_env: T2_TOKEN}}]
""")["server"]
os.environ["T2_TOKEN"] = "t2-secret-0123456789"
srv = from_config(doc)
ci = Principal("ci", ("ci",))
check("git status runs", srv.call("commands.run", principal=ci, command="git status")[0] == 200)
check("an unlisted command is refused", srv.call("commands.run", principal=ci, command="cat /etc/passwd")[1].get("code") == "policy.command_not_allowed")
check("shell=True is refused", srv.call("commands.run", principal=ci, command="git status", shell=True)[1].get("code") == "policy.shell_not_allowed")
check("workspace is READ-ONLY by default (no files.upload / delete / move)", all(
    srv.call(i, principal=ci)[0] == 404 for i in ("files.upload", "files.delete", "files.move")))
msgs = srv.check()
check("lint says pytest/git run project files (warn, because the workspace is read-only)", any("pytest" in m and m.startswith("warn") for m in msgs), msgs)
from ebxp.api import presets, SandboxServer, CommandScope, PathScope, Policy
bad = Policy().allow("files.*", paths=PathScope(str(ws))).allow("commands.run", commands=CommandScope(allow=["pytest -q ..."], cwd=PathScope(str(ws))))
check("pytest + writable files under the same root is a lint ERROR (arbitrary code execution)", any(m.startswith("error") and "pytest" in m for m in bad.lint()), bad.lint())
done("T2")
