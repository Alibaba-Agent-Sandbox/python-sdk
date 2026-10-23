"""Current workflow fixture factory; no schema migration occurs at runtime."""

from copy import deepcopy

MANIFEST = {
    "name": "test",
    "spec_version": 4,
    "workflow_contract_version": 1,
    "provides": {
        "app": {
            "protocol": "agent-sandbox-server",
            "version": 2,
            "port": 9000,
            "operations": ["commands.list", "commands.run"],
        }
    },
    "default_workflow": "application",
    "start_cmd": "python commands.py",
    "workflows": {
        "application": {
            "kind": "application",
            "input": "source",
            "startup": "exec",
            "service": "app",
            "operation": "commands.run",
            "binding": {
                "transport": "http",
                "endpoint": "provider-port",
                "caller": "host",
                "authentication": "service-token",
            },
            "required_operations": [],
        }
    },
}


def workflow_manifest(**extra):
    return {**deepcopy(MANIFEST), **extra}
