from enum import Enum


class SandboxState(str, Enum):
    PAUSED = "paused"
    RUNNING = "running"
    SNAPSHOTTING = "snapshotting"
    SNAPSHOT_FAILED = "snapshot_failed"

    def __str__(self) -> str:
        return str(self.value)
