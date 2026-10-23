"""Content identities for immutable workflow inputs (no machine paths in output)."""

from __future__ import annotations

import hashlib
import json


def bytes_digest(content: bytes) -> str:
    """Hash exact bytes; manifest identity includes formatting and all fields."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def snapshot_digest(files: dict[str, bytes]) -> str:
    """Hash eligible snapshot files by sorted portable relative paths and bytes.

    The snapshot producer must exclude ignored credentials before this call.
    Local eligible untracked inputs are included just like tracked inputs.
    """
    digest = hashlib.sha256()
    for name in sorted(files):
        if (
            not name
            or "\\" in name
            or "\0" in name
            or any(part in {"", ".", ".."} for part in name.split("/"))
        ):
            raise ValueError("snapshot paths must be normalized relative paths")
        digest.update(name.encode("utf-8") + b"\0" + files[name] + b"\0")
    return "sha256:" + digest.hexdigest()


def binding_digest(binding: dict[str, str]) -> str:
    """Hash validated string-only binding descriptors using sorted JSON keys."""
    if not isinstance(binding, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in binding.items()
    ):
        raise ValueError("binding must contain string keys and values")
    return bytes_digest(
        json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
