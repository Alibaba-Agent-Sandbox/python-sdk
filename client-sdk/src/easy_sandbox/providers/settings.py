"""Targeted, comment-preserving edits of ``config.toml`` / ``.env`` for provider settings."""

from __future__ import annotations

import contextlib
import os
import re
from typing import TYPE_CHECKING

from easy_sandbox.transport import config as _config
from easy_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID, provider_env_prefix

if TYPE_CHECKING:
    from pathlib import Path

_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def set_default_provider(provider_id: str | None, config_path: Path | None = None) -> None:
    """Write ``[core] provider = "<id>"`` (``None`` or the built-in id removes the key)."""
    path = config_path or _config._CONFIG_FILE
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    remove = provider_id is None or provider_id == BUILTIN_PROVIDER_ID
    out: list[str] = []
    in_core = False
    core_seen = False
    written = False
    for line in lines:
        m = _HEADER.match(line)
        if m:
            if in_core and not written and not remove:
                out.append(f'provider = "{provider_id}"')
                written = True
            in_core = m.group(1).strip() == "core"
            core_seen = core_seen or in_core
            out.append(line)
            continue
        if in_core and re.match(r"^\s*provider\s*=", line):
            if not remove and not written:
                out.append(f'provider = "{provider_id}"')
                written = True
            continue
        out.append(line)
    if not remove and not written:
        if core_seen and in_core:
            out.append(f'provider = "{provider_id}"')
        else:
            if out and out[-1].strip():
                out.append("")
            out.extend(["[core]", f'provider = "{provider_id}"'])
    if remove and not path.is_file():
        return
    _write(path, "\n".join(out) + "\n")


def purge_provider_settings(
    provider_id: str, config_path: Path | None = None, env_path: Path | None = None
) -> None:
    """Remove ``[providers.<id>]`` from config.toml and ``EBX_<ID>_*`` from the user ``.env``."""
    cfg = config_path or _config._CONFIG_FILE
    if cfg.is_file():
        keep: list[str] = []
        skipping = False
        target = f"providers.{provider_id}"
        for line in cfg.read_text(encoding="utf-8").splitlines():
            m = _HEADER.match(line)
            if m:
                skipping = m.group(1).replace(" ", "") == target
            if not skipping:
                keep.append(line)
        _write(cfg, "\n".join(keep) + "\n")
    env_file = env_path or cfg.parent / ".env"
    if env_file.is_file():
        prefix = provider_env_prefix(provider_id)
        kept = [
            ln
            for ln in env_file.read_text(encoding="utf-8").splitlines()
            if not re.match(rf"^\s*(export\s+)?{re.escape(prefix)}", ln)
        ]
        _write(env_file, "\n".join(kept) + ("\n" if kept else ""))
