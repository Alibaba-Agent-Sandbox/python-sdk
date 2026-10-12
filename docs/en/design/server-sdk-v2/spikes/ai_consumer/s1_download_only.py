# S1: "Only download is enabled, and only under /tmp."  (written from the reference card only)
from h import *
from ebxp.api import SandboxServer, Policy, ops, presets, PathScope
import pathlib, base64
d = pathlib.Path("/tmp/s1"); d.mkdir(exist_ok=True); (d / "a.txt").write_text("hello"); (d / ".env").write_text("SECRET=1")

policy = Policy().allow(ops.files.download, ops.files.stat, ops.files.list,
                        paths=PathScope("/tmp", deny=("**/.env",), max_bytes="10MB"))
srv = SandboxServer(policy)
code, body = srv.call("files.download", path="/tmp/s1/a.txt")
check("download in /tmp works", code == 200 and base64.b64decode(body["content_base64"]) == b"hello", body)
check("/etc/passwd -> 403", srv.call("files.download", path="/etc/passwd")[0] == 403)
check("dotdot escape -> 403", srv.call("files.download", path="/tmp/../etc/passwd")[0] == 403)
check(".env denied", srv.call("files.download", path="/tmp/s1/.env")[1].get("code") == "policy.path_denied")
check("upload not enabled -> 404", srv.call("files.upload", path="/tmp/s1/x", content_base64="eA==")[0] == 404)
check("delete not enabled -> 404", srv.call("files.delete", path="/tmp/s1/a.txt")[0] == 404)
check("commands.run not enabled -> 404", srv.call("commands.run", command="id")[0] == 404)
check("check-config clean", srv.check() == [], srv.check())
srv2 = SandboxServer(presets.download_only(root="/tmp"))
check("preset equivalent works", srv2.call("files.download", path="/tmp/s1/a.txt")[0] == 200)
check("preset: download_stream mounted, upload not", srv2.call("files.download_stream", path="/tmp/s1/a.txt")[0] == 200
      and srv2.call("files.upload", path="/tmp/s1/x", content_base64="eA==")[0] == 404)
done("S1")
