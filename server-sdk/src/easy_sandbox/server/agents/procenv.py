"""Child-process environment, workspace preparation and file helpers."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import threading
from typing import TYPE_CHECKING

from .errors import RuntimeFailure

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .adapters.base import AgentAdapter, InvocationFile
    from .config import AgentSpec
    from .redact import Redactor

__all__ = [
    "PASSTHROUGH_ENV_VAR",
    "base_child_env",
    "build_child_env",
    "prepare_workspace",
    "write_invocation_file",
]

PASSTHROUGH_ENV_VAR = "EBX_AGENTS_PASSTHROUGH_ENV"

_ALLOWED_EXACT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "LANG",
        "LANGUAGE",
        "TERM",
        "TMPDIR",
        "TZ",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "NODE_EXTRA_CA_CERTS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "all_proxy",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "CODEX_HOME",
        "CLAUDE_CONFIG_DIR",
        "QWEN_HOME",
    }
)
_ALLOWED_PREFIXES = ("LC_", "NPM_CONFIG_", "npm_config_")
_DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def base_child_env(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The allowlisted subset of *environ* (default: ``os.environ``) for agent children.

    ``EBX_SERVER_TOKEN`` and every other server variable are *not* inherited.
    """
    source = os.environ if environ is None else environ
    extra = {n.strip() for n in source.get(PASSTHROUGH_ENV_VAR, "").split(",") if n.strip()}
    env = {
        k: v
        for k, v in source.items()
        if k in _ALLOWED_EXACT or k in extra or k.startswith(_ALLOWED_PREFIXES)
    }
    env.setdefault("PATH", _DEFAULT_PATH)
    env.setdefault("HOME", os.path.expanduser("~"))
    env.setdefault("NO_COLOR", "1")
    return env


def build_child_env(
    spec: AgentSpec,
    adapter: AgentAdapter,
    adapter_env: Mapping[str, str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Compose the child environment.

    Order (later wins): allowlist < runtime passthrough of the server's own
    credential variables < adapter-mapped provider credentials < ``env`` <
    ``secrets`` < MCP header/env carriers.
    """
    source = os.environ if environ is None else environ
    env = base_child_env(source)
    for name in adapter.passthrough_env:
        if name in source:
            env[name] = source[name]
    env.update(adapter_env)
    env.update(spec.env)
    env.update(spec.secrets)
    env.update(spec.mcp_env())
    return env


_workspace_locks: dict[str, threading.Lock] = {}
_workspace_locks_guard = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    with _workspace_locks_guard:
        return _workspace_locks.setdefault(path, threading.Lock())


def prepare_workspace(spec: AgentSpec, redact: Redactor, *, timeout: float = 900.0) -> str:
    """Create the workspace directory and clone ``workspace.git`` on first use.

    The git token travels in ``GIT_CONFIG_*`` environment variables of the git
    process only (never argv, never ``.git/config``).

    Returns:
        The absolute workspace path.

    Raises:
        RuntimeFailure: ``workspace_error`` when creation or cloning fails.
    """
    path = spec.workspace.path
    with _lock_for(path):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            raise RuntimeFailure(
                "workspace_error", f"cannot create workspace {path}: {exc}"
            ) from exc
        git = spec.workspace.git
        if git is None or os.path.isdir(os.path.join(path, ".git")):
            return path
        if os.listdir(path):
            raise RuntimeFailure(
                "workspace_error",
                f"workspace {path} is not empty and is not a git checkout; cannot clone {git.url}",
            )
        env = base_child_env()
        env["GIT_TERMINAL_PROMPT"] = "0"
        if git.token:
            basic = base64.b64encode(f"{git.token_user}:{git.token}".encode()).decode()
            env["GIT_CONFIG_COUNT"] = "1"
            env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
            env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic}"
        argv = ["git", "clone"]
        if git.depth:
            argv += ["--depth", str(git.depth)]
        if git.ref:
            argv += ["--branch", git.ref]
        argv += ["--", git.url, path]
        try:
            proc = subprocess.run(  # noqa: S603
                argv, env=env, capture_output=True, text=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeFailure("workspace_error", redact(f"git clone failed: {exc}")) from exc
        if proc.returncode != 0:
            raise RuntimeFailure(
                "workspace_error",
                redact(f"git clone failed: {(proc.stderr or proc.stdout)[-1500:]}"),
            )
        return path


def write_invocation_file(file: InvocationFile, workdir: str) -> None:
    """Write (or merge) one adapter-provided file with restrictive permissions."""
    directory = os.path.dirname(file.path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    content = file.content
    if file.merge_key and os.path.isfile(file.path):
        try:
            with open(file.path, encoding="utf-8") as fh:
                existing = json.load(fh)
            incoming = json.loads(file.content)
            if isinstance(existing, dict) and isinstance(incoming, dict):
                merged = existing.get(file.merge_key)
                merged = dict(merged) if isinstance(merged, dict) else {}
                merged.update(incoming.get(file.merge_key, {}))
                existing[file.merge_key] = merged
                content = json.dumps(existing, indent=2).encode("utf-8")
        except (OSError, ValueError):
            pass
    fd = os.open(file.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, file.mode)
    with os.fdopen(fd, "wb") as fh:
        fh.write(content)
    if file.git_exclude:
        _git_exclude(workdir, file.path)


def _git_exclude(workdir: str, path: str) -> None:
    info = os.path.join(workdir, ".git", "info")
    if not os.path.isdir(os.path.join(workdir, ".git")):
        return
    rel = os.path.relpath(path, workdir)
    if rel.startswith(".."):
        return
    exclude = os.path.join(info, "exclude")
    try:
        os.makedirs(info, exist_ok=True)
        existing = ""
        if os.path.isfile(exclude):
            with open(exclude, encoding="utf-8") as fh:
                existing = fh.read()
        if not re.search(rf"(?m)^/?{re.escape(rel)}$", existing):
            with open(exclude, "a", encoding="utf-8") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(rel + "\n")
    except OSError:
        pass
