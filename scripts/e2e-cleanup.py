#!/usr/bin/env python3
"""Janitor for the real-cloud E2E suite: kill leftover sandboxes / delete leftover templates.

Only resources the suite itself created are touched:

* sandboxes whose metadata contains ``e2e=<run id>`` (``--run-id``) or any ``e2e`` tag (``--all-tagged``);
* templates whose alias/name starts with ``e2e-`` (``--prefix``);
* with ``--acr``: personal-ACR repositories in ``$ACR_NAMESPACE`` whose name starts with the prefix.

Nothing is deleted without ``--yes``; the default is a dry run that only lists candidates.
Credentials come from the environment / ``python-sdk/.env`` and are never printed.

    python scripts/e2e-cleanup.py                      # dry run, every e2e-tagged sandbox
    python scripts/e2e-cleanup.py --yes --all-tagged   # kill every e2e-tagged sandbox
    python scripts/e2e-cleanup.py --yes --run-id e2e-20261012070133-bad473 --templates --acr
    python scripts/e2e-cleanup.py --yes --older-than 30 --templates   # only things older than 30 min
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "e2e"))

import e2e_helpers as H  # noqa: E402

TAG_KEY = H.TAG_KEY


def _masked(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {H.mask(str(exc))[:160]}"


async def clean_sandboxes(args: argparse.Namespace) -> int:
    from easy_sandbox.api.sandbox import Sandbox

    cutoff = None
    if args.older_than:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=args.older_than)
    infos = await Sandbox.list(limit=500)
    victims = []
    for info in infos:
        tag = (info.metadata or {}).get(TAG_KEY)
        if not tag:
            continue
        if args.run_id and tag != args.run_id:
            continue
        if not args.run_id and not args.all_tagged:
            continue
        if cutoff and info.started_at and info.started_at > cutoff:
            continue
        victims.append((info.sandbox_id, tag, info.started_at))
    if not args.run_id and not args.all_tagged:
        print("[sandboxes] pass --run-id <id> or --all-tagged to select sandboxes; showing tagged ones:")
        for info in infos:
            tag = (info.metadata or {}).get(TAG_KEY)
            if tag:
                print(f"  candidate {info.sandbox_id} tag={tag} started={info.started_at}")
        return 0
    print(f"[sandboxes] {len(victims)} candidate(s) out of {len(infos)} listed")
    killed = 0
    for sid, tag, started in victims:
        print(f"  {'KILL' if args.yes else 'would kill'} {sid} tag={tag} started={started}")
        if args.yes:
            try:
                await Sandbox.kill_by_id(sid)
                killed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"    failed: {_masked(exc)}")
    return killed


async def clean_templates(args: argparse.Namespace) -> int:
    from easy_sandbox.api.template import TemplateManager
    from easy_sandbox.transport.auth import create_auth_provider
    from easy_sandbox.transport.config import load_config
    from easy_sandbox.transport.http import HttpClient

    cfg = load_config()
    http = HttpClient(cfg, create_auth_provider(api_key=cfg.api_key))
    deleted = 0
    try:
        manager = TemplateManager(http)
        for tpl in await manager.list():
            names = [*tpl.aliases]
            if not any(n.startswith(args.prefix) for n in names):
                continue
            print(f"  {'DELETE' if args.yes else 'would delete'} template {tpl.template_id} aliases={names}")
            if args.yes:
                try:
                    await manager.delete(tpl.template_id)
                    deleted += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"    failed: {_masked(exc)}")
    finally:
        await http.close()
    return deleted


def clean_acr(args: argparse.Namespace) -> int:
    import e2e_acr

    ak, sk, ns = os.environ.get("AccessKey", ""), os.environ.get("AccessSecret", ""), os.environ.get("ACR_NAMESPACE", "")
    if not (ak and sk and ns):
        print("[acr] skipped: AccessKey/AccessSecret/ACR_NAMESPACE not set")
        return 0
    deleted = 0
    for repo in e2e_acr.list_repos(ak, sk, ns):
        if not repo.startswith(args.prefix):
            continue
        print(f"  {'DELETE' if args.yes else 'would delete'} ACR repo <namespace>/{repo}")
        if args.yes and e2e_acr.delete_repo(ak, sk, ns, repo):
            deleted += 1
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-id", help="only resources tagged with this run id")
    parser.add_argument("--all-tagged", action="store_true", help="every sandbox carrying an e2e tag")
    parser.add_argument("--prefix", default=H.TEMPLATE_PREFIX, help="template / ACR repo name prefix (default e2e-)")
    parser.add_argument("--older-than", type=int, default=0, metavar="MIN", help="only sandboxes started more than MIN minutes ago")
    parser.add_argument("--templates", action="store_true", help="also delete templates with the prefix")
    parser.add_argument("--acr", action="store_true", help="also delete personal-ACR repos with the prefix")
    parser.add_argument("--yes", action="store_true", help="really delete (default: dry run)")
    args = parser.parse_args()

    H.load_env()
    if H.missing_env(H.REQUIRED_ENV):
        print(f"missing credentials {H.missing_env(H.REQUIRED_ENV)}; nothing to do", file=sys.stderr)
        return 2
    print(f"mode: {'DELETE' if args.yes else 'dry-run'}")
    killed = asyncio.run(clean_sandboxes(args))
    deleted = asyncio.run(clean_templates(args)) if args.templates else 0
    repos = clean_acr(args) if args.acr else 0
    print(f"summary: sandboxes_killed={killed} templates_deleted={deleted} acr_repos_deleted={repos}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
