"""On-disk provider store (``~/.ebx/providers``): layout, tree digest, receipts, locking."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from easy_sandbox.models.errors import (
    ProviderInstallError,
    ProviderIntegrityError,
    ProviderNotFoundError,
)
from easy_sandbox.transport import config as _config
from easy_sandbox.utils.config_keys import validate_provider_id

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

RECEIPT_NAME = ".ebx-install.json"
RECEIPT_VERSION = 1

MAX_FILES = 2000
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024

_EXCLUDED_TOP = {".git", RECEIPT_NAME}
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)


def providers_dir() -> Path:
    """Root of the store; follows the (patchable) location of ``config.toml``."""
    return _config._CONFIG_FILE.parent / "providers"


def provider_dir(provider_id: str) -> Path:
    return providers_dir() / provider_id


def data_dir(provider_id: str) -> Path:
    path = provider_dir(provider_id) / "data"
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    return path


@dataclass(frozen=True)
class FileEntry:
    """One regular file of a plugin tree."""

    path: str  # POSIX, relative
    executable: bool
    data: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


# ---------------------------------------------------------------- digest


def digest_from_entries(entries: Sequence[tuple[str, bool, str]]) -> str:
    """Tree digest from ``(path, executable, file_sha256_hex)`` triples.

    ``SHA-256( for each file sorted by UTF-8 path bytes: path + "\\0" + ("x"|"-") + "\\0" +
    file_sha256_hex + "\\n" )``. Paths are POSIX-style relative to the plugin root; ``.git/`` and
    ``.ebx-install.json`` are excluded by the callers.
    """
    h = hashlib.sha256()
    for path, executable, file_hash in sorted(entries, key=lambda e: e[0].encode("utf-8")):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(b"x" if executable else b"-")
        h.update(b"\x00")
        h.update(file_hash.encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def digest_files(entries: Sequence[FileEntry]) -> str:
    return digest_from_entries([(e.path, e.executable, e.sha256) for e in entries])


def digest_dir(root: Path) -> str:
    """Digest of an installed directory (re-computed from disk)."""
    triples: list[tuple[str, bool, str]] = []
    for path in _walk_regular(root):
        rel = path.relative_to(root).as_posix()
        with open(path, "rb") as fh:
            file_hash = hashlib.sha256(fh.read()).hexdigest()
        executable = bool(path.stat().st_mode & stat.S_IXUSR)
        triples.append((rel, executable, file_hash))
    return digest_from_entries(triples)


def _walk_regular(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir == Path("."):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_TOP and d != "data"]
            filenames = [f for f in filenames if f not in _EXCLUDED_TOP]
        dirnames.sort()
        for name in sorted(filenames):
            yield Path(dirpath) / name


# ---------------------------------------------------------------- path safety


def validate_rel_path(path: str) -> None:
    """Reject traversal, absolute/drive/NUL/backslash paths and reserved Windows names."""
    if not path or "\x00" in path or "\\" in path:
        raise ProviderInstallError(f"Unsafe entry '{path}' in provider source.")
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        raise ProviderInstallError(f"Unsafe entry '{path}' in provider source.")
    norm = posixpath.normpath(path)
    if norm != path or norm == ".." or norm.startswith("../") or norm.startswith("./"):
        raise ProviderInstallError(f"Unsafe entry '{path}' in provider source.")
    for part in path.split("/"):
        if part in ("", ".", "..") or _WIN_RESERVED.match(part) or part.endswith((".", " ")):
            raise ProviderInstallError(f"Unsafe entry '{path}' in provider source.")


def check_limits(entries: Sequence[FileEntry]) -> None:
    """File-count/size limits and case-fold collisions."""
    if len(entries) > MAX_FILES:
        raise ProviderInstallError(f"Provider source has more than {MAX_FILES} files.")
    total = 0
    seen: dict[str, str] = {}
    for e in entries:
        validate_rel_path(e.path)
        if e.path.split("/")[0] == "data":
            raise ProviderInstallError(
                "The top-level 'data/' directory is reserved for plugin state."
            )
        if len(e.data) > MAX_FILE_BYTES:
            raise ProviderInstallError(
                f"Unsafe entry '{e.path}' in provider source (file too large)."
            )
        total += len(e.data)
        folded = e.path.casefold()
        if folded in seen and seen[folded] != e.path:
            raise ProviderInstallError(
                f"Unsafe entry '{e.path}' in provider source (case collision)."
            )
        seen[folded] = e.path
    if total > MAX_TOTAL_BYTES:
        raise ProviderInstallError("Provider source exceeds the 50 MiB limit.")


def collect_local_dir(src: Path) -> list[FileEntry]:
    """Read a local plugin directory with the install safety rules (no symlinks/hardlinks)."""
    if not src.is_dir():
        raise ProviderInstallError(f"Cannot fetch provider source: '{src}' is not a directory.")
    entries: list[FileEntry] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=False):
        rel_dir = Path(dirpath).relative_to(src)
        dirnames[:] = sorted(
            d for d in dirnames if not (rel_dir == Path(".") and d in _EXCLUDED_TOP)
        )
        for d in dirnames:
            if (Path(dirpath) / d).is_symlink():
                raise ProviderInstallError(
                    f"Unsafe entry '{(rel_dir / d).as_posix()}' in provider source."
                )
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = (rel_dir / name).as_posix() if rel_dir != Path(".") else name
            if rel_dir == Path(".") and name in _EXCLUDED_TOP:
                continue
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_nlink > 1:
                raise ProviderInstallError(f"Unsafe entry '{rel}' in provider source.")
            if st.st_size > MAX_FILE_BYTES:
                raise ProviderInstallError(
                    f"Unsafe entry '{rel}' in provider source (file too large)."
                )
            total += st.st_size
            if total > MAX_TOTAL_BYTES or len(entries) >= MAX_FILES:
                raise ProviderInstallError("Provider source exceeds the size/file-count limits.")
            entries.append(FileEntry(rel, bool(st.st_mode & stat.S_IXUSR), full.read_bytes()))
    check_limits(entries)
    return entries


def write_entries(entries: Sequence[FileEntry], dest: Path) -> None:
    """Write validated entries under *dest* (dirs 0700, files 0600, +x only where set)."""
    dest.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(dest, 0o700)
    for e in entries:
        target = dest / e.path
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700 if e.executable else 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(e.data)
    for d in sorted(p for p in dest.rglob("*") if p.is_dir()):
        with contextlib.suppress(OSError):
            os.chmod(d, 0o700)


# ---------------------------------------------------------------- receipt


def read_receipt(provider_id: str) -> dict[str, Any] | None:
    path = provider_dir(provider_id) / RECEIPT_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_receipt(directory: Path, receipt: dict[str, Any]) -> None:
    path = directory / RECEIPT_NAME
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def redact_url(url: str) -> str:
    """Drop any userinfo from a URL for receipts and logs."""
    return re.sub(r"^([a-zA-Z][a-zA-Z0-9+.\-]*://)[^/@]*@", r"\1", url)


def verify_integrity(provider_id: str) -> dict[str, Any]:
    """Check the installed tree against its receipt; returns the receipt.

    Skipped (with trust ``link``) for development links. Raises :class:`ProviderIntegrityError`
    when the files changed since install and :class:`ProviderNotFoundError` when not installed.
    """
    directory = provider_dir(provider_id)
    receipt = read_receipt(provider_id)
    if receipt is None or not directory.exists():
        raise ProviderNotFoundError(f"Provider '{provider_id}' is not installed.")
    if receipt.get("trust") == "link":
        return receipt
    actual = digest_dir(directory.resolve())
    if actual != receipt.get("tree_sha256"):
        raise ProviderIntegrityError(
            f"Provider '{provider_id}': files changed since install.",
            suggestion=f"Reinstall or run 'ebx provider update {provider_id}'.",
        )
    return receipt


def list_installed_ids() -> list[str]:
    root = providers_dir()
    if not root.is_dir():
        return []
    ids = []
    for child in sorted(root.iterdir()):
        if child.name.startswith(".") or not (child.is_dir() or child.is_symlink()):
            continue
        if validate_provider_id(child.name) is None and (child / RECEIPT_NAME).exists():
            ids.append(child.name)
    return ids


# ---------------------------------------------------------------- lock


@contextlib.contextmanager
def store_lock(timeout: float = 10.0, stale_after: float = 300.0) -> Iterator[None]:
    """Exclusive install/update/uninstall lock (``O_EXCL`` file with stale detection)."""
    root = providers_dir()
    root.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(root, 0o700)
    lock = root / ".lock"
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > stale_after:
                    lock.unlink()
                    continue
            if time.monotonic() >= deadline:
                raise ProviderInstallError(
                    "Another provider install/update is in progress.",
                    suggestion=f"If none is running, remove {lock}.",
                ) from None
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def staging_dir() -> Path:
    path = providers_dir() / ".staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def trash_dir() -> Path:
    path = providers_dir() / ".trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def remove_tree(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path, ignore_errors=True)
