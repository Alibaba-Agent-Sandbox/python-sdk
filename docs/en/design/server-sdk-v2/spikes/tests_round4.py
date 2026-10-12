import sys, json, urllib.request, urllib.error
import os as _os; sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from ebxp.api import *
R = []
def check(n, c): R.append(c); print(("PASS " if c else "FAIL ") + n)
srv = SandboxServer(presets.minimal(), tokens={"tok": Principal("a", ("admin",))})
srv.max_request_bytes = 1000
httpd = start_http(srv); port = httpd.server_address[1]
def http(path, body=b"{}", token=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    try:
        r = urllib.request.urlopen(req); return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
check("unknown route, no token -> 401 (no route probing)", http("/nope/zzz")[0] == 401)
check("unknown op, no token -> 401", http("/ops/files.nonexistent")[0] == 401)
check("unknown op, token -> 404 op.not_enabled (same as unmounted)", http("/ops/files.nonexistent", token="tok")[1].get("code") == "op.not_enabled")
check("oversized body rejected before read", http("/ops/core.describe", body=b"x" * 5000, token="tok")[0] == 413)
check("oversized body, no token -> 401 first? (413 pre-auth is acceptable: no body read)", http("/ops/core.describe", body=b"x" * 5000)[0] in (401, 413))
httpd.shutdown(); print("ALL OK" if all(R) else "FAILURES")
