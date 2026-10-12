# S7: read-only observer of /tmp/s7 with an audit trail of every decision.
from h import *
from ebxp.api import SandboxServer, presets, Policy
import pathlib
d = pathlib.Path("/tmp/s7"); d.mkdir(exist_ok=True); (d / "log.txt").write_text("x")
policy = presets.readonly(paths="/tmp/s7")
records = []
@policy.audit
def sink(rec): records.append(rec)
srv = SandboxServer(policy)
srv.call("files.download", path="/tmp/s7/log.txt")
srv.call("files.download", path="/etc/shadow")
srv.call("files.upload", path="/tmp/s7/new", content_base64="eA==")
check("3 audit records", len(records) == 3, records)
check("allowed record", records[0]["allowed"] and records[0]["op"] == "files.download")
check("denied record has code", records[1]["code"] == "policy.path_not_allowed")
check("unmounted logged", records[2]["code"] == "op.not_enabled")
check("no content in audit", all("content" not in str(r) for r in records))
done("S7")
