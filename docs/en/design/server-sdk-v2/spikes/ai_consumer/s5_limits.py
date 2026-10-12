# S5: guests may download <=1MB at 2 req/min from /srv-ish public dir; staff up to 1GB.
from h import *
from ebxp.api import SandboxServer, Policy, ops, Limits, Principal
import pathlib
pub = pathlib.Path("/tmp/s5pub"); pub.mkdir(exist_ok=True)
(pub / "small.bin").write_bytes(b"x" * 1000); (pub / "big.bin").write_bytes(b"x" * 2_000_000)
policy = (Policy()
          .allow(ops.files.download, principals=["role:staff"], paths=str(pub), limits=Limits(max_bytes="1GB"))
          .allow(ops.files.download, principals=["role:guest"], paths=str(pub), limits=Limits(max_bytes="1MB", rate="2/min")))
srv = SandboxServer(policy)
g, s = Principal("g", ("guest",)), Principal("s", ("staff",))
check("guest small ok", srv.call("files.download", principal=g, path=str(pub / "small.bin"))[0] == 200)
c, b = srv.call("files.download", principal=g, path=str(pub / "big.bin"))
check("guest big -> 413 limit.max_bytes", c == 413 and b.get("code") == "limit.max_bytes", (c, b))
check("guest third request rate-limited", srv.call("files.download", principal=g, path=str(pub / "small.bin"))[0] == 429)
check("staff big ok", srv.call("files.download", principal=s, path=str(pub / "big.bin"))[0] == 200)
done("S5")
