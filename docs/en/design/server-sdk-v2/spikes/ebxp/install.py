"""Spike: lazy-install protocol on a read-only rootfs (design v2.1, 06-lazy-install.md).

Fast path is lock-free (marker + tree digest).  The lock lives in a WRITABLE dir (never next to the marker on a read-only
image).  Slow path runs on a job thread; callers wait a short time, then get InstallPending (HTTP 202 + job id).
"""
from __future__ import annotations
import fcntl, hashlib, json, os, threading, time, uuid


class InstallError(Exception):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.code, self.details = code, details


class InstallPending(Exception):
    def __init__(self, job_id, retry_after=5):
        super().__init__(f"install in progress: {job_id}")
        self.job_id, self.retry_after = job_id, retry_after


def tree_digest(path: str) -> str:
    h = hashlib.sha256()
    for dp, dn, fn in sorted(os.walk(path)):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, path).encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


def writable(d: str) -> bool:
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        return os.access(d, os.W_OK | os.X_OK)
    except OSError:
        return False


class Installer:
    def __init__(self, tool: str, version: str, dirs: list[str], install_fn, mode: str = "lazy", wait: float = 20.0):
        self.tool, self.version, self.dirs, self.install_fn, self.mode, self.wait = tool, version, dirs, install_fn, mode, wait
        self.jobs: dict[str, dict] = {}
        self._mu = threading.Lock()

    def _marker(self, d):
        return os.path.join(d, self.tool, self.version, ".installed")

    def find(self):
        """Lock-free fast path: first dir whose marker verifies (digest re-checked unless the tree is root-owned)."""
        for d in self.dirs:
            m = self._marker(d)
            try:
                meta = json.load(open(m))
            except (OSError, ValueError):
                continue
            tree = os.path.dirname(m)
            if os.stat(tree).st_uid != 0 and tree_digest(os.path.join(tree, "bin")) != meta["digest"]:
                continue
            return tree
        return None

    def ensure(self):
        hit = self.find()
        if hit:
            return hit
        if self.mode in ("off", "offline"):
            raise InstallError("install.disabled", f"{self.tool} is not installed and install mode is {self.mode!r}")
        target = next((d for d in self.dirs if writable(d)), None)
        if target is None:
            raise InstallError("install.read_only", f"no writable tools dir; tried {self.dirs}. "
                                                    f"Run `easy-sandbox-server prepare` at image build time, or set EBX_SERVER_TOOLS_DIR",
                               tried=list(self.dirs))
        with self._mu:
            job = next((j for j in self.jobs.values() if j["state"] == "running"), None)
            if job is None:
                jid = "inst_" + uuid.uuid4().hex[:12]
                job = self.jobs[jid] = {"id": jid, "state": "running", "error": None, "started": time.time()}
                threading.Thread(target=self._run, args=(job, target), daemon=True).start()
        deadline = time.time() + self.wait
        while time.time() < deadline and job["state"] == "running":
            time.sleep(0.02)
        if job["state"] == "running":
            raise InstallPending(job["id"])
        if job["state"] == "failed":
            raise InstallError("install.failed", job["error"])
        return self.find()

    def _run(self, job, target):
        lock_dir = os.path.join(target, ".locks")
        os.makedirs(lock_dir, mode=0o700, exist_ok=True)
        try:
            with open(os.path.join(lock_dir, f"{self.tool}-{self.version}.lock"), "w") as lk:
                fcntl.flock(lk, fcntl.LOCK_EX)                          # cross-process; per-dir
                if self.find():                                           # re-check after the lock
                    job["state"] = "done"
                    return
                tree = os.path.join(target, self.tool, self.version)
                tmp = tree + f".tmp-{os.getpid()}"
                os.makedirs(os.path.join(tmp, "bin"), exist_ok=True)
                self.install_fn(os.path.join(tmp, "bin"))
                json.dump({"digest": tree_digest(os.path.join(tmp, "bin")), "tool": self.tool, "version": self.version},
                          open(os.path.join(tmp, ".installed"), "w"))
                os.makedirs(os.path.dirname(tree), exist_ok=True)
                os.replace(tmp, tree)                                     # atomic publish
            job["state"] = "done"
        except Exception as exc:                                          # noqa: BLE001
            job["state"], job["error"] = "failed", str(exc)
