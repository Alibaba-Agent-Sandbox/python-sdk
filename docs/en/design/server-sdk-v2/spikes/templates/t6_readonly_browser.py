"""T6: read-only file browser: presets.files_readonly mounts only list/stat/download/download_stream."""
from _t import *
from ebxp.api import presets, SandboxServer, REG

ws = workspace(**{"a.txt": "x", ".env": "S", "k.pem": "P"})
srv = SandboxServer(presets.files_readonly(root=ws))
mounted = sorted(i for i in REG.all() if i.startswith("files.") and srv.policy.mounted(REG.get(i), None))
check("exactly the four read ops are mounted", mounted == ["files.download", "files.download_stream", "files.list", "files.stat"], mounted)
check("no system.* / process.* ops leak", not any(srv.policy.mounted(REG.get(i), None) for i in ("system.ports", "system.packages", "process.list")))
check(".env and *.pem denied", all(srv.call("files.download", path=str(ws / n))[1].get("code") == "policy.path_denied" for n in (".env", "k.pem")))
names = sorted(e["name"] for e in srv.call("files.list", path=str(ws))[1]["entries"])
check("list hides denied entries", names == ["a.txt"], names)
check("config check is clean", srv.check() == [], srv.check())
done("T6")
