#!/usr/bin/env python3
"""Install-flow E2E for the ``opensandbox`` plugin using the Python installer CLI.

Exercises ``python -m agent_sandbox.providers`` (the same code path as ``abx provider ...``) with a
throwaway ``HOME`` and a throwaway local bare git repository (``file://`` URL, pinned commit):

1.  install from a local path; receipt tree digest equals a fresh digest of the installed tree
2.  doctor, uninstall
3.  install from a git ``file://`` URL pinned to a 40-hex commit (needs
    ``--allow-insecure-transport``)
4.  safety rails: unpinned git refused, non-interactive install without ``--yes`` refused
5.  tamper detection: editing an installed file makes doctor fail (integrity) until reinstalled
6.  update (installer API; the CLI lacks ``--allow-insecure-transport`` for update): ``--check``,
    pinned-without-ref no-op, re-consent when features change,
    rollback when the new version fails its handshake
7.  uninstall (``--purge``), ``--link`` development install

If an OpenSandbox server is reachable (``ABX_OPENSANDBOX_BASE_URL``, default
``http://127.0.0.1:8080``) the git-installed plugin also creates and kills a real sandbox.

Usage::

    python3 provider_install_e2e.py [--keep]

Needs ``git`` and Node >= 20; ``agent_sandbox`` is taken from the sibling ``client-sdk/src``.
The plugin source is cloned from https://github.com/alibaba-agent-sandbox/awesome-providers
(``opensandbox/``), or taken from ``ABX_OPENSANDBOX_PLUGIN`` / ``ABX_AWESOME_PROVIDERS``.
This script does not keep a copy of the plugin.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from plugin_checkout import resolve_plugin

ROOT = Path(__file__).resolve().parents[2]
PLUGIN: Path  # set in main() from the awesome-providers catalog
sys.path[:0] = [str(ROOT / "client-sdk" / "src"), str(ROOT / "server-sdk" / "src")]

BASE_URL = (
    (os.environ.get("ABX_OPENSANDBOX_BASE_URL") or "http://127.0.0.1:8080")
    .rstrip("/")
    .removesuffix("/v1")
)
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(
        f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail and not ok else ""),
        flush=True,
    )
    return bool(ok)


class Env:
    def __init__(self, home: Path) -> None:
        self.home = home
        self.env = dict(os.environ)
        paths = [str(ROOT / "client-sdk" / "src"), str(ROOT / "server-sdk" / "src")]
        if self.env.get("PYTHONPATH"):
            paths.append(self.env["PYTHONPATH"])
        self.env.update(
            HOME=str(home),
            USERPROFILE=str(home),
            PYTHONPATH=os.pathsep.join(paths),
            PYTHONDONTWRITEBYTECODE="1",
        )
        for name in list(self.env):
            if name.startswith(("ABX_OPENSANDBOX_", "OPENSANDBOX_")):
                del self.env[name]
        self.env["ABX_OPENSANDBOX_BASE_URL"] = BASE_URL

    @property
    def provider_dir(self) -> Path:
        return self.home / ".abx" / "providers" / "opensandbox"

    def cli(self, *args: str, stdin: str | None = None) -> tuple[int, dict | list | None, str]:
        p = subprocess.run(
            [sys.executable, "-m", "agent_sandbox.providers", "--json", *args],
            env=self.env,
            cwd=str(self.home),
            text=True,
            input=stdin,
            capture_output=True,
            timeout=300,
            check=False,
        )  # fmt: skip
        try:
            data = json.loads(p.stdout) if p.stdout.strip() else None
        except json.JSONDecodeError:
            data = None
        return p.returncode, data, p.stderr

    def update(
        self, *args: str, ref: str | None = None, check: bool = False, yes: bool = False
    ) -> tuple[int, list | None, str]:
        """``python -m agent_sandbox.providers update`` with ``--allow-insecure-transport`` (file:// repos)."""
        argv = ["update", "opensandbox", "--allow-insecure-transport", *args]
        if ref:
            argv += ["--ref", ref]
        if check:
            argv.append("--check")
        if yes:
            argv.append("--yes")
        rc, data, err = self.cli(*argv)
        return rc, data if isinstance(data, list) else None, err

    def receipt(self) -> dict:
        return json.loads((self.provider_dir / ".abx-install.json").read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    from agent_sandbox.providers import store

    return store.digest_dir(path)


def git(cwd: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="e2e", GIT_AUTHOR_EMAIL="e2e@example.invalid",
               GIT_COMMITTER_NAME="e2e", GIT_COMMITTER_EMAIL="e2e@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)  # fmt: skip
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env, text=True, capture_output=True, check=True
    ).stdout.strip()


def copy_plugin(dest: Path) -> None:
    shutil.copytree(
        PLUGIN, dest, ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".pytest_cache")
    )


def server_healthy() -> bool:
    try:
        with urllib.request.urlopen(BASE_URL + "/health", timeout=3):
            return True
    except OSError:
        return False


def sdk_roundtrip(env: Env) -> str:
    code = (
        "import asyncio\nfrom agent_sandbox.api.sandbox import Sandbox\n"
        "async def m():\n"
        "    sb = await Sandbox.create(provider='opensandbox', timeout=120)\n"
        "    try:\n        print('OK', (await sb.commands.run('echo installed')).stdout.strip())\n"
        "    finally:\n        await sb.kill()\n"
        "asyncio.run(m())\n"
    )
    api_key = (
        os.environ.get("OPEN_SANDBOX_API_KEY")
        or os.environ.get("ABX_OPENSANDBOX_API_KEY")
        or os.environ.get("OPENSANDBOX_API_KEY")
    )
    e = dict(env.env)
    if api_key:
        e["OPEN_SANDBOX_API_KEY"] = api_key
    p = subprocess.run(
        [sys.executable, "-c", code],
        env=e,
        cwd=str(env.home),
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    return (
        p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "FAIL " + p.stderr.strip()[-200:]
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    if not shutil.which("git") or not shutil.which("node"):
        print("git and node are required", file=sys.stderr)
        return 2

    global PLUGIN
    try:
        PLUGIN = resolve_plugin()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="abx-osb-install-"))
    try:
        run_all(tmp)
    finally:
        if args.keep:
            print(f"kept {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok, _ in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        if not ok and detail:
            print(f"--- {name}\n{detail}")
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


def run_all(tmp: Path) -> None:
    home = tmp / "home"
    home.mkdir()
    env = Env(home)

    # 1-2. local path
    rc, data, err = env.cli("install", str(PLUGIN), "--yes")
    check(
        "local install succeeds",
        rc == 0 and isinstance(data, dict) and data.get("id") == "opensandbox",
        err,
    )
    receipt = env.receipt() if env.provider_dir.exists() else {}
    check("receipt trust is 'local'", receipt.get("trust") == "local", str(receipt.get("trust")))
    check(
        "receipt tree_sha256 equals fresh digest of installed tree",
        receipt.get("tree_sha256") == digest(env.provider_dir),
    )
    check(
        "installed tree matches source tree digest",
        receipt.get("tree_sha256") == digest_source(PLUGIN, tmp),
    )
    rc, data, err = env.cli("doctor", "opensandbox")
    check(
        "doctor ok (installed, integrity, config, handshake)", rc == 0 and data and data["ok"], err
    )
    rc, data, _ = env.cli("list")
    check(
        "list shows opensandbox as exec/local",
        any(r["id"] == "opensandbox" and r["kind"] == "exec" for r in (data or [])),
    )
    rc, _, err = env.cli("install", str(PLUGIN))
    check("non-interactive install without --yes is refused", rc != 0, err)
    rc, _, err = env.cli("install", str(PLUGIN), "--yes")
    check("re-install without --force is refused (conflict)", rc != 0, err)
    rc, data, err = env.cli("uninstall", "opensandbox")
    check(
        "uninstall removes the plugin",
        rc == 0 and not (env.provider_dir / "provider.mjs").exists(),
        err,
    )

    # 3. git file:// pinned
    work = tmp / "work"
    copy_plugin(work)
    git(work, "init", "-q", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "v1")
    sha1 = git(work, "rev-parse", "HEAD")
    bare = tmp / "origin.git"
    git(tmp, "clone", "-q", "--bare", str(work), str(bare))
    url = bare.as_uri()

    rc, _, err = env.cli("install", url, "--ref", sha1, "--yes")
    check("file:// git install is refused without --allow-insecure-transport", rc != 0, err)
    rc, _, err = env.cli("install", url, "--yes", "--allow-insecure-transport")
    check("unpinned git install is refused non-interactively", rc != 0, err)
    rc, data, err = env.cli("install", url, "--ref", sha1, "--yes", "--allow-insecure-transport")
    check("pinned git install succeeds", rc == 0, err)
    receipt = env.receipt() if env.provider_dir.exists() else {}
    check(
        "receipt trust is 'pinned' and records the commit",
        receipt.get("trust") == "pinned" and receipt.get("source", {}).get("commit") == sha1,
        json.dumps(receipt.get("source")),
    )
    check(
        "git receipt tree_sha256 equals fresh digest",
        receipt.get("tree_sha256") == digest(env.provider_dir),
    )
    check(
        "git and local trees have the same digest",
        receipt.get("tree_sha256") == digest_source(PLUGIN, tmp),
    )
    rc, data, err = env.cli("doctor", "opensandbox")
    check("doctor ok after git install", rc == 0 and data and data["ok"], err)
    if server_healthy():
        out = sdk_roundtrip(env)
        check("git-installed plugin drives a real sandbox", out == "OK installed", out)

    # 5. tamper
    entry = env.provider_dir / "provider.mjs"
    original = entry.read_bytes()
    entry.write_bytes(original + b"\n// tampered\n")
    rc, data, err = env.cli("doctor", "opensandbox")
    integrity = [c for c in (data or {}).get("checks", []) if c["name"] == "integrity"]
    check(
        "tampered file is detected by doctor (integrity)",
        rc != 0 and integrity and not integrity[0]["ok"],
        err,
    )
    entry.write_bytes(original)
    rc, data, _ = env.cli("doctor", "opensandbox")
    check("restoring the file restores integrity", rc == 0 and data and data["ok"])
    (env.provider_dir / "data").mkdir(exist_ok=True)
    (env.provider_dir / "data" / "note.txt").write_text("state", encoding="utf-8")
    rc, data, _ = env.cli("doctor", "opensandbox")
    check("data/ is excluded from the digest", rc == 0 and data and data["ok"])

    # 6. update
    rc, data, err = env.cli("update", "opensandbox")
    check(
        "update without --ref on a pinned install is a no-op ('pinned')",
        rc == 0 and data[0]["status"] == "pinned",
        err,
    )

    manifest = work / "abx-provider.toml"
    manifest.write_text(
        re.sub(
            r'(?m)^(version\s*=\s*)"0\.1\.0"', r'\g<1>"0.1.1"', manifest.read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )
    git(work, "commit", "-qam", "v2 version bump")
    sha2 = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", str(bare), "main")

    rc, _, err = env.cli("update", "opensandbox", "--ref", sha2, "--check")
    check("CLI 'update' refuses a file:// source without --allow-insecure-transport", rc != 0, err)
    rc, _, err = env.cli(
        "update", "opensandbox", "--ref", sha2, "--check", "--allow-insecure-transport"
    )
    check("CLI 'update --allow-insecure-transport' reaches a file:// source", rc == 0, err)
    rc, data, err = env.update(ref=sha2, check=True)
    check(
        "update --check reports 'available' without changing anything",
        rc == 0 and data[0]["status"] == "available" and env.receipt()["source"]["commit"] == sha1,
        err,
    )
    rc, _, err = env.update(ref=sha2)
    check(
        "update without --yes is refused non-interactively",
        rc != 0 and env.receipt()["source"]["commit"] == sha1,
        err,
    )
    rc, data, err = env.update(ref=sha2, yes=True)
    check(
        "update --ref <commit> --yes applies the new version",
        rc == 0
        and data[0]["status"] == "updated"
        and env.receipt()["source"]["commit"] == sha2
        and env.receipt().get("version") in ("0.1.1", None),
        err,
    )
    check("data/ survives update", (env.provider_dir / "data" / "note.txt").exists())
    check(
        "receipt digest valid after update",
        env.receipt()["tree_sha256"] == digest(env.provider_dir),
    )
    rc, data, err = env.update(ref=sha2, yes=True)
    check(
        "repeating the update reports 'up-to-date'",
        rc == 0 and data[0]["status"] == "up-to-date",
        err,
    )

    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(', "sessions"', ""), encoding="utf-8"
    )
    broken = work / "provider.mjs"
    broken.write_text("process.exit(7);\n", encoding="utf-8")
    git(work, "commit", "-qam", "v3 broken")
    sha3 = git(work, "rev-parse", "HEAD")
    git(work, "push", "-q", str(bare), "main")
    rc, _, err = env.update(ref=sha3, yes=True)
    check("update to a plugin that fails its handshake is rejected", rc != 0, err)
    check(
        "failed update rolled back (old commit, old files, doctor ok)",
        env.receipt()["source"]["commit"] == sha2
        and env.receipt()["tree_sha256"] == digest(env.provider_dir)
        and env.cli("doctor", "opensandbox")[0] == 0,
    )

    check(
        "data/ survives an update that was rolled back after a failed handshake",
        (env.provider_dir / "data" / "note.txt").exists(),
    )
    (env.provider_dir / "data").mkdir(exist_ok=True)
    (env.provider_dir / "data" / "note.txt").write_text("state", encoding="utf-8")

    # 7. uninstall + purge, link
    rc, data, err = env.cli("uninstall", "opensandbox")
    check(
        "uninstall keeps data/ by default",
        rc == 0
        and (env.provider_dir / "data" / "note.txt").exists()
        and not (env.provider_dir / "provider.mjs").exists(),
        err,
    )
    rc, _, err = env.cli("install", url, "--ref", sha1, "--yes", "--allow-insecure-transport")
    check("re-install after uninstall works", rc == 0, err)
    rc, data, err = env.cli("uninstall", "opensandbox", "--purge")
    check("uninstall --purge removes everything", rc == 0 and not env.provider_dir.exists(), err)
    rc, _, err = env.cli("install", str(PLUGIN), "--link")
    check("--link without --yes is refused", rc != 0, err)
    rc, data, err = env.cli("install", str(PLUGIN), "--link", "--yes")
    check("--link install succeeds", rc == 0 and env.receipt().get("trust") == "link", err)
    rc, data, err = env.cli("doctor", "opensandbox")
    check("doctor ok on a linked plugin", rc == 0 and data and data["ok"], err)
    rc, _, err = env.cli("uninstall", "opensandbox", "--purge")
    check(
        "uninstall a link leaves the source tree untouched",
        rc == 0 and (PLUGIN / "provider.mjs").exists(),
        err,
    )


def digest_source(plugin: Path, tmp: Path) -> str:
    """Digest of the plugin as the installer sees it (no VCS/node_modules noise)."""
    from agent_sandbox.providers import store

    entries = store.collect_local_dir(plugin)
    return store.digest_files(entries)


if __name__ == "__main__":
    sys.exit(main())
