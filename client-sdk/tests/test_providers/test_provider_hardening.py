"""Provider hardening: manifest hint, unpinned installs, record mapping, rest feature gate."""

from __future__ import annotations

import pytest

from agent_sandbox.models import errors as E  # noqa: N812
from agent_sandbox.providers import installer, registry
from agent_sandbox.providers.base import compact_features, ordered_features
from agent_sandbox.providers.exec_provider import record_to_info
from agent_sandbox.providers.feature_gate import SANDBOX_RULES, gate_protocol
from agent_sandbox.providers.manifest import load_manifest
from agent_sandbox.transport.config import load_config
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import git, git_commit_all, init_repo, write_plugin


class TestMissingManifest:
    def test_plain_missing_manifest_points_at_the_subdir_option(self, tmp_path):
        with pytest.raises(E.ProviderManifestError) as exc:
            load_manifest(tmp_path)
        assert "--subdir" in exc.value.suggestion


class TestUnpinnedGitInstalls:
    @pytest.fixture
    def repo(self, tmp_path):
        repo = init_repo(tmp_path / "remote")
        write_plugin(repo, version="1.0.0")
        git_commit_all(repo, "v1")
        return repo

    def test_yes_alone_never_accepts_a_moving_ref(self, iso, repo):  # noqa: F811
        commit = git(repo, "rev-parse", "HEAD")
        with pytest.raises(E.ProviderTrustError) as exc:
            installer.install(f"file://{repo}", yes=True, allow_insecure_transport=True)
        assert f"--ref {commit}" in exc.value.suggestion

    def test_interactive_review_may_accept_an_unpinned_ref(self, iso, repo):  # noqa: F811
        shown = []
        receipt = installer.install(
            f"file://{repo}",
            allow_insecure_transport=True,
            confirm=lambda plan: shown.append(plan.manifest.sha256) or True,
        )
        assert receipt["trust"] == "unpinned"
        assert len(shown[0]) == 64

    def test_commit_pin_with_yes_is_accepted(self, iso, repo):  # noqa: F811
        commit = git(repo, "rev-parse", "HEAD")
        receipt = installer.install(
            f"file://{repo}", ref=commit, yes=True, allow_insecure_transport=True
        )
        assert receipt["trust"] == "pinned"


class TestInstallConfirmationHint:
    def test_the_rerun_hint_keeps_the_subdir_and_the_commit(self, iso, tmp_path):  # noqa: F811
        repo = init_repo(tmp_path / "mono")
        write_plugin(repo / "plugins" / "demo", version="1.0.0")
        git_commit_all(repo, "v1")
        commit = git(repo, "rev-parse", "HEAD")
        with pytest.raises(E.ProviderTrustError) as exc:
            installer.install(
                f"file://{repo}",
                subdir="plugins/demo",
                ref=commit,
                allow_insecure_transport=True,
            )
        assert f"--subdir plugins/demo --ref {commit}" in exc.value.suggestion


class TestRecordToInfo:
    def test_region_is_empty_unless_the_plugin_reports_one(self):
        info = record_to_info({"sandbox_id": "s1", "status": "running"}, "p")
        assert info.region == ""
        assert info.envd_url == "epp://p/s1"
        assert record_to_info({"sandbox_id": "s1", "region": "eu-1"}, "p").region == "eu-1"

    def test_timeout_is_the_reported_lifetime(self):
        info = record_to_info(
            {
                "sandbox_id": "s1",
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-01T00:10:00Z",
            },
            "p",
        )
        assert info.timeout == 600

    def test_timeout_is_zero_when_the_plugin_reports_no_lifetime(self):
        assert record_to_info({"sandbox_id": "s1"}, "p").timeout == 0


class TestSandboxProtocolUnknownIfAbsent:
    def test_plugin_wire_leaves_absent_region_and_timeout_unknown(self):
        from agent_sandbox.providers.shared.e2b.sandbox import SandboxProtocol

        bare = {"sandboxID": "s1", "templateID": "base"}
        platform = SandboxProtocol(None)._info(bare)  # type: ignore[arg-type]
        assert (platform.region, platform.timeout) == ("cn-hangzhou", 300)
        plugin = SandboxProtocol(None, unknown_if_absent=True)  # type: ignore[arg-type]
        info = plugin._info(bare)
        assert (info.region, info.timeout) == ("", 0)
        info = plugin._info({**bare, "region": "eu-1", "timeout": 60})
        assert (info.region, info.timeout) == ("eu-1", 60)


REST_MANIFEST = """
manifest_version = 1
operation_contract_version = 1
[operations]
cli = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
python = [
  "sandbox.create",
  "sandbox.get",
  "sandbox.list",
  "sandbox.delete",
  "exec.run",
  "files.read",
  "files.write",
  "files.list",
  "files.stat",
  "files.remove",
  "files.move",
  "ports.resolve",
]
[workflow]
inputs = ["managed"]
startups = ["exec", "none"]
[provider]
id = "rest-lite"
version = "0.1.0"
[runtime]
kind = "rest"
[endpoint]
base_url = "http://127.0.0.1:9"
[features]
supported = ["sandbox.lifecycle"]
[core]
inherit = ["sandbox_api_key"]
"""


class TestRestFeatureGate:
    async def test_undeclared_features_fail_with_e8004_before_any_request(
        self,
        iso,  # noqa: F811
        tmp_path,
        monkeypatch,
    ):
        plugin = tmp_path / "rest-lite"
        plugin.mkdir()
        (plugin / "abx-provider.toml").write_text(REST_MANIFEST)
        installer.install(str(plugin), yes=True)
        monkeypatch.setenv("ABX_SANDBOX_API_KEY", "k")
        infra = await registry.get_provider("rest-lite").build_infra(
            load_config(provider="rest-lite")
        )
        try:
            for call in (
                infra.sandbox_protocol.pause("s1"),
                infra.process_protocol.list_processes("http://x", None),
                infra.filesystem_protocol.exists("http://x", None, path="/x"),
            ):
                with pytest.raises(E.ProviderFeatureNotSupportedError) as exc:
                    await call
                assert exc.value.code == "E8004"
        finally:
            await infra.http_client.close()

    async def test_gate_only_blocks_methods_of_undeclared_features(self):
        calls = []

        class Target:
            async def create(self):
                calls.append("create")

            async def pause(self):
                calls.append("pause")

            async def set_timeout(self):
                calls.append("set_timeout")

        gated = gate_protocol(
            Target(), "rest-lite", SANDBOX_RULES, frozenset({"sandbox.lifecycle"})
        )
        await gated.create()
        for name in ("pause", "set_timeout"):
            with pytest.raises(E.ProviderFeatureNotSupportedError):
                await getattr(gated, name)()
        assert calls == ["create"]

    async def test_declared_feature_passes_through(self):
        class Impl:
            tag = "ok"

            async def pause(self):
                return self.tag

        gated = gate_protocol(Impl(), "p", SANDBOX_RULES, frozenset({"sandbox.pause"}))
        assert await gated.pause() == "ok"


class TestFeatureListing:
    def test_ordered_and_compact_features(self):
        features = [
            "pty",
            "unknown.thing",
            "exec.stream",
            "sandbox.pause",
            "sandbox.lifecycle",
            "exec.run",
        ]
        assert ordered_features(features) == [
            "sandbox.lifecycle",
            "sandbox.pause",
            "exec.run",
            "exec.stream",
            "pty",
            "unknown.thing",
        ]
        assert (
            compact_features(features)
            == "sandbox(lifecycle,pause) exec(run,stream) pty unknown(thing)"
        )
        assert compact_features([]) == ""

    def test_list_providers_reports_declared_features(self, iso):  # noqa: F811
        builtin = next(r for r in registry.list_providers() if r["id"] == "alicloud-express")
        assert len(builtin["features"]) > 10
