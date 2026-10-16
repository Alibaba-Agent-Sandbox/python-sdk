"""Opt-in existing Volume acceptance; operate only on an exclusive sentinel."""

from __future__ import annotations

import json
import os
import re
import shlex
from uuid import uuid4

import pytest

from agent_sandbox import Sandbox
from agent_sandbox.models.errors import SandboxNotFoundError

_SCRIPT = r"""
import json, os, re, stat, sys
target, name, payload, mode = json.loads(sys.argv[1])
if os.path.realpath(target) != target or not os.path.isdir(target):
    raise RuntimeError('mount path unavailable or symlinked')
with open('/proc/self/mountinfo', encoding='utf-8') as mounts:
    points = [
        re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), line.split()[4])
        for line in mounts
    ]
if target not in points:
    raise RuntimeError('no exact kernel mount entry')
directory = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    if mode in ('roundtrip', 'write'):
        fd = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600, dir_fd=directory,
        )
        owned = os.fstat(fd)
        try:
            with os.fdopen(fd, 'wb') as sentinel:
                sentinel.write(payload.encode('ascii'))
                sentinel.flush()
                os.fsync(sentinel.fileno())
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(fd, 'rb') as sentinel:
                current = os.fstat(sentinel.fileno())
                if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                    raise RuntimeError('sentinel ownership changed')
                if sentinel.read(len(payload) + 1) != payload.encode('ascii'):
                    raise RuntimeError('sentinel read did not match')
        finally:
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode) or (
                current.st_dev, current.st_ino
            ) != (owned.st_dev, owned.st_ino):
                raise RuntimeError('ownership changed; no deletion attempted')
            if mode == 'roundtrip':
                os.unlink(name, dir_fd=directory)
    elif mode in ('cleanup', 'read-delete'):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            if mode == 'read-delete':
                raise RuntimeError('persisted sentinel is missing')
            pass
        else:
            with os.fdopen(fd, 'rb') as sentinel:
                owned = os.fstat(sentinel.fileno())
                if not stat.S_ISREG(owned.st_mode) or (
                    sentinel.read(len(payload) + 1) != payload.encode('ascii')
                ):
                    raise RuntimeError('ownership unproven; no deletion attempted')
            current = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                raise RuntimeError('ownership changed; no deletion attempted')
            os.unlink(name, dir_fd=directory)
    else:
        raise RuntimeError('unknown mode')
    print('ABX_VOLUME_' + mode.upper())
finally:
    os.close(directory)
"""


def _configuration() -> tuple[str, str, str]:
    # Resolve prerequisites before requesting sandbox_factory: its tracker finalizer
    # makes cloud calls, so even fixture construction must follow the opt-in guard.
    volume = os.environ.get("ABX_E2E_VOLUME_NAME", "")
    target = os.environ.get("ABX_E2E_VOLUME_MOUNT_PATH", "")
    template = os.environ.get("E2E_VOLUME_TEMPLATE", "").strip()
    if os.environ.get("ABX_E2E_VOLUME_MOUNT") != "1":
        pytest.skip("Volume E2E requires explicit ABX_E2E_VOLUME_MOUNT=1")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", volume) or not template:
        pytest.skip("Volume E2E needs an existing ABX_E2E_VOLUME_NAME and E2E_VOLUME_TEMPLATE")
    if len(target) > 512 or not re.fullmatch(
        r"/mnt/abx-e2e/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*", target
    ):
        pytest.skip("ABX_E2E_VOLUME_MOUNT_PATH must be a dedicated path under /mnt/abx-e2e/")
    return volume, target, template


def test_existing_volume_mount_read_write_cleanup(request, run):  # type: ignore[no-untyped-def]
    volume, target, template = _configuration()
    factory = request.getfixturevalue("sandbox_factory")
    sandbox = factory(
        template=template,
        provider="alicloud-express",
        volume_mounts={target: volume},
    )
    name, payload = f".abx-volume-{uuid4().hex}", f"abx-volume-{uuid4().hex}"

    def verify(mode: str) -> None:
        config = json.dumps([target, name, payload, mode])
        command = f"python3 -c {shlex.quote(_SCRIPT)} {shlex.quote(config)}"
        try:
            result = run(sandbox.commands.run(command, timeout=30))
        except Exception:
            raise RuntimeError(f"Volume {mode} failed; raw output omitted") from None
        if result.exit_code != 0 or result.stdout.strip() != f"ABX_VOLUME_{mode.upper()}":
            raise RuntimeError(f"Volume {mode} did not prove its postcondition; output omitted")

    try:
        verify("roundtrip")
    finally:
        # Independently recover an owned sentinel after an interrupted command.
        # The fixture releases the tagged sandbox even if this cleanup fails.
        verify("cleanup")


def test_volume_persists_after_sandbox_recreation(request, run):  # type: ignore[no-untyped-def]
    volume, target, template = _configuration()
    factory = request.getfixturevalue("sandbox_factory")
    first = factory(template=template, provider="alicloud-express", volume_mounts={target: volume})
    name, payload = f".abx-volume-{uuid4().hex}", f"abx-persist-{uuid4().hex}"

    def verify(sandbox, mode: str) -> None:  # type: ignore[no-untyped-def]
        config = json.dumps([target, name, payload, mode])
        command = f"python3 -c {shlex.quote(_SCRIPT)} {shlex.quote(config)}"
        try:
            result = run(sandbox.commands.run(command, timeout=30))
        except Exception:
            raise RuntimeError(f"Volume {mode} failed; raw output omitted") from None
        if result.exit_code != 0 or result.stdout.strip() != f"ABX_VOLUME_{mode.upper()}":
            raise RuntimeError(f"Volume {mode} did not prove its postcondition; output omitted")

    second = None
    first_deleted = False
    try:
        verify(first, "write")
        run(first.kill())
        with pytest.raises(SandboxNotFoundError):
            run(Sandbox.get_info_by_id(first.id))
        first_deleted = True
        second = factory(
            template=template, provider="alicloud-express", volume_mounts={target: volume}
        )
        assert second.id != first.id, "recreation did not create a different sandbox"
        verify(second, "read-delete")
    finally:
        if second is not None:
            verify(second, "cleanup")
        elif not first_deleted:
            verify(first, "cleanup")
        else:
            raise RuntimeError(
                f"Recreation failed; exclusive sentinel {name} needs cleanup in the test Volume"
            )
