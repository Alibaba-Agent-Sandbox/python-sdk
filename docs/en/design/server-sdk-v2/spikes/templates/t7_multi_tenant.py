"""T7: two tenants, per-tenant roots via PathScope('/data/{principal.id}'), custom authenticate(headers)."""
from _t import *
from ebxp.api import SandboxServer, Policy, PathScope, Principal, start_http, ops

data = workspace(**{"alice/f.txt": "A", "alice2/f.txt": "A2", "bob/f.txt": "B"})
KEYS = {"alice-key-0123456789": "alice", "bob-key-0123456789": "bob"}


def authenticate(headers):          # headers are lower-cased; return a Principal or None (-> 401)
    tok = headers.get("authorization", "")[7:]
    return Principal(KEYS[tok], ("tenant",)) if tok in KEYS else None


pol = Policy().allow(ops.files.download, ops.files.list, principals=["role:tenant"], paths=PathScope(str(data) + "/{principal.id}"))
srv = SandboxServer(pol, authenticate=authenticate)
httpd = start_http(srv); port = httpd.server_address[1]
a, b = "alice-key-0123456789", "bob-key-0123456789"
check("alice reads her own file", http(port, "POST", "/ops/files.download", {"path": "f.txt"}, a)[0] == 200)
check("alice cannot read bob's", http(port, "POST", "/ops/files.download", {"path": str(data / "bob" / "f.txt")}, a)[0] == 403)
check("alice cannot reach /data/alice2 by prefix (component-wise, not string prefix)", http(port, "POST", "/ops/files.download", {"path": str(data / "alice2" / "f.txt")}, a)[0] == 403)
check("no token -> 401", http(port, "POST", "/ops/files.download", {"path": "f.txt"})[0] == 401)
check("bob reads his own", http(port, "POST", "/ops/files.download", {"path": "f.txt"}, b)[0] == 200)
httpd.shutdown()
done("T7")
