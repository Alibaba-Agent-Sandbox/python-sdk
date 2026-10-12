# S8: template.yaml equivalents of S1 and S2 (+ declarative custom command).
from h import *
import yaml, pathlib
from ebxp.api import from_config, check_config, Principal
os.environ["GRADER_TOKEN"] = "grader-token-0123456789"
ws = pathlib.Path("/tmp/s8ws"); (ws / "submissions").mkdir(parents=True, exist_ok=True)
(ws / "grade.py").write_text("import sys; print('graded', sys.argv[1:])"); (ws / "submissions/s1.txt").write_text("x")
doc = yaml.safe_load(f"""
server:
  preset: download-only
  paths: /tmp/s1
  custom:
    grade:
      argv: ["python3", "{ws}/grade.py", "--submission", "{{submission}}"]
      params: {{submission: {{type: path, root: {ws}/submissions}}}}
      cwd: {ws}
      timeout: 60s
      effects: [exec]
  rules:
    - allow: custom.grade
      principals: [role:grader]
  auth:
    tokens: [{{id: grader, roles: [grader], token_env: GRADER_TOKEN}}]
""")["server"]
srv = from_config(doc)
gr = Principal("grader", ("grader",))
check("download-only from yaml", srv.call("files.download", path="/tmp/s1/a.txt", principal=gr)[0] == 200)
c, b = srv.call("custom.grade", principal=gr, submission=f"{ws}/submissions/s1.txt")
check("declarative custom op runs", c == 200 and b["exit_code"] == 0 and "graded" in b["stdout"], (c, b))
check("param jailed by param root", srv.call("custom.grade", principal=gr, submission="/etc/passwd")[0] == 403)
check("anon cannot grade", srv.call("custom.grade", principal=Principal("z", ()), submission=f"{ws}/submissions/s1.txt")[0] == 404)
check("unknown key suggests fix", "did you mean" in check_config({"presett": "x"})[0], check_config({"presett": "x"}))
done("S8")
