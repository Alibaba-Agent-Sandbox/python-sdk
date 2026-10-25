#!/usr/bin/env python3
"""Bind a release to its tag and verify existing/public PyPI artifact digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {"client-sdk": "agent-sandbox-client", "server-sdk": "agent-sandbox-server"}


def release_version(root: Path = ROOT) -> str:
    versions = []
    for path in (
        "client-sdk/src/agent_sandbox/_version.py",
        "server-sdk/src/agent_sandbox/server/_version.py",
    ):
        match = re.search(r'__version__\s*=\s*"([^"]+)"', (root / path).read_text())
        if not match:
            raise ValueError(f"Missing version in {path}")
        versions.append(match[1])
    if len(set(versions)) != 1:
        raise ValueError("Client and server versions must match")
    return versions[0]


def validate_tag(tag: str, version: str) -> None:
    if tag != f"v{version}":
        raise ValueError(f"Release must use tag v{version}; got {tag!r}")


def verify_files(files: list[Path], remote: dict, *, required: bool) -> None:
    hashes = {item["filename"]: item["digests"]["sha256"] for item in remote.get("urls", [])}
    for path in files:
        actual = hashes.get(path.name)
        if actual is None:
            if required:
                raise ValueError(f"Published artifact missing: {path.name}")
            continue
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Published artifact differs from candidate: {path.name}")


def public_artifacts(version: str, *, required: bool) -> None:
    for directory, package in PACKAGES.items():
        files = sorted((ROOT / "dist" / directory).glob("*"))
        if len(files) != 2 or not any(p.suffix == ".whl" for p in files):
            raise ValueError(f"Expected one wheel and one sdist for {package}")
        try:
            with urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=30) as response:
                remote = json.load(response)
        except HTTPError as exc:
            if exc.code != 404 or required:
                raise
            remote = {"urls": []}
        verify_files(files, remote, required=required)
        print(f"{package}: {'published' if required else 'existing'} files checked")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("candidate", "preflight", "published"))
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    version = release_version()
    if args.mode == "candidate":
        validate_tag(args.tag, version)
        print(f"Candidate {args.tag}: both distributions {version}")
    else:
        try:
            public_artifacts(version, required=args.mode == "published")
        except HTTPError as exc:
            if args.mode == "published" and exc.code == 404:
                print("Public PyPI metadata is not visible yet")
                raise SystemExit(75) from None  # Temporary publication propagation only.
            raise


if __name__ == "__main__":
    main()
