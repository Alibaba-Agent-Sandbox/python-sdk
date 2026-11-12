"""Canonical public v1 fixture; no runtime schema migration."""

from copy import deepcopy

MANIFEST = {
    "name": "test",
    "specVersion": 1,
    "sandbox": {
        "provider": "alicloud-express",
        "template": {"source": {"dockerfile": "Dockerfile"}},
        "services": {
            "app": {
                "protocol": "agent-sandbox-server",
                "version": 2,
                "port": 9000,
                "operations": ["commands.list", "commands.run"],
            }
        },
        "start": "python commands.py",
    },
}


def template_manifest(**extra):
    return {**deepcopy(MANIFEST), **extra}
