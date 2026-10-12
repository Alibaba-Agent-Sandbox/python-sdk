"""Checks the catalog tables of 04-builtin-modules.md against the ORIGINAL server source and the id grammar."""
import sys, re, glob, collections
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp.api import REG
from ebxp.catalog import CATALOG
import os
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, *([".."] * 5)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
    "EBX_LEGACY_SRC", os.path.join(_REPO, "server-sdk", "src", "easy_sandbox", "server"))
res = []
def check(n, c): res.append(c); print(("PASS " if c else "FAIL ") + n)

src = set()
for f in glob.glob(SRC + "/routes*.py"):
    for m in re.finditer(r'register\(\s*"(\w+)",\s*"([^"]+)"', open(f).read()):
        src.add((m.group(1), m.group(2)))
legacy = {(m, p) for _, _, _, b, _, _ in CATALOG for m, p, l in b if l} | {("POST", "/commands/{name}")}
# the 41 released (0.2.x) routes must all exist in the source; the working tree may add unreleased in-flight routes (6 at HEAD),
# which the catalog carries as NON-legacy bindings of ops that exist anyway
INFLIGHT = {("GET", "/files/watch"), ("GET", "/process/{pid}/output"), ("GET", "/pty/sessions/{id}"),
            ("POST", "/capabilities/check"), ("POST", "/process/{pid}/stdin"), ("POST", "/pty/sessions/{id}/resize")}
check(f"the 41 legacy bindings in the catalog are all routes in the source ({len(src)} found)", legacy <= src)
check("routes in the source beyond the 41 are exactly the known unreleased in-flight routes", (src - legacy) <= INFLIGHT)
cat_all = {(m, p) for _, _, _, b, _, _ in CATALOG for m, p, l in b}
check("every in-flight route has an op binding in the catalog", (src & INFLIGHT) <= cat_all)
ids = list(REG.all())
check("all ids match grammar", all(re.match(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,4}$", i) for i in ids))
check("no id is a prefix of another", not any(b.startswith(a + ".") for a in ids for b in ids))
by = collections.Counter(i.split(".")[0] for i in ids)
check("files has 12 ops", by["files"] == 12)
check("terminal has 6 ops", by["terminal"] == 6)
check("browser has 8 ops", by["browser"] == 8)
check("system has 6 ops", by["system"] == 6)
check("process+commands = 8 ops", by["process"] + by["commands"] == 8)
check("agents = 3 generic + 25 implemented + 2 reserved + 5 refused (official 32 ids) + 5 adapters * 4", by["agents"] == 3 + 32 + 5 * 4)
check("ops with zero declared effects = 0", all(o.effects for o in REG.all().values()))
AD = ("codex", "claude_code", "qwen_code", "cursor", "qoder")
check("explicit-only ops: install x5, adapter sessions.create x5, core.reload, system.env.set, terminal.create, process.signal",
      sorted(i for i, o in REG.all().items() if o.explicit) ==
      sorted([f"agents.{a}.install" for a in AD] + [f"agents.{a}.sessions.create" for a in AD] +
             ["core.reload", "system.env.set", "terminal.create", "process.signal"]))
from ebxp.catalog import OFFICIAL_47
check("47 official routes: 25 implemented + 2 reserved + 5 refused + 15 not planned",
      len(OFFICIAL_47) == 47 and [sum(1 for *_, t in OFFICIAL_47 if t == k) for k in (1, "R", "X", "N")] == [25, 2, 5, 15])
check("every official op id (non-N) is registered", all(REG.get(i) for _, i, t in OFFICIAL_47 if i))
check("exec-effect ops that start agents carry agent_scope", all(REG.get(i).agent_scope for i in
      ["agents.sessions.create", "agents.sessions.send_event"] + [f"agents.{a}.{s}" for a in AD for s in ("run", "sessions.create", "sessions.send_event")]))
check("every op declares effects explicitly", all(o.effects_declared for o in REG.all().values()))
print(f"total ops in default registry: {len(ids)}  (non-agent {len(ids) - by['agents']})")
print("ALL OK" if all(res) else "FAILURES")
