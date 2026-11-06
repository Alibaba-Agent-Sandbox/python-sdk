"""Conservative cooperative process-domain observation for the private bridge.

This is not isolation from hostile same-UID code. Any unreadable or unowned new
process prevents Session reuse; only provider destruction can then confirm stop.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from pathlib import Path

_SCOPE = b"ABX_MANAGED_TURN_SCOPE="


class ProcessDomain:
    """Observe PID identities, including children which changed session or parent."""

    def __init__(self, scope: str) -> None:
        self.scope = scope.encode()
        self.baseline: dict[int, tuple[str, str, bytes]] | None
        try:
            self.baseline = self._scan(environments=False)
        except OSError:
            self.baseline = None

    @staticmethod
    def _identity(path: Path) -> tuple[str, str]:
        # comm may contain spaces and ')'; fields after its final ')' are stable.
        fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
        return fields[19], fields[0]  # kernel starttime and process state

    @classmethod
    def _scan(
        cls,
        *,
        environments: bool = True,
        baseline: dict[int, tuple[str, str, bytes]] | None = None,
    ) -> dict[int, tuple[str, str, bytes]]:
        result = {}
        entries = list(Path("/proc").iterdir())
        if len(entries) > 10000:
            raise OSError("process_observation_budget")
        for path in entries:
            if not path.name.isdigit():
                continue
            try:
                if path.stat().st_uid != os.getuid():
                    continue
                start, state = cls._identity(path)
                if state == "Z":
                    continue
                pid = int(path.name)
                known = baseline is not None and pid in baseline and baseline[pid][0] == start
                environment = (path / "environ").read_bytes() if environments and not known else b""
                if len(environment) > 1048576:
                    raise OSError("process_environment_budget")
                result[pid] = start, state, environment
            except FileNotFoundError:
                continue  # exited before inspection
        return result

    def quiesce(self) -> bool:
        """Kill positively marked residuals; refuse reuse on incomplete attribution."""
        if self.baseline is None:
            return False
        try:
            current = self._scan(baseline=self.baseline)
            marker = _SCOPE + self.scope
            owned = {pid: row[0] for pid, row in current.items() if marker in row[2].split(b"\0")}
            for pid, start in owned.items():
                # Guard against PID reuse between enumeration and signal.
                with contextlib.suppress(ProcessLookupError, FileNotFoundError):
                    if self._identity(Path("/proc") / str(pid))[0] == start:
                        os.kill(pid, signal.SIGKILL)
            deadline = time.monotonic() + 2
            while True:
                current = self._scan(baseline=self.baseline)
                residual = any(marker in row[2].split(b"\0") for row in current.values())
                unknown = any(
                    pid not in self.baseline or self.baseline[pid][0] != row[0]
                    for pid, row in current.items()
                    if pid not in owned
                )
                if not residual:
                    return not unknown
                if time.monotonic() >= deadline:
                    return False
                time.sleep(0.02)
        except (OSError, ValueError, IndexError):
            return False
