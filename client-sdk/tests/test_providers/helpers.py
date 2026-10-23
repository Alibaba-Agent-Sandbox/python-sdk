"""Builders for throw-away provider plugin trees and git repositories."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = REPO_ROOT / "examples" / "providers"
LOCAL_PROCESS = EXAMPLES / "local-process"
E2B_COMPATIBLE = EXAMPLES / "e2b-compatible"

MANIFEST = """\
manifest_version = 1
operation_contract_version = 1
[operations]
cli = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
python = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
[workflow]
inputs = ["managed"]
startups = ["exec", "none"]

[provider]
id = "{id}"
name = "{id}"
version = "{version}"

[compat]
requires = {{ sdk = ">=0.3" }}

[runtime]
kind = "exec"
command = ["python3", "./provider.py"]

[features]
supported = ["sandbox.lifecycle"]
{extra}
"""


def write_plugin(
    root: Path,
    *,
    id: str = "demo-prov",
    version: str = "0.1.0",
    extra: str = "",
    files: dict[str, str | bytes] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "abx-provider.toml").write_text(
        MANIFEST.format(id=id, version=version, extra=extra), encoding="utf-8"
    )
    (root / "provider.py").write_text("print('plugin')\n", encoding="utf-8")
    for rel, content in (files or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return root


def copy_local_process(dest: Path) -> Path:
    shutil.copytree(LOCAL_PROCESS, dest)
    return dest


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(repo: Path, *args: str) -> str:
    env = {**os.environ, **_GIT_ENV, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    out = subprocess.run(
        ["git", *args], cwd=repo, env=env, check=True, capture_output=True, text=True
    )
    return out.stdout.strip()


def git_commit_all(repo: Path, message: str = "c") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def init_repo(repo: Path) -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "main")
    return repo
