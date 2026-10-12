# S6: custom op custom.checksum(path) (sha256), only under /tmp/s6, never *.exe, and everything else is off.
from h import *
from ebxp.api import SandboxServer, Policy, ops, op, Deny
import hashlib, pathlib
d = pathlib.Path("/tmp/s6"); d.mkdir(exist_ok=True); (d / "a.txt").write_text("abc"); (d / "evil.exe").write_text("MZ")

@op("custom.checksum", effects="read", paths=("path",), summary="sha256 of a file")
def checksum(ctx, path: str) -> dict:
    return {"sha256": hashlib.sha256(open(ctx.paths["path"], "rb").read()).hexdigest()}

policy = Policy().allow(ops.custom.checksum, paths="/tmp/s6")
@policy.authorize
def no_exe(ctx):
    if ctx.op == "custom.checksum" and ctx.paths["path"].endswith(".exe"):
        return Deny("executables are not allowed", code="policy.extension_not_allowed")
srv = SandboxServer(policy)
c, b = srv.call("custom.checksum", path="/tmp/s6/a.txt")
check("checksum works", c == 200 and b["sha256"] == hashlib.sha256(b"abc").hexdigest(), b)
check("outside jail denied", srv.call("custom.checksum", path="/etc/passwd")[0] == 403)
c, b = srv.call("custom.checksum", path="/tmp/s6/evil.exe")
check("hook veto with custom code", c == 403 and b.get("code") == "policy.extension_not_allowed", (c, b))
check("other ops unmounted", srv.call("files.download", path="/tmp/s6/a.txt")[0] == 404)
check("unknown arg rejected", srv.call("custom.checksum", path="/tmp/s6/a.txt", extra=1)[0] == 400)
@op("custom.sneaky", effects="read")
def sneaky(ctx, file: str) -> dict: return {}
check("lint warns about undeclared path-like param", any("custom.sneaky" in m and "file" in m for m in SandboxServer(Policy()).check()), SandboxServer(Policy()).check())
done("S6")
