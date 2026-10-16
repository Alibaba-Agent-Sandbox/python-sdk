"""Install, update and uninstall provider plugins. Nothing from a plugin is ever executed here."""

from __future__ import annotations

import contextlib
import datetime as _dt
import os
import re
import secrets
import shutil
import subprocess  # nosec B404 - audited argv-only subprocess boundary; no shell
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_sandbox._version import __version__
from agent_sandbox.models.errors import (
    ProviderConflictError,
    ProviderInstallError,
    ProviderNotFoundError,
    ProviderTrustError,
)
from agent_sandbox.providers import store
from agent_sandbox.providers.manifest import (
    MANIFEST_NAME,
    Manifest,
    check_requires,
    missing_manifest_error,
    parse_manifest,
)
from agent_sandbox.providers.settings import purge_provider_settings, set_default_provider
from agent_sandbox.utils.config_keys import BUILTIN_PROVIDER_ID
from agent_sandbox.utils.logging import get_logger

logger = get_logger("providers.installer")

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SCP_URL = re.compile(r"^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+:(?!//).+$")
_GIT_TIMEOUT = 120

#: Manifest aspects whose change forces a new consent on update.
RISK_ASPECTS = ("runtime", "security", "features", "inherit", "fields", "commands")


@dataclass
class InstallPlan:
    """Everything the consent screen shows."""

    manifest: Manifest
    source: dict[str, Any]
    tree_sha256: str
    trust: str
    previous: dict[str, Any] | None = None
    changes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        m = self.manifest
        return {
            "id": m.id,
            "name": m.name,
            "name_zh": m.name_zh,
            "version": m.version,
            "source": self.source,
            "tree_sha256": self.tree_sha256,
            "trust": self.trust,
            "runtime": list(m.command)
            if m.kind == "exec"
            else [m.kind, m.endpoint.get("base_url", "")],
            "kind": m.kind,
            "features": sorted(m.features),
            "commands": m.to_summary()["commands"],
            "security": m.security,
            "fields": [{"key": f.key, "secret": f.secret} for f in m.fields],
            "inherit": sorted(m.inherit),
            "changes": list(self.changes),
        }


ConfirmFn = Callable[[InstallPlan], bool]
VerifyFn = Callable[[str], None]


# ---------------------------------------------------------------- git


_SLUG_PART = re.compile(r"^[A-Za-z0-9_.-]+$")


def expand_catalog_ref(
    source: str, ref: str | None = None, subdir: str | None = None
) -> tuple[str, str | None, str | None]:
    """Turn ``owner/repo//subdir[@ref]`` into a GitHub URL plus subdir and ref.

    Same grammar as ``abx template install``: ``//`` is the directory inside the
    repository, ``@`` after that is the git ref. A full git URL, an scp-style
    ``git@host:path``, or a local path is returned unchanged. ``--ref`` and
    ``--subdir`` still work; giving both forms with different values is an error.
    """
    raw = source.strip()
    if (
        not raw
        or "://" in raw
        or raw.startswith("git@")
        or raw.startswith(("./", "/", "~"))
        or (len(raw) >= 3 and raw[1] == ":")
        or Path(raw).exists()
    ):
        return source, ref, subdir
    body = raw
    embedded_ref: str | None = None
    if "@" in body:
        body, embedded_ref = body.rsplit("@", 1)
    embedded_subdir: str | None = None
    if "//" in body:
        body, path = body.split("//", 1)
        embedded_subdir = path.strip("/") or None
    parts = body.split("/")
    if len(parts) != 2 or not all(_SLUG_PART.fullmatch(part) for part in parts):
        return source, ref, subdir
    if subdir and embedded_subdir and subdir.strip("/") != embedded_subdir:
        raise ProviderInstallError(
            "Subdirectory given both in SOURCE (after //) and as --subdir.",
            suggestion="Use one of them: owner/repo//subdir, or a git URL with --subdir.",
        )
    if ref and embedded_ref and ref != embedded_ref:
        raise ProviderInstallError(
            "Ref given both in SOURCE (after @) and as --ref.",
            suggestion="Use one of them: owner/repo//subdir@ref, or --ref.",
        )
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    url = f"https://github.com/{parts[0]}/{repo}.git"
    return url, ref or embedded_ref, (subdir.strip("/") if subdir else None) or embedded_subdir


def classify_source(source: str, *, allow_insecure: bool = False) -> tuple[str, str]:
    """Return ``("local", path)`` or ``("git", clean_url)``; reject unsafe git URLs."""
    local = Path(source).expanduser()
    if local.exists():
        return "local", str(local)
    url = source[4:] if source.startswith("git+") else source
    if _SCP_URL.match(url):
        return "git", url
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if not scheme and not url.startswith("ext::"):
        raise ProviderInstallError(
            f"Cannot fetch provider source: '{source}' is not a directory or a git URL.",
            suggestion=(
                "Pass a local directory, owner/repo//subdir[@ref], "
                "or an https://, ssh:// or git@host:path URL."
            ),
        )
    if url.startswith("ext::") or scheme not in ("https", "ssh", "http", "git", "file"):
        raise ProviderTrustError(
            f"Insecure provider source '{source}'.",
            suggestion="Use https:// or ssh:// (or --allow-insecure-transport for testing).",
        )
    if scheme in ("http", "git", "file") and not allow_insecure:
        raise ProviderTrustError(
            f"Insecure provider source '{source}'.",
            suggestion="Use https:// or ssh:// (or --allow-insecure-transport for testing).",
        )
    if scheme != "file" and "@" in parsed.netloc:
        userinfo = parsed.netloc.rsplit("@", 1)[0]
        if scheme != "ssh" or ":" in userinfo:
            raise ProviderTrustError(
                "Insecure provider source: credentials in URLs are not accepted.",
                suggestion="Use an SSH agent or a git credential helper (clone it yourself and "
                "install the directory).",
            )
    return "git", url


def _git_env(url: str, allow_insecure: bool, scratch: Path) -> dict[str, str]:
    empty_cfg = scratch / "gitconfig"
    empty_cfg.write_text("", encoding="utf-8")
    protocols = "https:ssh" + (":file:http:git" if allow_insecure else "")
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": protocols,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty_cfg),
        "HOME": str(scratch),
        "XDG_CONFIG_HOME": str(scratch),
        "LC_ALL": "C",
    }
    if url.startswith("ssh://") or _SCP_URL.match(url):
        for name in ("HOME", "SSH_AUTH_SOCK", "SSH_AGENT_PID"):
            if name in os.environ:
                env[name] = os.environ[name]
    if os.name == "nt":  # pragma: no cover - Windows only
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
    return env


def _git(args: list[str], *, cwd: Path, env: dict[str, str], stdin: bytes | None = None) -> bytes:
    hooks = cwd / ".empty-hooks"
    hooks.mkdir(exist_ok=True)
    cmd = [
        "git",
        "-c",
        f"core.hooksPath={hooks}",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "http.followRedirects=false",
        "-c",
        "protocol.ext.allow=never",
        "-c",
        "credential.helper=",
        *args,
    ]
    try:
        # Fixed git argv and constrained environment; no shell interpretation.
        proc = subprocess.run(  # noqa: S603  # nosec B603 - argv only; shell defaults to False
            cmd,
            cwd=cwd,
            env=env,
            input=stdin,
            capture_output=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ProviderInstallError(
            "Cannot fetch provider source: git is not installed.",
            suggestion="Install git or install the plugin from a local directory.",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProviderInstallError("Cannot fetch provider source: git timed out.") from exc
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["git failed"]
        raise ProviderInstallError(f"Cannot fetch provider source: {store.redact_url(tail[0])}.")
    return proc.stdout


def _parse_ls_tree(raw: bytes) -> list[tuple[str, str, int, str]]:
    """Parse ``git ls-tree -r -z -l`` into ``(mode, oid, size, path)``; only regular blobs pass."""
    out: list[tuple[str, str, int, str]] = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        meta, _, path_b = record.partition(b"\t")
        parts = meta.decode("ascii", "replace").split()
        if len(parts) != 4:
            raise ProviderInstallError("Unsafe entry in provider source (unparsable tree).")
        mode, typ, oid, size = parts
        path = path_b.decode("utf-8", "surrogateescape")
        if typ != "blob" or mode not in ("100644", "100755"):
            raise ProviderInstallError(f"Unsafe entry '{path}' in provider source.")
        out.append((mode, oid, int(size) if size.isdigit() else 0, path))
    return out


def fetch_git(
    url: str, *, ref: str | None, subdir: str | None, allow_insecure: bool
) -> tuple[list[store.FileEntry], str]:
    """Fetch a git source *without checking anything out*; returns ``(entries, commit_sha)``."""
    store.staging_dir()
    with tempfile.TemporaryDirectory(prefix="git-", dir=store.staging_dir()) as scratch_s:
        scratch = Path(scratch_s)
        repo = scratch / "repo.git"
        repo.mkdir()
        env = _git_env(url, allow_insecure, scratch)
        _git(["init", "--bare", "--quiet", "--template="], cwd=repo, env=env)
        target = ref or "HEAD"
        fetch = [
            "fetch",
            "--quiet",
            "--no-tags",
            "--no-recurse-submodules",
            "--filter=blob:limit=10m",
        ]
        try:
            _git([*fetch, "--depth", "1", url, target], cwd=repo, env=env)
        except ProviderInstallError:
            _git([*fetch, url, target], cwd=repo, env=env)
        commit = (
            _git(["rev-parse", "--verify", "FETCH_HEAD^{commit}"], cwd=repo, env=env)
            .decode()
            .strip()
        )
        if ref and _SHA40.match(ref) and commit != ref:
            raise ProviderInstallError(
                "Cannot fetch provider source: the server returned a different commit."
            )
        spec = f"{commit}:{subdir.strip('/')}" if subdir else commit
        if subdir:
            validate_subdir(subdir)
        listing = _git(["ls-tree", "-r", "-z", "-l", spec], cwd=repo, env=env)
        records = _parse_ls_tree(listing)
        if len(records) > store.MAX_FILES:
            raise ProviderInstallError(f"Provider source has more than {store.MAX_FILES} files.")
        total = 0
        for _mode, _oid, size, path in records:
            store.validate_rel_path(path)
            if size > store.MAX_FILE_BYTES:
                raise ProviderInstallError(
                    f"Unsafe entry '{path}' in provider source (file too large)."
                )
            total += size
        if total > store.MAX_TOTAL_BYTES:
            raise ProviderInstallError("Provider source exceeds the 50 MiB limit.")
        entries = _read_blobs(records, repo=repo, env=env)
    store.check_limits(entries)
    return entries, commit


def validate_subdir(subdir: str) -> None:
    s = subdir.strip("/")
    if not s or ".." in s.split("/") or s.startswith(("/", "-")) or "\\" in s or "\x00" in s:
        raise ProviderInstallError(f"Unsafe --subdir '{subdir}'.")


def _read_blobs(
    records: list[tuple[str, str, int, str]], *, repo: Path, env: dict[str, str]
) -> list[store.FileEntry]:
    if not records:
        return []
    request = ("\n".join(oid for _m, oid, _s, _p in records) + "\n").encode("ascii")
    raw = _git(["cat-file", "--batch"], cwd=repo, env=env, stdin=request)
    pos = 0
    entries: list[store.FileEntry] = []
    for mode, oid, _size, path in records:
        eol = raw.index(b"\n", pos)
        header = raw[pos:eol].decode("ascii", "replace").split()
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise ProviderInstallError(
                f"Cannot fetch provider source: missing object for '{path}'."
            )
        size = int(header[2])
        data = raw[eol + 1 : eol + 1 + size]
        pos = eol + 1 + size + 1
        entries.append(store.FileEntry(path, mode == "100755", data))
    return entries


# ---------------------------------------------------------------- install


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _manifest_from_entries(entries: list[store.FileEntry]) -> Manifest:
    for e in entries:
        if e.path == MANIFEST_NAME:
            return parse_manifest(e.data)
    raise missing_manifest_error()


def _diff_aspects(old: dict[str, Any], new: Manifest) -> list[str]:
    consented = old.get("consented", {})
    summary = new.to_summary()
    changed: list[str] = []
    if consented.get("runtime") != summary["runtime"]:
        changed.append("runtime")
    if consented.get("security") != summary["security"]:
        changed.append("security")
    if consented.get("features") != summary["features"]:
        changed.append("features")
    if not set(summary["inherit"]) <= set(consented.get("inherit", [])):
        changed.append("inherit")
    if consented.get("fields") != summary["fields"]:
        changed.append("fields")
    if consented.get("commands", []) != summary["commands"]:
        changed.append("commands")
    return changed


def _receipt(
    plan: InstallPlan, installed_by: dict[str, str] | None, manifest_sha: str
) -> dict[str, Any]:
    m = plan.manifest
    return {
        "receipt_version": store.RECEIPT_VERSION,
        "id": m.id,
        "version": m.version,
        "source": plan.source,
        "tree_sha256": plan.tree_sha256,
        "manifest_sha256": manifest_sha,
        "trust": plan.trust,
        "consented": m.to_summary(),
        "installed_at": _now(),
        "installed_by": installed_by or {"name": "agent-sandbox", "version": __version__},
    }


def prepare(
    source: str,
    *,
    ref: str | None = None,
    subdir: str | None = None,
    sha256: str | None = None,
    link: bool = False,
    allow_insecure_transport: bool = False,
) -> tuple[InstallPlan, list[store.FileEntry]]:
    """Fetch and validate a source; nothing is written to the store."""
    source, ref, subdir = expand_catalog_ref(source, ref, subdir)
    kind, location = classify_source(source, allow_insecure=allow_insecure_transport)
    if link:
        if kind != "local":
            raise ProviderInstallError("--link needs a local directory.")
        if os.name == "nt":
            raise ProviderTrustError("--link is not supported on Windows.")
        root = Path(location).resolve()
        from agent_sandbox.providers.manifest import load_manifest

        manifest = load_manifest(root)
        plan = InstallPlan(manifest, {"type": "link", "path": str(root)}, "", "link")
        return plan, []
    if kind == "local":
        root = Path(location).resolve()
        if subdir:
            validate_subdir(subdir)
            root = root / subdir.strip("/")
        entries = store.collect_local_dir(root)
        src: dict[str, Any] = {"type": "local", "path": str(root)}
        trust = "local"
    else:
        entries, commit = fetch_git(
            location, ref=ref, subdir=subdir, allow_insecure=allow_insecure_transport
        )
        src = {
            "type": "git",
            "url": store.redact_url(location),
            "ref": ref or "HEAD",
            "commit": commit,
            "subdir": subdir or "",
        }
        trust = "pinned" if ref and _SHA40.match(ref) else "unpinned"
    manifest = _manifest_from_entries(entries)
    digest = store.digest_files(entries)
    if sha256:
        if sha256.lower() != digest:
            from agent_sandbox.models.errors import ProviderIntegrityError

            raise ProviderIntegrityError(
                f"Tree digest mismatch: expected {sha256.lower()}, got {digest}.",
                suggestion="Review the plugin source and pass the digest you verified.",
            )
        trust = "pinned"
    return InstallPlan(manifest, src, digest, trust), entries


def _refuse_unpinned(
    plan: InstallPlan, *, interactive: bool, yes: bool, allow_unpinned: bool
) -> None:
    """Accept an unpinned git source (branch, tag, HEAD) only after review or ``--allow-unpinned``.

    ``yes`` alone confirms a reviewed, pinned install; it never accepts a moving ref.
    """
    if plan.trust != "unpinned" or allow_unpinned:
        return
    if interactive and not yes:
        return
    commit = plan.source.get("commit")
    why = "--yes does not accept a moving ref" if yes else "in non-interactive mode"
    raise ProviderTrustError(
        f"Refusing an unpinned git source without review ({why}).",
        suggestion=(
            f"Pin it: --ref {commit or '<40-hex commit>'} (or --sha256 <digest>); "
            "or pass --allow-unpinned to accept the current head."
        ),
    )


def install(
    source: str,
    *,
    ref: str | None = None,
    subdir: str | None = None,
    sha256: str | None = None,
    link: bool = False,
    force: bool = False,
    allow_unpinned: bool = False,
    allow_insecure_transport: bool = False,
    yes: bool = False,
    confirm: ConfirmFn | None = None,
    interactive: bool | None = None,
    verify: VerifyFn | None = None,
    installed_by: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Install a provider from a directory or git URL and return its receipt.

    Consent: pass ``yes=True`` (after the caller reviewed the plan) or a ``confirm`` callback that
    shows :meth:`InstallPlan.summary` and returns ``True``. Without either, a
    :class:`ProviderTrustError` (E8012) is raised. ``verify`` runs after the swap and may raise to
    roll back (used by update to run the plugin's ``initialize``).
    """
    interactive = (confirm is not None) if interactive is None else interactive
    catalog_source: dict[str, Any] | None = None
    if source.startswith("registry:"):
        from agent_sandbox.providers.catalog import materialize, registry_url

        catalog_id = source.split(":", 1)[1].strip()
        catalog_source = {"type": "catalog", "id": catalog_id, "registry": registry_url()}
        source = materialize(catalog_id)
    plan, entries = prepare(
        source,
        ref=ref,
        subdir=subdir,
        sha256=sha256,
        link=link,
        allow_insecure_transport=allow_insecure_transport,
    )
    manifest = plan.manifest
    check_requires(manifest, component="sdk", host_version=__version__)

    if plan.trust == "link" and not yes:
        raise ProviderTrustError(
            "--link requires --yes (the linked code is not pinned).",
            suggestion="Re-run with --yes after reviewing the directory.",
        )
    _refuse_unpinned(plan, interactive=interactive, yes=yes, allow_unpinned=allow_unpinned)

    existing = store.read_receipt(manifest.id)
    reserved = {BUILTIN_PROVIDER_ID}
    if manifest.id in reserved:
        raise ProviderConflictError("The built-in provider id is reserved.")
    if existing is not None and not force:
        raise ProviderConflictError(
            f"Provider id '{manifest.id}' is already installed.",
            suggestion="Re-run with --force to replace it.",
        )
    if existing is not None:
        plan.previous = existing
        plan.changes = _diff_aspects(existing, manifest)

    if not yes:
        if confirm is None:
            raise ProviderTrustError(
                "Installing a provider requires confirmation.",
                suggestion=f"Re-run with --yes after reviewing: abx provider install {source}"
                + (f" --subdir {plan.source['subdir']}" if plan.source.get("subdir") else "")
                + (f" --ref {plan.source['commit']}" if plan.source.get("commit") else ""),
            )
        if not confirm(plan):
            raise ProviderTrustError("Installation cancelled.")

    if catalog_source is not None and plan.source.get("type") == "local":
        plan.source = catalog_source
    receipt = _receipt(plan, installed_by, manifest.sha256)
    with store.store_lock():
        _swap_in(manifest.id, entries, receipt, link=plan.trust == "link", verify=verify)
    return receipt


def _return_data(src: Path, dest: Path) -> None:
    """Move a plugin's ``data/`` back where it came from (rollback); never raises."""
    if not src.exists() or dest.exists():
        return
    with contextlib.suppress(OSError, shutil.Error):
        shutil.move(str(src), str(dest))


def _swap_in(
    provider_id: str,
    entries: list[store.FileEntry],
    receipt: dict[str, Any],
    *,
    link: bool,
    verify: VerifyFn | None,
) -> None:
    final = store.provider_dir(provider_id)
    stage = store.staging_dir() / f"{provider_id}-{secrets.token_hex(4)}"
    trash: Path | None = None
    try:
        if link:
            stage.mkdir(parents=True)
            with contextlib.suppress(OSError):
                os.chmod(stage, 0o700)
        else:
            store.write_entries(entries, stage)
        store.write_receipt(stage, receipt)
        if final.exists():
            trash = store.trash_dir() / f"{provider_id}-{secrets.token_hex(4)}"
            try:
                os.replace(final, trash)
            except OSError as exc:
                raise ProviderInstallError(
                    f"Provider '{provider_id}' is in use ({exc.strerror or exc}).",
                    suggestion="Close programs using it and retry.",
                ) from exc
            if (trash / "data").exists():
                shutil.move(str(trash / "data"), str(stage / "data"))
        os.replace(stage, final)
    except BaseException:
        if trash is not None and trash.exists() and not final.exists():
            _return_data(stage / "data", trash / "data")
            with contextlib.suppress(OSError):
                os.replace(trash, final)
        store.remove_tree(stage)
        raise
    if verify is not None:
        try:
            verify(provider_id)
        except BaseException:
            if trash is not None and trash.exists():
                _return_data(final / "data", trash / "data")
                store.remove_tree(final)
                os.replace(trash, final)
            else:
                store.remove_tree(final)
            raise
    if trash is not None:
        store.remove_tree(trash)


# ---------------------------------------------------------------- update / uninstall


def _update_catalog(
    provider_id: str,
    src: dict[str, Any],
    receipt: dict[str, Any],
    *,
    check: bool,
    yes: bool,
    verify: VerifyFn | None,
) -> dict[str, Any]:
    """Re-fetch a ``registry:`` install. ``check`` only compares versions."""
    from agent_sandbox.providers.catalog import fetch_index, find

    recorded = str(src.get("registry") or "")
    previous = os.environ.get("ABX_PROVIDER_REGISTRY")
    if recorded:
        os.environ["ABX_PROVIDER_REGISTRY"] = recorded
    try:
        index = fetch_index()
        row = find(index, str(src.get("id") or provider_id))
        remote = str(row.get("version") or "")
        installed = str(receipt.get("version") or "")
        if check or remote == installed:
            return {
                "id": provider_id,
                "status": "up-to-date" if remote == installed else "available",
                "installed": installed,
                "available": remote,
                "changes": [],
            }
        if not yes:
            raise ProviderTrustError(
                f"Updating '{provider_id}' to {remote} requires confirmation.",
                suggestion=f"Re-run with --yes after reviewing version {remote}.",
            )
        new_receipt = install(
            f"registry:{src.get('id') or provider_id}",
            force=True,
            yes=True,
            verify=verify,
        )
    finally:
        if previous is None:
            os.environ.pop("ABX_PROVIDER_REGISTRY", None)
        else:
            os.environ["ABX_PROVIDER_REGISTRY"] = previous
    return {
        "id": provider_id,
        "status": "updated",
        "installed": installed,
        "available": remote,
        "changes": [],
        "receipt": new_receipt,
    }


def update(
    provider_id: str,
    *,
    ref: str | None = None,
    check: bool = False,
    yes: bool = False,
    confirm: ConfirmFn | None = None,
    allow_unpinned: bool = False,
    allow_insecure_transport: bool = False,
    verify: VerifyFn | None = None,
) -> dict[str, Any]:
    """Update one installed provider from its recorded source.

    Returns ``{"id", "status", "installed", "available", "changes"}`` where ``status`` is one of
    ``up-to-date``, ``pinned`` (pinned and no new ``ref`` given), ``available`` (``check=True``) or
    ``updated``. ``local``/``link`` installs raise :class:`ProviderInstallError`.
    """
    receipt = store.read_receipt(provider_id)
    if receipt is None:
        raise ProviderNotFoundError(f"Provider '{provider_id}' is not installed.")
    src = receipt.get("source", {})
    if src.get("type") == "catalog":
        return _update_catalog(
            provider_id,
            src,
            receipt,
            check=check,
            yes=yes,
            verify=verify,
        )
    if src.get("type") != "git":
        raise ProviderInstallError(
            f"Provider '{provider_id}' was installed from a local directory; reinstall it with "
            "'abx provider install --force <path>'."
        )
    if receipt.get("trust") == "pinned" and not ref:
        return {
            "id": provider_id,
            "status": "pinned",
            "installed": src.get("commit"),
            "available": None,
            "changes": [],
        }
    use_ref = ref or src.get("ref") or "HEAD"
    plan, entries = prepare(
        src["url"],
        ref=use_ref,
        subdir=src.get("subdir") or None,
        allow_insecure_transport=allow_insecure_transport,
    )
    if plan.manifest.id != provider_id:
        raise ProviderInstallError(
            f"Provider id changed from '{provider_id}' to '{plan.manifest.id}'; refusing to update."
        )
    plan.changes = _diff_aspects(receipt, plan.manifest)
    plan.previous = receipt
    same = plan.tree_sha256 == receipt.get("tree_sha256")
    result: dict[str, Any] = {
        "id": provider_id,
        "installed": src.get("commit"),
        "available": plan.source.get("commit"),
        "changes": plan.changes,
    }
    if same:
        return {**result, "status": "up-to-date"}
    if check:
        return {**result, "status": "available"}
    _refuse_unpinned(plan, interactive=confirm is not None, yes=yes, allow_unpinned=allow_unpinned)
    check_requires(plan.manifest, component="sdk", host_version=__version__)
    if not yes:
        if confirm is None:
            raise ProviderTrustError(
                "Installing a provider requires confirmation.",
                suggestion=f"Re-run with --yes after reviewing: abx provider update {provider_id}",
            )
        if not confirm(plan):
            raise ProviderTrustError("Update cancelled.")
    new_receipt = _receipt(plan, receipt.get("installed_by"), plan.manifest.sha256)
    with store.store_lock():
        _swap_in(provider_id, entries, new_receipt, link=False, verify=verify)
    return {**result, "status": "updated"}


def uninstall(provider_id: str, *, purge: bool = False) -> dict[str, Any]:
    """Remove an installed provider. Resets the default when it pointed at it."""
    if provider_id == BUILTIN_PROVIDER_ID:
        raise ProviderConflictError("The built-in provider cannot be removed.")
    if store.read_receipt(provider_id) is None and not store.provider_dir(provider_id).exists():
        raise ProviderNotFoundError(f"Provider '{provider_id}' is not installed.")
    from agent_sandbox.transport.config import collect_sources

    core_tbl = collect_sources().toml.get("core")
    was_default = isinstance(core_tbl, dict) and core_tbl.get("provider") == provider_id
    with store.store_lock():
        directory = store.provider_dir(provider_id)
        if purge:
            store.remove_tree(directory)
        else:
            # Keep the data directory unless purging; drop plugin files and the receipt.
            data = directory / "data"
            if data.exists():
                keep = store.trash_dir() / f"{provider_id}-data-{secrets.token_hex(4)}"
                shutil.move(str(data), str(keep))
                store.remove_tree(directory)
                directory.mkdir(parents=True)
                shutil.move(str(keep), str(directory / "data"))
                for child in directory.iterdir():
                    if child.name != "data":
                        store.remove_tree(child)
            else:
                store.remove_tree(directory)
    if purge:
        purge_provider_settings(provider_id)
    reset_default = False
    if was_default:
        set_default_provider(None)
        reset_default = True
    from agent_sandbox.providers import registry

    registry.forget(provider_id)
    return {"id": provider_id, "removed": True, "purged": purge, "default_reset": reset_default}
