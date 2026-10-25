"""Current template fixture factory; no schema migration occurs at runtime."""

from copy import deepcopy

MANIFEST = {
    "name": "test",
    "spec_version": 5,
    "provides": {
        "app": {
            "protocol": "agent-sandbox-server",
            "version": 2,
            "port": 9000,
            "operations": ["commands.list", "commands.run"],
        }
    },
    "start_cmd": "python commands.py",
}


def template_manifest(**extra):
    return {**deepcopy(MANIFEST), **extra}
