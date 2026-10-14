"""Provider catalog.

The human registry site is https://registry.agent-sandbox.com. The official
site is https://www.agent-sandbox.com. The installer fetches ``REGISTRY_INDEX``
on registry.agent-sandbox.cn. The SDK ships only ``alicloud-express``. Every
other provider is installed from this index. A background check compares
installed versions and writes ``~/.abx/providers/updates.json``. It never
blocks the caller and ignores network errors.
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from agent_sandbox.models.errors import ProviderConfigError, ProviderNotFoundError
from agent_sandbox.providers import store

REGISTRY_INDEX = "https://registry.agent-sandbox.cn/providers/index.json"
_ENV_REGISTRY = "ABX_PROVIDER_REGISTRY"
_ENV_CHECK = "ABX_PROVIDER_UPDATE_CHECK"

_lock = threading.Lock()
_started = False


def registry_url() -> str:
    return (os.environ.get(_ENV_REGISTRY) or REGISTRY_INDEX).strip()


def fetch_index(*, timeout: float = 5, url: str | None = None) -> dict[str, Any]:
    """Load the catalog. A filesystem path or ``file:`` URL is read locally."""
    url = (url or registry_url()).strip()
    path = _local_path(url)
    if path is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_base"] = str(path.parent)
        return data
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    data["_base"] = url
    return data


def _local_path(url: str) -> Path | None:
    if url.startswith("file:"):
        return Path(url[5:])
    candidate = Path(url)
    if candidate.exists():
        return candidate
    return None


def find(index: dict[str, Any], provider_id: str) -> dict[str, Any]:
    for row in index.get("providers") or []:
        if isinstance(row, dict) and row.get("id") == provider_id:
            return row
    raise ProviderNotFoundError(
        f"Provider '{provider_id}' is not in the catalog.",
        suggestion=f"Check {registry_url()}.",
    )


def resolve_url(index: dict[str, Any], row: dict[str, Any]) -> str:
    raw = str(row.get("url") or "")
    if not raw:
        raise ProviderConfigError(f"Catalog entry '{row.get('id')}' has no url.")
    if raw.startswith(("https://", "http://", "file:")):
        return raw
    base = str(index.get("_base") or "")
    if base.startswith("http"):
        # Join against the directory that contains index.json, not the file itself.
        directory = base.rsplit("/", 1)[0] + "/"
        return urljoin(directory, raw)
    return str(Path(base) / raw)


def materialize(provider_id: str, *, timeout: float = 30, registry: str | None = None) -> str:
    """Return a local directory for *provider_id*, downloading a tarball when needed."""
    index = fetch_index(timeout=timeout, url=registry)
    row = find(index, provider_id)
    url = resolve_url(index, row)
    local = _local_path(url)
    if local is not None and local.is_dir():
        return str(local)
    digest = str(row.get("sha256") or "")
    return _download(url, digest, timeout=timeout)


def _download(url: str, digest: str, *, timeout: float) -> str:
    if not url.startswith("https://"):
        raise ProviderConfigError(f"Catalog download must be https: {url}")
    if not digest:
        raise ProviderConfigError(f"Catalog entry {url} has no sha256.")
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(store.MAX_TOTAL_BYTES + 1)
    if len(payload) > store.MAX_TOTAL_BYTES:
        raise ProviderConfigError(f"Catalog download for {url} exceeds the size limit.")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ProviderConfigError(f"Catalog download for {url} did not match sha256.")
    dest = Path(tempfile.mkdtemp(prefix="abx-provider-"))
    archive = dest / "provider.tar.gz"
    archive.write_bytes(payload)
    with tarfile.open(archive) as packed:
        packed.extractall(dest, filter="data")
    archive.unlink()
    children = [p for p in dest.iterdir() if p.is_dir()]
    if len(children) == 1 and not (dest / "abx-provider.toml").is_file():
        return str(children[0])
    return str(dest)


def pending_updates() -> list[dict[str, str]]:
    """Versions in the catalog that are newer than what is installed. Empty on failure."""
    try:
        index = fetch_index(timeout=3)
    except Exception:
        return []
    notes: list[dict[str, str]] = []
    for row in index.get("providers") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        provider_id = str(row["id"])
        remote = str(row.get("version") or "")
        receipt = store.read_receipt(provider_id)
        if receipt is None:
            continue
        installed = str(receipt.get("version") or "")
        if remote and _version_older(installed, remote):
            notes.append({"id": provider_id, "installed": installed, "version": remote})
    path = store.providers_dir() / "updates.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updates": notes}, indent=2) + "\n", encoding="utf-8")
    return notes


def _version_older(installed: str, remote: str) -> bool:
    """True when *remote* is a newer dotted version than *installed*."""

    def parts(text: str) -> tuple[int, ...]:
        nums: list[int] = []
        for piece in text.split("."):
            digits = ""
            for char in piece:
                if char.isdigit():
                    digits += char
                else:
                    break
            nums.append(int(digits or "0"))
        return tuple(nums)

    return parts(installed) < parts(remote)


def schedule_update_check() -> None:
    """Start one daemon thread. Tests and ``ABX_PROVIDER_UPDATE_CHECK=0`` skip it."""
    global _started
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get(_ENV_CHECK) == "0":
        return
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=pending_updates, name="abx-provider-update", daemon=True).start()
