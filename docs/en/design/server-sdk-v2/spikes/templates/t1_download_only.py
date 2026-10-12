"""T1: 'Only download is enabled, and only under /tmp.'  (template server.py, Python flavour: 3 lines)"""
from _t import *
from ebxp.api import SandboxServer, presets

ROOT = workspace(**{"a.txt": "hello", ".env": "SECRET=1"})          # stands in for /tmp
srv = SandboxServer(presets.download_only(root=ROOT))                # <- the whole template

st, b = srv.call("files.download", path=str(ROOT / "a.txt"))
check("download works", st == 200)
check(".env is denied (403 policy.path_denied)", srv.call("files.download", path=str(ROOT / ".env"))[1].get("code") == "policy.path_denied")
check("upload is not enabled (404 op.not_enabled)", srv.call("files.upload", path=str(ROOT / "x"), content_base64="eA==")[1].get("code") == "op.not_enabled")
check("commands.run is not enabled", srv.call("commands.run", command="id")[0] == 404)
check("core.health is mounted (the platform ready check)", srv.call("core.health")[0] == 200)
check("config check is clean", srv.check() == [], srv.check())
done("T1")
