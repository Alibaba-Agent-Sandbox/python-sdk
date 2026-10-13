"""Install / update / uninstall of provider plugins: trust, integrity and rollback."""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path

import pytest

from agent_sandbox.models.errors import (
    ProviderConflictError,
    ProviderInstallError,
    ProviderIntegrityError,
    ProviderManifestError,
    ProviderNotFoundError,
    ProviderTrustError,
    ProviderVersionError,
)
from agent_sandbox.providers import installer, registry, settings, store
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import (
    git,
    git_commit_all,
    init_repo,
    write_plugin,
)


def _install(src, **kw):
    kw.setdefault("yes", True)
    return installer.install(str(src), **kw)


def _seed_data(provider_id: str = "demo-prov") -> dict[str, bytes]:
    data = store.data_dir(provider_id)
    files = {
        "state.json": b'{"sandboxes": 2}',
        "nested/deep/cache.bin": bytes(range(256)),
        "empty-dir/.keep": b"",
    }
    for rel, blob in files.items():
        target = data / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    (data / "state.json").chmod(0o600)
    return files


def _snapshot_data(provider_id: str = "demo-prov") -> dict[str, tuple[bytes, int]]:
    data = store.data_dir(provider_id)
    return {
        str(p.relative_to(data)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in sorted(data.rglob("*"))
        if p.is_file()
    }


class TestLocalInstall:
    def test_installs_and_records_receipt(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        receipt = _install(src)
        assert receipt["id"] == "demo-prov" and receipt["trust"] == "local"
        assert receipt["source"]["type"] == "local"
        on_disk = store.read_receipt("demo-prov")
        assert on_disk["tree_sha256"] == store.digest_dir(store.provider_dir("demo-prov"))
        assert on_disk["consented"]["runtime"] == ["python3", "./provider.py"]
        assert store.list_installed_ids() == ["demo-prov"]
        assert registry.get_provider("demo-prov").id == "demo-prov"

    def test_store_permissions(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        (src / "run.sh").write_text("#!/bin/sh\n")
        os.chmod(src / "run.sh", 0o755)
        _install(src)
        root = store.provider_dir("demo-prov")
        assert oct(root.stat().st_mode & 0o777) == "0o700"
        assert oct((root / "provider.py").stat().st_mode & 0o777) == "0o600"
        assert (root / "run.sh").stat().st_mode & 0o111

    def test_consent_required(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        with pytest.raises(ProviderTrustError) as exc:
            installer.install(str(src))
        assert exc.value.code == "E8012"
        assert store.read_receipt("demo-prov") is None

    def test_confirm_callback_sees_plan(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        seen = []

        def deny(plan):
            seen.append(plan.summary())
            return False

        with pytest.raises(ProviderTrustError):
            installer.install(str(src), confirm=deny)
        assert seen[0]["id"] == "demo-prov" and seen[0]["runtime"] == ["python3", "./provider.py"]
        assert store.read_receipt("demo-prov") is None
        installer.install(str(src), confirm=lambda plan: True)
        assert store.read_receipt("demo-prov") is not None

    def test_duplicate_needs_force(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        _install(src)
        with pytest.raises(ProviderConflictError) as exc:
            _install(src)
        assert exc.value.code == "E8003"
        write_plugin(src, version="0.2.0")
        _install(src, force=True)
        assert store.read_receipt("demo-prov")["version"] == "0.2.0"

    def test_missing_manifest_and_bad_source(self, iso, tmp_path):  # noqa: F811
        (tmp_path / "empty").mkdir()
        with pytest.raises(ProviderManifestError):
            _install(tmp_path / "empty")
        with pytest.raises(ProviderInstallError):
            installer.install("definitely-not-a-source", yes=True)

    def test_builtin_id_is_reserved(self, iso, tmp_path):  # noqa: F811
        with pytest.raises((ProviderManifestError, ProviderConflictError)):
            _install(write_plugin(tmp_path / "src", id="alicloud-express"))

    def test_symlink_rejected(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        os.symlink("/etc/passwd", src / "link")
        with pytest.raises(ProviderInstallError):
            _install(src)

    def test_symlinked_dir_rejected(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        os.symlink("/etc", src / "etc-link")
        with pytest.raises(ProviderInstallError):
            _install(src)

    def test_hardlink_rejected(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        outside = tmp_path / "outside.txt"
        outside.write_text("x")
        os.link(outside, src / "hl")
        with pytest.raises(ProviderInstallError):
            _install(src)

    def test_top_level_data_dir_is_reserved(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src", files={"data/x.txt": "x"})
        with pytest.raises(ProviderInstallError):
            _install(src)

    def test_requires_incompatible_sdk(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        text = (src / "abx-provider.toml").read_text().replace('sdk = ">=0.3"', 'sdk = ">=99"')
        (src / "abx-provider.toml").write_text(text)
        with pytest.raises(ProviderVersionError):
            _install(src)

    def test_install_never_executes_plugin_code(self, iso, tmp_path):  # noqa: F811
        canary = tmp_path / "canary"
        src = write_plugin(
            tmp_path / "src",
            files={
                "provider.py": f"open({str(canary)!r}, 'w').write('ran')\n",
                "sitecustomize.py": f"open({str(canary)!r}, 'w').write('ran')\n",
            },
        )
        _install(src)
        registry.get_provider("demo-prov")
        store.verify_integrity("demo-prov")
        assert not canary.exists()

    def test_sha256_pin(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        plan, _ = installer.prepare(str(src))
        with pytest.raises(ProviderIntegrityError) as exc:
            _install(src, sha256="0" * 64)
        assert exc.value.code == "E8011"
        receipt = _install(src, sha256=plan.tree_sha256.upper())
        assert receipt["trust"] == "pinned"

    def test_link_requires_yes_and_skips_integrity(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        with pytest.raises(ProviderTrustError):
            installer.install(str(src), link=True, confirm=lambda p: True)
        receipt = _install(src, link=True)
        assert receipt["trust"] == "link"
        (src / "provider.py").write_text("print('changed')\n")
        store.verify_integrity("demo-prov")
        assert registry.get_provider("demo-prov").plugin_root == src.resolve()

    def test_failing_verify_rolls_back_to_previous_version(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src", version="1.0.0")
        _install(src)
        before = store.digest_dir(store.provider_dir("demo-prov"))
        write_plugin(src, version="2.0.0")

        def boom(pid):
            raise ProviderInstallError("handshake failed")

        with pytest.raises(ProviderInstallError):
            _install(src, force=True, verify=boom)
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        assert store.digest_dir(store.provider_dir("demo-prov")) == before
        store.verify_integrity("demo-prov")

    def test_failed_verify_rollback_restores_data_dir_exactly(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src", version="1.0.0")
        _install(src)
        _seed_data()
        before = _snapshot_data()
        assert before
        write_plugin(src, version="2.0.0")

        def boom(pid):
            raise ProviderInstallError("handshake failed")

        with pytest.raises(ProviderInstallError):
            _install(src, force=True, verify=boom)
        assert _snapshot_data() == before
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        store.verify_integrity("demo-prov")
        leftovers = [p for p in store.trash_dir().iterdir()] if store.trash_dir().exists() else []
        assert leftovers == []

    def test_failed_swap_rollback_restores_data_dir_exactly(
        self,
        iso,  # noqa: F811
        tmp_path,
        monkeypatch,
    ):
        src = write_plugin(tmp_path / "src", version="1.0.0")
        _install(src)
        _seed_data()
        before = _snapshot_data()
        write_plugin(src, version="2.0.0")
        real_replace = os.replace
        final = store.provider_dir("demo-prov")

        def flaky(a, b, *args, **kw):
            if Path(b) == final and Path(a).parent == store.staging_dir():
                raise OSError(13, "injected failure")
            return real_replace(a, b, *args, **kw)

        with monkeypatch.context() as patched:
            patched.setattr(installer.os, "replace", flaky)
            with pytest.raises(OSError, match="injected"):
                _install(src, force=True)
        assert _snapshot_data() == before
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        store.verify_integrity("demo-prov")

    def test_successful_update_keeps_data_dir(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src", version="1.0.0")
        _install(src)
        _seed_data()
        before = _snapshot_data()
        write_plugin(src, version="2.0.0")
        _install(src, force=True, verify=lambda pid: None)
        assert _snapshot_data() == before
        assert store.read_receipt("demo-prov")["version"] == "2.0.0"

    def test_failing_first_install_leaves_nothing(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")

        def boom(pid):
            raise ProviderInstallError("nope")

        with pytest.raises(ProviderInstallError):
            _install(src, verify=boom)
        assert store.list_installed_ids() == []
        assert not store.provider_dir("demo-prov").exists()

    def test_data_dir_survives_force_reinstall(self, iso, tmp_path):  # noqa: F811
        src = write_plugin(tmp_path / "src")
        _install(src)
        (store.data_dir("demo-prov") / "state.json").write_text("{}")
        write_plugin(src, version="0.2.0")
        _install(src, force=True)
        assert (store.data_dir("demo-prov") / "state.json").exists()
        store.verify_integrity("demo-prov")

    def test_lock_is_exclusive(self, iso):  # noqa: F811
        with store.store_lock(), pytest.raises(ProviderInstallError), store.store_lock(timeout=0.2):
            pass
        with store.store_lock(timeout=0.2):
            pass

    def test_stale_lock_is_broken(self, iso):  # noqa: F811
        store.providers_dir().mkdir(parents=True, exist_ok=True)
        lock = store.providers_dir() / ".lock"
        lock.write_text("123")
        os.utime(lock, (1, 1))
        with store.store_lock(timeout=0.5):
            pass

    def test_concurrent_installs_serialize(self, iso, tmp_path):  # noqa: F811
        srcs = [write_plugin(tmp_path / f"s{i}", id=f"prov-{c}") for i, c in enumerate("abc")]
        errors: list[BaseException] = []

        def run(src):
            try:
                _install(src)
            except BaseException as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(s,)) for s in srcs]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert store.list_installed_ids() == ["prov-a", "prov-b", "prov-c"]


class TestIntegrity:
    def test_tamper_detected(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        (store.provider_dir("demo-prov") / "provider.py").write_text("print('evil')\n")
        with pytest.raises(ProviderIntegrityError):
            store.verify_integrity("demo-prov")

    def test_extra_file_detected(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        (store.provider_dir("demo-prov") / "extra.py").write_text("x")
        with pytest.raises(ProviderIntegrityError):
            store.verify_integrity("demo-prov")

    def test_mode_change_detected(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        os.chmod(store.provider_dir("demo-prov") / "provider.py", 0o700)
        with pytest.raises(ProviderIntegrityError):
            store.verify_integrity("demo-prov")

    def test_data_dir_changes_are_not_tampering(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        (store.data_dir("demo-prov") / "x").write_text("state")
        store.verify_integrity("demo-prov")

    def test_not_installed(self, iso):  # noqa: F811
        with pytest.raises(ProviderNotFoundError):
            store.verify_integrity("nothing-here")


class TestUninstall:
    def test_removes_plugin_keeps_data_unless_purged(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        (store.data_dir("demo-prov") / "state").write_text("s")
        result = installer.uninstall("demo-prov")
        assert result["removed"] and not result["purged"]
        root = store.provider_dir("demo-prov")
        assert sorted(p.name for p in root.iterdir()) == ["data"]
        assert store.list_installed_ids() == []
        installer.uninstall("demo-prov", purge=True)
        assert not root.exists()

    def test_resets_default_and_purges_settings(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        iso.write_toml(
            '# my notes\n[core]\nprovider = "demo-prov"\n\n[providers.demo-prov]\nregion = "x"\n\n'
            '[providers.other]\nk = "v"\n'
        )
        result = installer.uninstall("demo-prov", purge=True)
        assert result["default_reset"] is True
        text = iso.toml.read_text()
        assert "demo-prov" not in text
        assert "# my notes" in text and "[providers.other]" in text

    def test_unknown_and_builtin(self, iso):  # noqa: F811
        with pytest.raises(ProviderNotFoundError):
            installer.uninstall("ghost")
        with pytest.raises(ProviderConflictError):
            installer.uninstall("alicloud-express")


class TestDefaultSetting:
    def test_roundtrip_preserves_other_content(self, iso):  # noqa: F811
        iso.write_toml('# top\n[transport]\nregion = "cn-beijing"\n')
        settings.set_default_provider("demo-prov")
        text = iso.toml.read_text()
        assert "# top" in text and 'region = "cn-beijing"' in text
        assert 'provider = "demo-prov"' in text
        settings.set_default_provider("other-one")
        assert iso.toml.read_text().count("provider =") == 1
        settings.set_default_provider("alicloud-express")
        assert "provider =" not in iso.toml.read_text()
        assert oct(iso.toml.stat().st_mode & 0o777) == "0o600"


class TestClassifySource:
    @pytest.mark.parametrize(
        "src",
        [
            "ext::sh -c 'x'",
            "http://example.com/r.git",
            "git://example.com/r.git",
            "file:///tmp/r",
            "ftp://x/y",
        ],
    )
    def test_insecure_rejected(self, iso, src):  # noqa: F811
        with pytest.raises(ProviderTrustError):
            installer.classify_source(src)

    @pytest.mark.parametrize(
        "src",
        [
            "https://user:pw@example.com/r.git",
            "https://token@example.com/r.git",
            "ssh://user:pw@example.com/r.git",
        ],
    )
    def test_credentials_in_url_rejected(self, iso, src):  # noqa: F811
        with pytest.raises(ProviderTrustError):
            installer.classify_source(src)

    @pytest.mark.parametrize(
        "src",
        [
            "https://example.com/r.git",
            "ssh://git@example.com/r.git",
            "git@example.com:org/r.git",
            "git+https://example.com/r",
        ],
    )
    def test_good_urls(self, iso, src):  # noqa: F811
        assert installer.classify_source(src)[0] == "git"

    def test_insecure_allowed_with_flag(self, iso):  # noqa: F811
        assert installer.classify_source("file:///tmp/r", allow_insecure=True)[0] == "git"

    def test_garbage(self, iso):  # noqa: F811
        with pytest.raises(ProviderInstallError):
            installer.classify_source("not a thing")

    def test_redact_url(self):
        assert store.redact_url("https://u:p@h.com/r") == "https://h.com/r"
        assert store.redact_url("https://h.com/r") == "https://h.com/r"


class TestPathSafety:
    @pytest.mark.parametrize(
        "path",
        [
            "",
            "/abs",
            "../x",
            "a/../../x",
            "a//b",
            "./a",
            "a\\b",
            "C:/x",
            "a/b/",
            "nul",
            "COM1.txt",
            "a/.",
            "x.",
            "x ",
            "a\x00b",
        ],
    )
    def test_rejects(self, path):
        with pytest.raises(ProviderInstallError):
            store.validate_rel_path(path)

    @pytest.mark.parametrize("path", ["a", "a/b.py", "dir/sub/file.txt", ".hidden", "a-b_c.d"])
    def test_accepts(self, path):
        store.validate_rel_path(path)

    def test_case_collisions_and_limits(self):
        e = store.FileEntry
        with pytest.raises(ProviderInstallError):
            store.check_limits([e("A.py", False, b""), e("a.py", False, b"")])
        with pytest.raises(ProviderInstallError):
            store.check_limits([e(f"f{i}", False, b"") for i in range(store.MAX_FILES + 1)])
        with pytest.raises(ProviderInstallError):
            store.check_limits([e("big", False, b"x" * (store.MAX_FILE_BYTES + 1))])


class TestGitInstall:
    @pytest.fixture
    def repo(self, tmp_path):
        repo = init_repo(tmp_path / "remote")
        write_plugin(repo, version="1.0.0")
        git_commit_all(repo, "v1")
        return repo

    def url(self, repo):
        return f"file://{repo}"

    def test_insecure_transport_needs_flag(self, iso, repo):  # noqa: F811
        with pytest.raises(ProviderTrustError):
            installer.install(self.url(repo), yes=True)

    def test_unpinned_refused_non_interactive(self, iso, repo):  # noqa: F811
        with pytest.raises(ProviderTrustError) as exc:
            installer.install(self.url(repo), yes=True, allow_insecure_transport=True)
        assert "unpinned" in str(exc.value).lower()
        assert store.read_receipt("demo-prov") is None

    def test_unpinned_allowed_explicitly(self, iso, repo):  # noqa: F811
        receipt = installer.install(
            self.url(repo), yes=True, allow_insecure_transport=True, allow_unpinned=True
        )
        assert receipt["trust"] == "unpinned"
        assert receipt["source"]["commit"] == git(repo, "rev-parse", "HEAD")
        assert receipt["source"]["type"] == "git"
        store.verify_integrity("demo-prov")
        assert not (store.provider_dir("demo-prov") / ".git").exists()

    def test_commit_pin_is_trusted_and_checked(self, iso, repo):  # noqa: F811
        commit = git(repo, "rev-parse", "HEAD")
        receipt = installer.install(
            self.url(repo), ref=commit, yes=True, allow_insecure_transport=True
        )
        assert receipt["trust"] == "pinned" and receipt["source"]["commit"] == commit

    def test_tag_is_unpinned(self, iso, repo):  # noqa: F811
        git(repo, "tag", "v1")
        with pytest.raises(ProviderTrustError):
            installer.install(self.url(repo), ref="v1", yes=True, allow_insecure_transport=True)
        receipt = installer.install(
            self.url(repo), ref="v1", yes=True, allow_insecure_transport=True, allow_unpinned=True
        )
        assert receipt["trust"] == "unpinned"

    def test_sha256_pins_a_branch(self, iso, repo):  # noqa: F811
        plan, _ = installer.prepare(self.url(repo), allow_insecure_transport=True)
        receipt = installer.install(
            self.url(repo), sha256=plan.tree_sha256, yes=True, allow_insecure_transport=True
        )
        assert receipt["trust"] == "pinned"

    def test_subdir(self, iso, tmp_path):  # noqa: F811
        repo = init_repo(tmp_path / "mono")
        write_plugin(repo / "plugins" / "one", id="sub-one")
        (repo / "README.md").write_text("mono")
        git_commit_all(repo)
        receipt = installer.install(
            self.url(repo),
            subdir="plugins/one",
            yes=True,
            allow_insecure_transport=True,
            allow_unpinned=True,
        )
        assert receipt["id"] == "sub-one" and receipt["source"]["subdir"] == "plugins/one"
        assert not (store.provider_dir("sub-one") / "README.md").exists()

    @pytest.mark.parametrize("subdir", ["../x", "/abs", "-flag", "a/../b"])
    def test_bad_subdir(self, iso, repo, subdir):  # noqa: F811
        with pytest.raises(ProviderInstallError):
            installer.install(
                self.url(repo),
                subdir=subdir,
                yes=True,
                allow_insecure_transport=True,
                allow_unpinned=True,
            )

    def test_symlink_in_repo_rejected(self, iso, tmp_path):  # noqa: F811
        repo = init_repo(tmp_path / "evil")
        write_plugin(repo)
        os.symlink("/etc/passwd", repo / "leak")
        git_commit_all(repo)
        with pytest.raises(ProviderInstallError):
            installer.install(
                self.url(repo), yes=True, allow_insecure_transport=True, allow_unpinned=True
            )
        assert store.read_receipt("demo-prov") is None

    def test_submodule_in_repo_rejected(self, iso, tmp_path):  # noqa: F811
        repo = init_repo(tmp_path / "subm")
        write_plugin(repo)
        git_commit_all(repo)
        git(repo, "update-index", "--add", "--cacheinfo", "160000", "a" * 40, "vendor")
        git(repo, "commit", "-q", "-m", "gitlink")
        with pytest.raises(ProviderInstallError):
            installer.install(
                self.url(repo), yes=True, allow_insecure_transport=True, allow_unpinned=True
            )

    def test_hooks_and_git_dir_are_not_executed_or_installed(self, iso, tmp_path):  # noqa: F811
        repo = init_repo(tmp_path / "hooky")
        write_plugin(repo)
        canary = tmp_path / "hook-ran"
        (repo / ".git" / "hooks" / "post-checkout").write_text(f"#!/bin/sh\ntouch {canary}\n")
        os.chmod(repo / ".git" / "hooks" / "post-checkout", 0o755)
        (repo / ".gitattributes").write_text("* filter=pwn\n")
        git_commit_all(repo)
        git(repo, "config", "filter.pwn.smudge", f"touch {canary}; cat")
        installer.install(
            self.url(repo), yes=True, allow_insecure_transport=True, allow_unpinned=True
        )
        assert not canary.exists()

    def test_update_flow(self, iso, repo):  # noqa: F811
        kw = {"yes": True, "allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), **kw)
        assert installer.update("demo-prov", **kw)["status"] == "up-to-date"
        write_plugin(repo, version="1.1.0")
        commit = git_commit_all(repo, "v1.1")
        res = installer.update("demo-prov", check=True, **kw)
        assert res["status"] == "available" and res["available"] == commit
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        res = installer.update("demo-prov", **kw)
        assert res["status"] == "updated"
        assert store.read_receipt("demo-prov")["version"] == "1.1.0"
        store.verify_integrity("demo-prov")

    def test_update_requires_new_consent_for_risky_changes(self, iso, repo):  # noqa: F811
        kw = {"allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), yes=True, **kw)
        write_plugin(
            repo,
            version="1.1.0",
            extra='[security]\nnetwork = ["*"]\n[core]\ninherit = ["sandbox_api_key"]\n',
        )
        git_commit_all(repo)
        with pytest.raises(ProviderTrustError):
            installer.update("demo-prov", **kw)
        seen = []

        def deny(plan):
            seen.append(plan.changes)
            return False

        with pytest.raises(ProviderTrustError):
            installer.update("demo-prov", confirm=deny, **kw)
        assert "security" in seen[0] and "inherit" in seen[0]
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        installer.update("demo-prov", confirm=lambda plan: True, **kw)
        assert store.read_receipt("demo-prov")["consented"]["inherit"] == ["sandbox_api_key"]

    def test_pinned_install_does_not_float(self, iso, repo):  # noqa: F811
        commit = git(repo, "rev-parse", "HEAD")
        installer.install(self.url(repo), ref=commit, yes=True, allow_insecure_transport=True)
        write_plugin(repo, version="9.9.9")
        git_commit_all(repo)
        res = installer.update("demo-prov", yes=True, allow_insecure_transport=True)
        assert res["status"] == "pinned"
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"

    def test_update_refuses_id_change(self, iso, repo):  # noqa: F811
        kw = {"yes": True, "allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), **kw)
        write_plugin(repo, id="renamed-prov", version="2.0.0")
        git_commit_all(repo)
        with pytest.raises(ProviderInstallError):
            installer.update("demo-prov", **kw)

    def test_update_rolls_back_on_failed_verify(self, iso, repo):  # noqa: F811
        kw = {"yes": True, "allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), **kw)
        write_plugin(repo, version="1.1.0")
        git_commit_all(repo)

        def boom(pid):
            raise ProviderInstallError("handshake")

        with pytest.raises(ProviderInstallError):
            installer.update("demo-prov", verify=boom, **kw)
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        store.verify_integrity("demo-prov")

    def test_update_rollback_after_failed_verify_keeps_data_dir(self, iso, repo):  # noqa: F811
        kw = {"yes": True, "allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), **kw)
        _seed_data()
        before = _snapshot_data()
        write_plugin(repo, version="1.1.0")
        git_commit_all(repo)

        def boom(pid):
            raise ProviderInstallError("handshake")

        with pytest.raises(ProviderInstallError):
            installer.update("demo-prov", verify=boom, **kw)
        assert _snapshot_data() == before
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        store.verify_integrity("demo-prov")

    def test_cli_update_accepts_allow_insecure_transport(self, iso, repo, capsys):  # noqa: F811
        from agent_sandbox.providers.__main__ import main

        kw = {"yes": True, "allow_insecure_transport": True, "allow_unpinned": True}
        installer.install(self.url(repo), **kw)
        write_plugin(repo, version="1.1.0")
        git_commit_all(repo)
        argv = ["--json", "update", "demo-prov", "--yes", "--allow-unpinned", "--no-verify"]
        assert main(argv) == 2  # file:// is refused without the flag (E8012)
        capsys.readouterr()
        assert store.read_receipt("demo-prov")["version"] == "1.0.0"
        assert main([*argv, "--allow-insecure-transport", "--check"]) == 0
        assert '"available"' in capsys.readouterr().out
        assert main([*argv, "--allow-insecure-transport"]) == 0
        assert store.read_receipt("demo-prov")["version"] == "1.1.0"

    def test_catalog_ref_uses_double_slash_for_the_subdirectory(self) -> None:
        """owner/repo//subdir[@ref] is the same grammar as template install."""
        assert installer.expand_catalog_ref(
            "alibaba-agent-sandbox/awesome-providers//opensandbox"
        ) == (
            "https://github.com/alibaba-agent-sandbox/awesome-providers.git",
            None,
            "opensandbox",
        )
        assert installer.expand_catalog_ref("acme/plugins//providers/one@v1.2.0") == (
            "https://github.com/acme/plugins.git",
            "v1.2.0",
            "providers/one",
        )
        url = "https://github.com/acme/plugins.git"
        assert installer.expand_catalog_ref(url, subdir="opensandbox") == (url, None, "opensandbox")
        with pytest.raises(ProviderInstallError, match="--subdir"):
            installer.expand_catalog_ref("acme/plugins//one", subdir="two")
        with pytest.raises(ProviderInstallError, match="--ref"):
            installer.expand_catalog_ref("acme/plugins//one@v1", ref="v2")

    def test_update_of_local_install_is_an_error(self, iso, tmp_path):  # noqa: F811
        _install(write_plugin(tmp_path / "src"))
        with pytest.raises(ProviderInstallError):
            installer.update("demo-prov", yes=True)

    def test_receipt_never_contains_credentials(self, iso, repo):  # noqa: F811
        installer.install(
            self.url(repo), yes=True, allow_insecure_transport=True, allow_unpinned=True
        )
        text = json.dumps(store.read_receipt("demo-prov"))
        assert "@" not in text.split('"url"')[1].split(",")[0]
        assert shutil.which("git")
