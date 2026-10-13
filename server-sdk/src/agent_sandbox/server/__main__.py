"""``agent-sandbox-server`` command line (also ``python -m agent_sandbox.server``).

Sub-commands:

* ``serve`` - run the HTTP (and PTY WebSocket) server.
* ``healthcheck`` - ``GET /health`` against a running server; exit code 0/1 (Docker
  ``HEALTHCHECK`` / platform ``ready_cmd``).
* ``check-config`` - validate a policy, print the effective endpoint table and lint warnings.
* ``version`` - print the package version.

Stdlib only; ``healthcheck`` imports nothing heavy.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

from . import contract
from ._version import __version__

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-sandbox-server", description=__doc__.split("\n")[0]
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the sandbox server")
    serve.add_argument("--host", default="0.0.0.0")  # noqa: S104 (container-internal)
    serve.add_argument("--port", type=int, default=contract.DEFAULT_HTTP_PORT)
    serve.add_argument("--pty-port", type=int, default=None)
    serve.add_argument(
        "--commands",
        action="append",
        default=[],
        metavar="FILE_OR_MODULE",
        help="python file or module that registers commands/routes (repeatable)",
    )
    serve.add_argument("--policy", metavar="FILE", help="policy JSON file")
    serve.add_argument("--preset", help="policy preset (default, transfer-only, ...)")
    serve.add_argument("--base-dir", help="override ABX_SERVER_BASE_DIR")

    health = sub.add_parser("healthcheck", help="GET /health, exit 0 when healthy")
    health.add_argument("--host", default="127.0.0.1")
    health.add_argument("--port", type=int, default=contract.DEFAULT_HTTP_PORT)
    health.add_argument("--timeout", type=float, default=2.0)

    check = sub.add_parser("check-config", help="validate and lint a policy")
    check.add_argument("--policy", metavar="FILE")
    check.add_argument("--preset")
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.add_argument("--strict", action="store_true", help="exit 2 when lint warnings exist")
    check.add_argument("--explain", metavar="ENDPOINT", help="explain a decision for ENDPOINT")
    check.add_argument("--path", help="path for --explain")
    check.add_argument("--scopes", help="comma-separated scopes for --explain (default '*')")
    check.add_argument("--op", choices=["read", "write", "delete", "exec"])

    sub.add_parser("version", help="print the version")
    return parser


def _load_commands(spec: str) -> None:
    """Import a file or module so its registrations run."""
    if spec.endswith(".py") or os.path.sep in spec or os.path.isfile(spec):
        path = os.path.abspath(spec)
        module_spec = importlib.util.spec_from_file_location(
            f"_abx_user_commands_{abs(hash(path))}", path
        )
        if module_spec is None or module_spec.loader is None:
            raise SystemExit(f"cannot load commands file {spec!r}")
        module = importlib.util.module_from_spec(module_spec)
        sys.path.insert(0, os.path.dirname(path))
        module_spec.loader.exec_module(module)
    else:
        importlib.import_module(spec)


def _resolve_policy(args: argparse.Namespace) -> Any:
    from .policy import PolicyConfigError, ServerPolicy

    try:
        if args.policy:
            policy = ServerPolicy.from_file(args.policy)
            if args.preset:
                policy = policy.with_options(preset=args.preset)
            return policy
        if args.preset:
            return ServerPolicy.preset(args.preset)
        return ServerPolicy.from_environment()
    except PolicyConfigError as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _cmd_serve(args: argparse.Namespace) -> int:
    from .app import SandboxServer

    if args.base_dir:
        os.environ["ABX_SERVER_BASE_DIR"] = args.base_dir
    for spec in args.commands:
        _load_commands(spec)
    policy = _resolve_policy(args)
    try:
        server = SandboxServer(host=args.host, pty_port=args.pty_port, policy=policy)
    except ValueError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 1
    server.serve(args.port)
    return 0


def _cmd_healthcheck(args: argparse.Namespace) -> int:
    url = f"http://{args.host}:{args.port}/health"
    try:
        with urllib.request.urlopen(url, timeout=args.timeout) as resp:  # noqa: S310
            return 0 if resp.status == 200 else 1
    except (urllib.error.URLError, OSError, ValueError):
        return 1


def _cmd_check_config(args: argparse.Namespace) -> int:
    from .policy import PolicyConfigError, ServerPolicy

    policy = _resolve_policy(args) or ServerPolicy.from_dict({})
    try:
        engine = policy.bind()
    except PolicyConfigError as exc:
        print(f"policy error: {exc}", file=sys.stderr)
        return 1
    warnings = engine.lint()
    if args.policy:
        warnings.extend(_file_permission_warnings(args.policy))
    if args.explain:
        scopes = args.scopes.split(",") if args.scopes else None
        decision = engine.explain(args.explain, scopes=scopes, path=args.path, op=args.op)
        print(json.dumps(decision, indent=2))
        return 0 if decision["allowed"] else 3
    rows = []
    for name in sorted(engine._rules):
        rule = engine.rule_for(name)
        route = engine._routes[name]
        rows.append(
            {
                "endpoint": name,
                "group": route.group.value,
                "enabled": rule.enabled,
                "rule": rule.disabled_by or None,
                "scopes": list(rule.scopes),
                "limits": dict(rule.limits),
                "paths": {
                    "allow": list(rule.allow),
                    "deny": list(rule.deny),
                    "read_only": rule.read_only,
                },
            }
        )
    if args.json:
        print(
            json.dumps(
                {"revision": policy.revision, "endpoints": rows, "warnings": warnings}, indent=2
            )
        )
    else:
        print(f"policy {policy!r}")
        for row in rows:
            flag = "on " if row["enabled"] else "off"
            print(f"  [{flag}] {row['endpoint']:<24} scopes={','.join(row['scopes']) or '-'}")
        for warning in warnings:
            print(f"warning: {warning}")
    return 2 if warnings and args.strict else 0


def _file_permission_warnings(path: str) -> list[str]:
    out: list[str] = []
    if os.access(path, os.W_OK):
        out.append(f"L5: policy file {path} is writable by the current user")
    directory = os.path.dirname(os.path.abspath(path))
    if os.access(directory, os.W_OK):
        out.append(f"L5: policy directory {directory} is writable by the current user")
    return out


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    command = args.command or "serve"
    if command == "serve" and args.command is None:
        args = parser.parse_args(["serve", *(argv or [])])
    if command == "version":
        print(__version__)
        return 0
    if command == "healthcheck":
        return _cmd_healthcheck(args)
    if command == "check-config":
        return _cmd_check_config(args)
    return _cmd_serve(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
