"""``python -m easy_sandbox.providers`` — provider management without the ``ebx`` CLI.

Mirrors ``ebx provider ...``: ``list``, ``info``, ``install``, ``uninstall``, ``update``,
``default``, ``doctor``. Add ``--json`` for machine-readable output. Exit codes follow the shared
mapping (see :func:`easy_sandbox.providers.epp.exit_code_for`).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, Any

from easy_sandbox.models.errors import SandboxError
from easy_sandbox.providers import doctor as doctor_mod
from easy_sandbox.providers import installer, registry, settings
from easy_sandbox.providers.epp import exit_code_for

if TYPE_CHECKING:
    from collections.abc import Sequence


def _out(args: argparse.Namespace, data: Any, text: str) -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(text)


def _confirm(plan: installer.InstallPlan) -> bool:
    summary = plan.summary()
    sys.stderr.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    if not sys.stdin.isatty():
        return False
    sys.stderr.write("Install this provider? [y/N] ")
    sys.stderr.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def _cmd_list(args: argparse.Namespace) -> int:
    rows = registry.list_providers()
    default = registry.ambient_provider_id()
    for row in rows:
        row["default"] = row["id"] == default
    lines = [
        f"{'*' if r['default'] else ' '} {r['id']:<24} {r['version']:<10} "
        f"{r['kind']:<8} {r['trust']:<9} {r['name']}"
        for r in rows
    ]
    _out(args, rows, "\n".join(lines))
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    provider = registry.get_provider(args.id)
    data = provider.describe()
    receipt = None
    if args.id != "alicloud-express":
        from easy_sandbox.providers import store

        receipt = store.read_receipt(args.id)
    data["receipt"] = receipt
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    _out(args, data, text)
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    receipt = installer.install(
        args.source,
        ref=args.ref,
        subdir=args.subdir,
        sha256=args.sha256,
        link=args.link,
        force=args.force,
        allow_unpinned=args.allow_unpinned,
        allow_insecure_transport=args.allow_insecure_transport,
        yes=args.yes,
        confirm=None if args.yes else _confirm,
        verify=None if args.no_verify else doctor_mod.verify_handshake,
        installed_by={"tool": "python-sdk"},
    )
    _out(args, receipt, f"Installed {receipt['id']} {receipt.get('version', '')}")
    return 0


def _cmd_uninstall(args: argparse.Namespace) -> int:
    result = installer.uninstall(args.id, purge=args.purge)
    _out(args, result, f"Removed {args.id}")
    return 0


def _cmd_update(args: argparse.Namespace) -> int:
    ids = (
        [args.id]
        if args.id
        else [r["id"] for r in registry.list_providers() if r["trust"] not in ("builtin", "python")]
    )
    results = []
    for pid in ids:
        results.append(
            installer.update(
                pid,
                ref=args.ref,
                check=args.check,
                yes=args.yes,
                confirm=None if args.yes else _confirm,
                allow_unpinned=args.allow_unpinned,
                verify=doctor_mod.verify_handshake,
            )
        )
    _out(args, results, "\n".join(f"{r['id']}: {r['status']}" for r in results))
    return 0


def _cmd_default(args: argparse.Namespace) -> int:
    if args.id is None:
        current = registry.ambient_provider_id()
        _out(args, {"default": current}, current)
        return 0
    registry.get_provider(args.id)
    settings.set_default_provider(None if args.id == "alicloud-express" else args.id)
    _out(args, {"default": args.id}, f"Default provider: {args.id}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    pid = args.id or registry.ambient_provider_id()
    report = doctor_mod.doctor(pid, handshake=not args.no_handshake)
    lines = [
        f"{'ok  ' if c['ok'] else 'FAIL'} {c['name']}" + (f": {c['detail']}" if c["detail"] else "")
        for c in report["checks"]
    ]
    _out(args, report, "\n".join(lines))
    return 0 if report["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m easy_sandbox.providers")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list").set_defaults(func=_cmd_list)
    p = sub.add_parser("info")
    p.add_argument("id")
    p.set_defaults(func=_cmd_info)

    p = sub.add_parser("install")
    p.add_argument("source")
    p.add_argument("--ref")
    p.add_argument("--subdir")
    p.add_argument("--sha256")
    p.add_argument("--link", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--yes", "-y", action="store_true")
    p.add_argument("--allow-unpinned", action="store_true")
    p.add_argument("--allow-insecure-transport", action="store_true")
    p.add_argument("--no-verify", action="store_true")
    p.set_defaults(func=_cmd_install)

    p = sub.add_parser("uninstall")
    p.add_argument("id")
    p.add_argument("--purge", action="store_true")
    p.set_defaults(func=_cmd_uninstall)

    p = sub.add_parser("update")
    p.add_argument("id", nargs="?")
    p.add_argument("--ref")
    p.add_argument("--check", action="store_true")
    p.add_argument("--yes", "-y", action="store_true")
    p.add_argument("--allow-unpinned", action="store_true")
    p.set_defaults(func=_cmd_update)

    p = sub.add_parser("default")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=_cmd_default)

    p = sub.add_parser("doctor")
    p.add_argument("id", nargs="?")
    p.add_argument("--no-handshake", action="store_true")
    p.set_defaults(func=_cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except SandboxError as exc:
        if args.json:
            print(json.dumps({"error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return exit_code_for(exc)


if __name__ == "__main__":
    sys.exit(main())
