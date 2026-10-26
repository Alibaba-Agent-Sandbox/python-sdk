"""Opt-in real OSS persistence/RO acceptance using explicitly owned fixtures.

Provisioning is deliberately outside pytest. See e2e/README.md for the exact
prerequisites; no existing Volume is selected automatically.
"""

from __future__ import annotations

import errno
import json
import os
import re
import shlex
import uuid
from typing import Any

import e2e_helpers as helpers
import pytest

from agent_sandbox import Sandbox, SandboxNotFoundException


def _fixtures() -> tuple[str, str, str]:
    owner = os.environ.get("E2E_VOLUME_OWNER_RUN", "")
    rw = os.environ.get("E2E_VOLUME_RW_NAME", "")
    ro = os.environ.get("E2E_VOLUME_RO_NAME", "")
    if os.environ.get("E2E_VOLUME_ACCEPTANCE") != "owned-only":
        pytest.skip("requires E2E_VOLUME_ACCEPTANCE=owned-only and owned RW/RO OSS fixtures")
    if not re.fullmatch(r"abx-accept-[a-z0-9]{12}", owner):
        pytest.fail("E2E_VOLUME_OWNER_RUN must identify this invocation's owned abx-accept fixture")
    if rw != owner + "-rw" or ro != owner + "-ro":
        pytest.fail("RW/RO Volume names must exactly match E2E_VOLUME_OWNER_RUN + -rw/-ro")
    template = os.environ.get("E2E_VOLUME_TEMPLATE", "").strip()
    if not template:
        pytest.fail("E2E_VOLUME_TEMPLATE must explicitly select an eligible mount runtime")
    return rw, ro, template


def _command(sandbox: Any, script: str, settings: dict[str, str]) -> dict[str, Any]:
    command = "python3 -c " + shlex.quote(script) + " " + shlex.quote(json.dumps(settings))
    return json.loads(sandbox.commands.run(command, timeout=30).stdout)


# Never open/delete a sentinel until an exact kernel mount has been verified.
# O_EXCL and O_NOFOLLOW prevent overwriting another file, including a symlink.
_MOUNT = """import os,json,re,sys,stat,errno
c=json.loads(sys.argv[1]); p=c['path']; name=c['name']; expected=c['payload']
assert os.path.realpath(p)==p and os.path.isdir(p)
points=[re.sub(r'\\\\([0-7]{3})',lambda m:chr(int(m[1],8)),x.split()[4])
        for x in open('/proc/self/mountinfo')]
assert p in points
d=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
"""
_WRITE = (
    _MOUNT
    + """try:
 f=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=d)
 with os.fdopen(f,'w') as out:out.write(expected);out.flush();os.fsync(out.fileno())
 print(json.dumps({'written':True}))
finally:os.close(d)
"""
)
_READ = (
    _MOUNT
    + """try:
 f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=d)
 with os.fdopen(f) as source:assert source.read(len(expected)+1)==expected
 print(json.dumps({'persisted':True}))
finally:os.close(d)
"""
)
_READ_ONLY = (
    _MOUNT
    + """try:
 try:
  f=os.open(name+'-forbidden',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=d)
 except OSError as e:print(json.dumps({'write_errno':e.errno}))
 else:
  os.close(f);os.unlink(name+'-forbidden',dir_fd=d)
  raise AssertionError('RO fixture permits writes')
finally:os.close(d)
"""
)
_CLEAN = (
    _MOUNT
    + """try:
 try:f=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=d)
 except FileNotFoundError:pass
 else:
  with os.fdopen(f) as source:
   before=os.fstat(source.fileno());assert stat.S_ISREG(before.st_mode)
   assert source.read(len(expected)+1)==expected
  now=os.stat(name,dir_fd=d,follow_symlinks=False)
  assert (before.st_dev,before.st_ino)==(now.st_dev,now.st_ino)
  os.unlink(name,dir_fd=d)
 print(json.dumps({'clean':True}))
finally:os.close(d)
"""
)


def test_owned_oss_volume_persists_across_recreation_and_enforces_read_only(
    request: pytest.FixtureRequest,
) -> None:
    rw, ro, template = _fixtures()
    tracker = request.getfixturevalue("tracker")
    mount = "/mnt/abx-e2e/acceptance"
    settings = {
        "path": mount,
        "name": ".abx-owned-" + uuid.uuid4().hex,
        "payload": "abx-owned-persistence-" + uuid.uuid4().hex,
    }
    owned: list[Any] = []
    writer = None
    sentinel_attempted = False
    sentinel_clean = False

    def create(volume: str) -> Any:
        sandbox = Sandbox.create(
            template=template,
            timeout=300,
            metadata=helpers.tag_metadata("owned-oss-persistence-ro"),
            volume_mounts={mount: volume},
        )
        tracker.sandbox(sandbox.sandbox_id)
        owned.append(sandbox)
        return sandbox

    try:
        writer = create(rw)
        sentinel_attempted = True
        assert _command(writer, _WRITE, settings) == {"written": True}
        first_id = writer.sandbox_id
        assert writer.kill()
        writer = None
        with pytest.raises(SandboxNotFoundException):
            Sandbox.get_info(first_id)
        # A fresh creation, rather than reconnecting the same instance, proves
        # data outlives the first sandbox's actual deletion.
        writer = create(rw)
        assert _command(writer, _READ, settings) == {"persisted": True}
        reader = create(ro)
        assert _command(reader, _READ, settings) == {"persisted": True}
        result = _command(reader, _READ_ONLY, settings)
        assert result["write_errno"] in (errno.EROFS, errno.EACCES, errno.EPERM)
        assert _command(writer, _CLEAN, settings) == {"clean": True}
        sentinel_clean = True
    finally:
        try:
            if sentinel_attempted and not sentinel_clean:
                # Recover only our exclusive sentinel through an owned sandbox;
                # never remove a mismatched or symlinked object.
                if writer is None:
                    writer = create(rw)
                assert _command(writer, _CLEAN, settings) == {"clean": True}
        finally:
            for sandbox in owned:
                Sandbox.kill(sandbox.sandbox_id)
                with pytest.raises(SandboxNotFoundException):
                    Sandbox.get_info(sandbox.sandbox_id)
