"""Verify and prepare explicitly approved provider and interpreter archives."""

from __future__ import annotations

import contextlib
import gzip
import hashlib
import lzma
import os
import ssl
import stat
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent_sandbox.models.errors import ProviderProcessError, ProviderTimeoutError

if TYPE_CHECKING:
    from typing import BinaryIO

_MAX_BYTES = 256 * 1024 * 1024
_MAX_UNPACKED_BYTES = 512 * 1024 * 1024
_MAX_MEMBERS = 20_000
_CHUNK = 128 * 1024


class ProviderArtifact(BaseModel):
    """An immutable HTTPS tar archive approved by the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(gt=0, le=_MAX_BYTES)
    root: str

    @field_validator("url")
    @classmethod
    def https_only(cls, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.port == 0:
            raise ValueError("Artifact port must be greater than zero.")
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ch.isspace() for ch in url)
        ):
            raise ValueError("Use an HTTPS artifact URL without credentials, query or fragment.")
        return url

    @field_validator("root")
    @classmethod
    def valid_root(cls, root: str) -> str:
        if len(member_path(root).parts) != 1:
            raise ValueError("An archive root must be one directory.")
        return root


def member_path(value: str) -> PurePosixPath:
    if (
        any(part in {"", ".", ".."} for part in value.split("/"))
        or "\\" in value
        or ":" in value
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ValueError("Invalid archive path.")
    return PurePosixPath(value)


def _budget(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderTimeoutError("Provider artifact preparation timed out.")
    return remaining


def _verify(stream: BinaryIO, asset: ProviderArtifact, deadline: float) -> None:
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(_CHUNK):
        _budget(deadline)
        size += len(chunk)
        if size > asset.size:
            break
        digest.update(chunk)
    if size != asset.size or digest.hexdigest() != asset.sha256:
        raise ProviderProcessError("Provider artifact does not match its approved size or digest.")
    stream.seek(0)


def _download(asset: ProviderArtifact, destination: Path, deadline: float) -> None:
    with tempfile.NamedTemporaryFile(dir=destination.parent) as stage:
        try:
            with (
                httpx.Client(
                    trust_env=False,
                    verify=ssl.create_default_context(),
                    follow_redirects=False,
                    timeout=min(_budget(deadline), 20.0),
                ) as http,
                http.stream("GET", asset.url, headers={"Accept-Encoding": "identity"}) as response,
            ):
                response.raise_for_status()
                total = 0
                for chunk in response.iter_raw():
                    _budget(deadline)
                    total += len(chunk)
                    if total > asset.size:
                        raise ProviderProcessError("Provider artifact exceeds its approved size.")
                    stage.write(chunk)
        except httpx.HTTPError:
            raise ProviderProcessError(
                "Could not download the approved provider artifact."
            ) from None
        stage.flush()
        stage.seek(0)
        _verify(cast("BinaryIO", stage), asset, deadline)
        os.fsync(stage.fileno())
        _budget(deadline)
        # A concurrent prepare may have already published a verified copy.
        with contextlib.suppress(FileExistsError):
            os.link(stage.name, destination)


def unpack(
    asset: ProviderArtifact,
    cache: Path,
    destination: Path,
    *,
    download: bool,
    deadline: float,
    executable: str | None = None,
    license_file: str | None = None,
) -> None:
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = cache.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ProviderProcessError(
            "Use a private provider cache directory owned by the current user."
        )
    blob = cache / asset.sha256
    if not blob.exists() and download:
        _download(asset, blob, deadline)
    try:
        fd = os.open(blob, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        raise ProviderProcessError(
            "The approved provider artifact is missing from the cache."
        ) from None
    except OSError:
        raise ProviderProcessError(
            "Could not open the approved cached provider artifact."
        ) from None

    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != asset.size:
            raise ProviderProcessError(
                "The cached provider artifact has an unexpected type or size."
            )
        _verify(stream, asset, deadline)
        try:
            _extract(stream, asset.root, destination, deadline, executable, license_file)
        except (OSError, ValueError, tarfile.TarError, EOFError, lzma.LZMAError):
            raise ProviderProcessError(
                "The approved provider archive has an invalid layout."
            ) from None


class _ExtractionReader:
    def __init__(self, stream: BinaryIO, deadline: float) -> None:
        self._stream = stream
        self._deadline = deadline
        self._remaining = _MAX_UNPACKED_BYTES

    def read(self, count: int) -> bytes:
        _budget(self._deadline)
        data = self._stream.read(min(count, self._remaining + 1))
        self._remaining -= len(data)
        if self._remaining < 0:
            raise ValueError("Archive exceeds the decompressed byte limit.")
        return data


def _extract(
    stream: BinaryIO,
    root: str,
    destination: Path,
    deadline: float,
    executable: str | None,
    license_file: str | None,
) -> None:
    selected = {executable, license_file} if license_file else None
    extracted: set[str] = set()
    members: set[PurePosixPath] = set()
    total = 0
    magic = stream.read(6)
    stream.seek(0)
    if magic.startswith(b"\x1f\x8b"):
        decoded = cast("BinaryIO", gzip.GzipFile(fileobj=stream))
    elif magic == b"\xfd7zXZ\x00":
        decoded = cast("BinaryIO", lzma.LZMAFile(stream))  # noqa: SIM115
    else:
        raise ValueError("Expected a gzip or xz compressed tar archive.")
    reader = cast("BinaryIO", _ExtractionReader(decoded, deadline))
    with decoded, tarfile.open(fileobj=reader, mode="r|") as archive:
        for member in archive:
            _budget(deadline)
            path = member_path(member.name)
            if path.parts[0] != root or path in members:
                raise ValueError("Unexpected or repeated archive path.")
            members.add(path)
            total += member.size
            if len(members) > _MAX_MEMBERS or total > _MAX_UNPACKED_BYTES or member.size < 0:
                raise ValueError("Archive exceeds extraction limits.")
            relative = "/".join(path.parts[1:])
            if not relative and member.isdir():
                continue
            if not relative:
                raise ValueError("Archive root must be a directory.")
            if selected is not None and relative not in selected:
                continue
            target = destination.joinpath(*path.parts[1:])
            if member.isdir() and selected is None:
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.issparse():
                raise ValueError("Expected a regular archive member.")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Missing archive contents.")
            with source, target.open("xb") as output:
                while chunk := source.read(_CHUNK):
                    _budget(deadline)
                    output.write(chunk)
            if relative == executable:
                target.chmod(0o700)
            extracted.add(relative)
    if selected is not None and extracted != selected:
        raise ValueError("Missing runtime executable or license.")
