"""Every op of the default registry has a parity-ledger row; every ledger row names a real op (IF-27)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from ebxp import api  # noqa: F401  (registers wire ops)
from ebxp.server import REG
from parity_ledger import ledger, DYNAMIC

ids = set(REG.all()); rows = set(ledger())
ok = True
for name, cond in [
    ("every registry op has a ledger row", not (ids - rows)),
    ("every ledger row is a registry op", not (rows - ids)),
    ("dynamic families documented (custom.<name>, ext.<handler>)", set(DYNAMIC) == {"custom.<name>", "ext.<handler>"}),
    ("the 18 ops named in the review all present", all(i in rows for i in (
        "files.search", "files.upload_stream", "files.download_stream", "files.archive", "process.get", "process.output",
        "terminal.list", "terminal.get", "system.info", "system.env.get", "system.env.set", "system.ports", "system.packages",
        "devtools.git.status", "devtools.git.diff", "core.openapi", "core.reload", "core.describe"))),
    ("browser.* all present", all(f"browser.{v}" in rows for v in ("navigate", "screenshot", "content", "click", "type", "evaluate", "pdf", "console"))),
]:
    print(("PASS " if cond else "FAIL ") + name); ok &= cond
if ids - rows: print("missing:", sorted(ids - rows))
if rows - ids: print("unknown:", sorted(rows - ids))
print(f"{len(ids)} ops / {len(rows)} rows")
sys.exit(0 if ok else 1)
