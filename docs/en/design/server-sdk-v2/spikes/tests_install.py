"""Lazy-install protocol checks (no network): fast path, read-only rootfs, async 202, concurrent installers, tamper."""
import os, sys, tempfile, threading, time, pathlib, stat
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ebxp.install import Installer, InstallError, InstallPending, tree_digest
R = []
def check(n, c, extra=""):
    R.append(bool(c)); print(("PASS " if c else "FAIL ") + n + ((" :: " + str(extra)) if (extra and not c) else ""))

calls = []
def fake(bindir, delay=0.0):
    calls.append(bindir); time.sleep(delay); open(os.path.join(bindir, "codex"), "w").write("#!/bin/sh\necho codex\n")

d = tempfile.mkdtemp()
ins = Installer("codex", "1.0.0", [d], fake)
t = ins.ensure()
check("first ensure installs and returns the tree", os.path.exists(os.path.join(t, "bin", "codex")))
n = len(calls)
check("second ensure is the lock-free fast path (no installer call)", ins.ensure() == t and len(calls) == n)
os.remove(os.path.join(d, ".locks", "codex-1.0.0.lock"))
os.rmdir(os.path.join(d, ".locks"))
check("fast path needs no lock dir at all", ins.ensure() == t)

# read-only rootfs: marker present in a read-only dir is found; a missing tool reports the dirs tried
ro = tempfile.mkdtemp(); inst = Installer("codex", "1.0.0", [ro], fake); inst.ensure()
os.chmod(ro, 0o500)
for p in pathlib.Path(ro).rglob("*"):
    if p.is_dir(): os.chmod(p, 0o500)
ro_inst = Installer("codex", "1.0.0", [ro], fake)
if os.geteuid() == 0:
    print("SKIP read-only checks (running as root: chmod is not enforced)")
else:
    check("prepared tools on a read-only dir are found without any write", ro_inst.find() is not None)
    other = Installer("claude", "2.0.0", [ro], fake)
    try:
        other.ensure(); check("read-only + missing -> install.read_only", False)
    except InstallError as e:
        check("read-only + missing -> install.read_only listing the dirs tried", e.code == "install.read_only" and ro in e.details["tried"], e)
for p in sorted(pathlib.Path(ro).rglob("*"), reverse=True):
    os.chmod(p, 0o700)
os.chmod(ro, 0o700)

# chain: first dir read-only/unwritable, second writable
bad = "/proc/ebx-nope"; good = tempfile.mkdtemp()
chain = Installer("qwen", "0.1", [bad, good], fake)
check("tools-dir chain falls through an unwritable dir to a writable one", chain.ensure().startswith(good))

# async: slow installer -> 202 style pending, then ready
slow = Installer("cursor", "9", [tempfile.mkdtemp()], lambda b: fake(b, 0.6), wait=0.1)
try:
    slow.ensure(); check("slow install returns InstallPending after the short wait", False)
except InstallPending as e:
    jid = e.job_id; check("slow install returns InstallPending (HTTP 202 + job id + Retry-After)", jid.startswith("inst_") and e.retry_after > 0)
time.sleep(0.9)
check("the job completed in the background and the next call hits the fast path", slow.find() is not None and slow.jobs[jid]["state"] == "done")

# concurrency: 8 threads, one installer call
calls.clear()
cc = Installer("qoder", "3", [tempfile.mkdtemp()], lambda b: fake(b, 0.2), wait=5)
out = []
ts = [threading.Thread(target=lambda: out.append(cc.ensure())) for _ in range(8)]
[x.start() for x in ts]; [x.join() for x in ts]
check("8 concurrent ensure() calls run the installer exactly once", len(calls) == 1 and len(set(out)) == 1, (len(calls), out))

# tamper: non-root-owned tree with a modified binary is not trusted
tree = chain.find(); open(os.path.join(tree, "bin", "codex"), "a").write("echo pwned\n")
check("a modified tool tree fails the digest re-check and is not returned", chain.find() is None)
try:
    Installer("x", "1", [tempfile.mkdtemp()], fake, mode="off").ensure(); ok = False
except InstallError as e:
    ok = e.code == "install.disabled"
check("mode=off / offline refuse with install.disabled", ok)
print(sum(R), "/", len(R)); sys.exit(0 if all(R) else 1)
