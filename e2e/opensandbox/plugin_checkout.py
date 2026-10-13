"""Locate the opensandbox plugin. This file is not a copy of the plugin.

The canonical source is https://github.com/alibaba-agent-sandbox/awesome-providers
(subdirectory ``opensandbox``). Harnesses in this directory start a local
OpenSandbox server and install that plugin; they do not vendor it.

Resolution order:

1. ``ABX_OPENSANDBOX_PLUGIN`` — a directory that contains ``abx-provider.toml``
2. ``ABX_AWESOME_PROVIDERS`` — a checkout of the catalog; uses ``opensandbox/``
3. ``git clone`` of ``ABX_AWESOME_PROVIDERS_URL`` (default the GitHub catalog)
   into a temp directory, then ``opensandbox/``
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

CATALOG_URL = os.environ.get(
    "ABX_AWESOME_PROVIDERS_URL",
    "https://github.com/alibaba-agent-sandbox/awesome-providers.git",
)


def _has_manifest(path: Path) -> bool:
    return (path / "abx-provider.toml").is_file()


def resolve_plugin() -> Path:
    direct = os.environ.get("ABX_OPENSANDBOX_PLUGIN")
    if direct:
        path = Path(direct).expanduser().resolve()
        if not _has_manifest(path):
            raise SystemExit(f"ABX_OPENSANDBOX_PLUGIN is not a plugin directory: {path}")
        return path

    root = os.environ.get("ABX_AWESOME_PROVIDERS")
    if root:
        path = Path(root).expanduser().resolve() / "opensandbox"
        if not _has_manifest(path):
            raise SystemExit(f"ABX_AWESOME_PROVIDERS has no opensandbox plugin: {path}")
        return path

    checkout = Path(tempfile.mkdtemp(prefix="awesome-providers-")) / "awesome-providers"
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", CATALOG_URL, str(checkout)],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise SystemExit(f"cannot clone {CATALOG_URL}: {detail}") from exc
    plugin = checkout / "opensandbox"
    if not _has_manifest(plugin):
        raise SystemExit(f"catalog checkout has no opensandbox plugin: {plugin}")
    return plugin
